"""Guarded table I/O, hashing and deterministic JSON output.

``read_table`` is the only way the pipeline reads a tabular file. It refuses
(1) anything under ``legacy/`` that is not in ``legacy_allowlist`` and
(2) any file whose SHA-256 is listed in ``forbidden_sha256`` (the 3,000-row synthetic
demo table from v1), whatever its name or location.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import Config


class ForbiddenInputError(RuntimeError):
    """Raised when a stage tries to read a table that must never enter the v3 pipeline."""


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def check_readable(cfg: Config, path: str | Path) -> Path:
    p = Path(path).resolve()
    repo = cfg.repo_root.resolve()
    legacy = (repo / "legacy").resolve()
    allow = {(repo / a).resolve() for a in cfg.get("legacy_allowlist", [])}
    if (legacy == p or legacy in p.parents) and p not in allow:
        raise ForbiddenInputError(f"refusing to read {p}: files under legacy/ are not v3 inputs "
                                  f"(allow-list: {sorted(str(a) for a in allow)})")
    if p.exists() and p.is_file():
        digest = sha256_file(p)
        if digest in set(cfg.get("forbidden_sha256", [])):
            raise ForbiddenInputError(f"refusing to read {p}: SHA-256 {digest[:12]}… is a forbidden "
                                      "table (v1 synthetic demo data)")
    return p


def read_table(cfg: Config, path: str | Path, **kw) -> pd.DataFrame:
    p = check_readable(cfg, path)
    suf = p.suffix.lower()
    if suf == ".parquet":
        return pd.read_parquet(p, **kw)
    if suf in (".csv", ".txt"):
        return pd.read_csv(p, **kw)
    raise ValueError(f"unsupported table format: {p}")


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    if p.suffix.lower() == ".parquet":
        df.to_parquet(tmp, index=False)
    elif p.suffix.lower() == ".csv":
        df.to_csv(tmp, index=False)
    else:
        raise ValueError(f"unsupported table format: {p}")
    os.replace(tmp, p)
    return p


def _clean(obj: Any) -> Any:
    """Make numpy/pandas objects JSON-serialisable; NaN/inf -> None."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if isinstance(obj, Path):
        return str(obj)
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def write_json(obj: Any, path: str | Path) -> Path:
    """Deterministic JSON (sorted keys, no timestamps) so result hashes are stable across runs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(_clean(obj), fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, p)
    return p


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
