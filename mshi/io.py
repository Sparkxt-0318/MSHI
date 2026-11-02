"""Guarded table I/O, hashing, deterministic JSON output and result provenance.

``read_table`` is the only reader of tabular files (parquet/CSV) in ``mshi/``; tests/test_guards.py
fails if any other module calls a pandas/pyarrow table reader. It reads single files only and refuses
(1) a directory (a partitioned dataset): the v3 pipeline reads no directory datasets, and refusing them
    means every byte read passes checks (2) and (3);
(2) anything whose resolved path is under ``legacy/`` (compared case-insensitively) and is not in
    ``legacy_allowlist``, and an allow-listed file whose SHA-256 differs from the one pinned there;
(3) any file whose SHA-256 is listed in ``forbidden_sha256`` (the 3,000-row synthetic demo table from
    v1), whatever its name or location;
(4) any table whose ``source`` column contains ``synthetic`` (catches re-encoded copies of the demo
    table, which have a different SHA-256). The column is checked even when the read projects other
    columns.
Other inputs are not tables: GeoJSON (Natural Earth) and the SRDB CSV are checked against SHA-256s pinned
in the config, COSORE against its pinned commit and a clean worktree, and rasters (WorldClim, SoilGrids,
MODIS) against the hashes their fetch or extraction stage recorded (``require_outputs``).

Provenance. ``write_result`` stamps each result with the config and code hashes of the run (the snapshot
taken when ``mshi.run.run`` started) and the SHA-256 of every output file the stage wrote. A result is
current (``result_staleness`` is None) only if both hashes equal the current ones and every recorded
output still has its recorded bytes. A stage that reads another stage's outputs calls ``require_outputs``
first, so it never runs on inputs produced by another config or code, or changed after they were written.
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


class StaleInputError(RuntimeError):
    """An upstream result is missing, records an incomplete run, or is not current (another config or
    code, or an output file changed after the run). The run log records the stage as ``stale``."""


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
    """The resolved path, if it may be read (rules (1)-(3) in the module docstring); raises otherwise."""
    p = Path(path).resolve()
    if p.is_dir():
        raise ForbiddenInputError(f"refusing to read {p}: a directory dataset; the v3 pipeline reads single "
                                  "table files only")
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
    if p.is_file():
        digest = sha256_file(p)
        if digest in set(cfg.get("forbidden_sha256", [])):
            raise ForbiddenInputError(f"refusing to read {p}: SHA-256 {digest[:12]}…, a forbidden table "
                                      "(v1 synthetic demo data)")
    return p


def _refuse_synthetic(p: Path, source: pd.Series) -> None:
    if source.astype(str).str.contains("synthetic", case=False).any():
        raise ForbiddenInputError(f"refusing to use {p}: its 'source' column contains synthetic rows "
                                  "(v1 demo data)")


def read_table(cfg: Config, path: str | Path, **kw) -> pd.DataFrame:
    p = check_readable(cfg, path)
    suf = p.suffix.lower()
    if suf == ".parquet":
        df = pd.read_parquet(p, **kw)
    elif suf in (".csv", ".txt"):
        df = pd.read_csv(p, **kw)
    else:
        raise ValueError(f"unsupported table format: {p}")
    if "source" in df.columns:
        _refuse_synthetic(p, df["source"])
    elif kw.get("columns") is not None or kw.get("usecols") is not None:
        # the read projected other columns: check the file's own 'source' column, if it has one
        if suf == ".parquet":
            import pyarrow.parquet as pq
            if "source" in pq.read_schema(p).names:
                _refuse_synthetic(p, pd.read_parquet(p, columns=["source"])["source"])
        else:
            opts = {k: kw[k] for k in ("sep", "delimiter", "encoding") if k in kw}
            if "source" in pd.read_csv(p, nrows=0, **opts).columns:
                _refuse_synthetic(p, pd.read_csv(p, usecols=["source"], dtype=str, **opts)["source"])
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


def write_result(cfg: Config, obj: dict, name: str, outputs: list | tuple = ()) -> Path:
    """Write ``results/<name>`` with ``_provenance`` (config and code hashes of this run: the snapshot
    taken when ``mshi.run.run`` started, else the current ones) and ``_outputs`` (SHA-256 of each file in
    ``outputs``, keyed by ``Config.root_key``), so later stages and tests can tell a current result from
    a stale one."""
    from .runlog import provenance
    prov = (cfg.invocation or {}).get("provenance") or provenance(cfg)
    rec = {k: v for k, v in obj.items() if k not in ("_provenance", "_outputs")}
    rec["_provenance"] = {"config_sha256": prov["config_sha256"], "code_sha256": prov["code_sha256"]}
    if outputs:
        rec["_outputs"] = {cfg.root_key(p): sha256_file(p) for p in outputs}
    return write_json(rec, cfg.path("results", name))


def _show(cfg: Config, key: str) -> str:
    p = cfg.from_root_key(key)
    try:
        return p.resolve().relative_to(cfg.repo_root.resolve()).as_posix()
    except ValueError:
        return str(p)


def result_staleness(cfg: Config, obj: dict | None) -> str | None:
    """None if ``obj`` (a result written by ``write_result``) was produced by the current config and code
    and every output it records still has its recorded bytes; otherwise a short reason."""
    from .runlog import provenance
    if obj is None:
        return "missing"
    got = obj.get("_provenance")
    if not got:
        return "no provenance recorded"
    cur = provenance(cfg)
    diff = [k.replace("_sha256", "") for k in ("config_sha256", "code_sha256") if got.get(k) != cur[k]]
    if diff:
        return f"produced with a different {' and '.join(diff)}"
    for key, digest in sorted((obj.get("_outputs") or {}).items()):
        p = cfg.from_root_key(key)
        if not p.is_file():
            return f"missing its output {_show(cfg, key)}"
        if sha256_file(p) != digest:
            return f"its output {_show(cfg, key)} changed after the run"
    return None


def require_current(cfg: Config, name: str) -> dict:
    """``results/<name>``, if it is current (``result_staleness``) and records a complete run; raises
    StaleInputError otherwise. Called by every stage before it reads another stage's outputs."""
    p = cfg.path("results", name)
    obj = read_json(p) if p.exists() else None
    if obj is not None and str(obj.get("status", "")).startswith("incomplete"):
        raise StaleInputError(f"results/{name} records an incomplete run ({obj['status']}); re-run its stage")
    why = result_staleness(cfg, obj)
    if why:
        raise StaleInputError(f"results/{name}: {why}; re-run the stage that writes it (or `make all`)")
    return obj


def require_outputs(cfg: Config, name: str, paths) -> dict:
    """``require_current(name)``, and every file in ``paths`` is one of the outputs it records (so its
    bytes were verified). Returns the result."""
    obj = require_current(cfg, name)
    recorded = obj.get("_outputs") or {}
    for p in paths:
        if cfg.root_key(p) not in recorded:
            raise StaleInputError(f"{p} is not an output recorded in results/{name}; re-run the stage that "
                                  "writes it (or `make all`)")
    return obj
