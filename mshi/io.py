"""Guarded table I/O, hashing and deterministic JSON output.

``read_table`` is the only reader of tabular files (parquet/CSV) in ``mshi/``; tests/test_guards.py
fails if any other module calls a pandas/pyarrow table reader. It refuses
(1) anything under ``legacy/`` (compared case-insensitively) that is not in ``legacy_allowlist``,
    and an allow-listed file whose SHA-256 differs from the one pinned there;
(2) any file, or any file inside a directory dataset, whose SHA-256 is listed in ``forbidden_sha256``
    (the 3,000-row synthetic demo table from v1), whatever its name or location;
(3) any table with a ``source`` column containing ``synthetic`` (catches re-encoded copies of the
    demo table, which have a different SHA-256).
Other inputs (GeoJSON via geopandas, COSORE ``.RDS`` via rdata, rasters via rasterio) are not tables
and are checked against pinned hashes or commits by the stages that read them.
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


def _allowlist(cfg: Config) -> dict[Path, str | None]:
    al = cfg.get("legacy_allowlist", {}) or {}
    if isinstance(al, list):                      # tolerate the older list form (no hash pins)
        al = {a: None for a in al}
    return {(cfg.repo_root / a).resolve(): h for a, h in al.items()}


def check_readable(cfg: Config, path: str | Path) -> Path:
    p = Path(path).resolve()
    repo = cfg.repo_root.resolve()
    legacy = (repo / "legacy").resolve().as_posix().lower()
    allow = _allowlist(cfg)
    in_legacy = p.as_posix().lower() == legacy or p.as_posix().lower().startswith(legacy + "/")
    if in_legacy:
        if p not in allow:
            raise ForbiddenInputError(f"refusing to read {p}: files under legacy/ are not v3 inputs "
                                      f"(allow-list: {sorted(str(a) for a in allow)})")
        pinned = allow[p]
        if pinned is not None and p.is_file() and sha256_file(p) != pinned:
            raise ForbiddenInputError(f"refusing to read {p}: allow-listed, but its SHA-256 is not the pinned "
                                      f"{pinned[:12]}…")
    forbidden = set(cfg.get("forbidden_sha256", []))
    files = [p] if p.is_file() else (sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [])
    for f in files:
        digest = sha256_file(f)
        if digest in forbidden:
            raise ForbiddenInputError(f"refusing to read {p}: {f.name} has SHA-256 {digest[:12]}…, a forbidden "
                                      "table (v1 synthetic demo data)")
    return p


def read_table(cfg: Config, path: str | Path, **kw) -> pd.DataFrame:
    p = check_readable(cfg, path)
    suf = p.suffix.lower()
    if suf == ".parquet":
        df = pd.read_parquet(p, **kw)
    elif suf in (".csv", ".txt"):
        df = pd.read_csv(p, **kw)
    else:
        raise ValueError(f"unsupported table format: {p}")
    if "source" in df.columns and df["source"].astype(str).str.contains("synthetic", case=False).any():
        raise ForbiddenInputError(f"refusing to use {p}: its 'source' column contains synthetic rows "
                                  "(v1 demo data)")
    return df


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
    """JSON with sorted keys and no timestamps, written atomically. Identical inputs give identical files
    as long as the computation itself is bit-reproducible (see docs/DECISIONS.md D-P1-1)."""
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


def write_result(cfg: Config, obj: dict, name: str) -> Path:
    """Write ``results/<name>`` with a ``_provenance`` block (config and code hashes, see
    ``mshi.runlog.provenance``) so later stages and tests can tell a current result from a stale one."""
    from .runlog import provenance
    return write_json({**obj, "_provenance": provenance(cfg)}, cfg.path("results", name))


def result_staleness(cfg: Config, obj: dict | None) -> str | None:
    """None if ``obj`` (a result written by ``write_result``) was produced by the current config and code;
    otherwise a short reason."""
    from .runlog import provenance
    if obj is None:
        return "missing"
    got = obj.get("_provenance")
    if not got:
        return "no provenance recorded"
    cur = provenance(cfg)
    diff = [k.replace("_sha256", "") for k in ("config_sha256", "code_sha256") if got.get(k) != cur[k]]
    return f"produced with a different {' and '.join(diff)}" if diff else None
