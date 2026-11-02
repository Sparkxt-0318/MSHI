"""Guarded table I/O, hashing, deterministic JSON output and result provenance.

``read_table`` is the only reader of tabular files (parquet/CSV) in ``mshi/``; tests/test_guards.py
fails if any other module calls a pandas/pyarrow table reader. It reads single files only and refuses
(1) a directory (a partitioned dataset): the v3 pipeline reads no directory datasets, and refusing them
    means every byte read passes checks (2) and (3);
(2) anything whose resolved path is under ``legacy/`` (compared case-insensitively) and is not in
    ``legacy_allowlist``, and an allow-listed file whose SHA-256 differs from the one pinned there;
(3) any file whose SHA-256 is listed in ``forbidden_sha256`` (the 3,000-row synthetic demo table from
    v1), whatever its name or location;
(4) any table with a column or index level named ``source`` that contains ``synthetic`` (catches
    re-encoded copies of the demo table, which have a different SHA-256). When the read projects other
    columns (``columns=``/``usecols=``), the file is read again without the projection, with every other
    option kept, and checked. Limit: the rule finds the column by its name, so a copy whose ``source``
    column was renamed, or a CSV read under other column names (``header=None, names=...``), is not
    caught by (4); a byte copy is still caught by (3).
Other inputs are not tables: GeoJSON (Natural Earth) and the SRDB CSV are checked against SHA-256s pinned
in the config, COSORE against its pinned commit and a clean worktree, and rasters (WorldClim, SoilGrids,
MODIS) against the hashes their fetch or extraction stage recorded (``require_outputs``).

Written files have the same bytes on every platform: JSON, Markdown and CSV are written with ``\n`` line
endings (``.gitattributes`` turns off line-ending conversion in git checkouts for the same reason).

Provenance (docs/DECISIONS.md D-P1-17, R-P1-21). ``write_result`` stamps each result with
- ``_provenance``: the config and code hashes of the run (the snapshot taken when ``mshi.run.run`` started);
- ``_outputs``: the SHA-256 of each file the stage wrote for later stages to read (tables, rasters,
  the reproduction table's Markdown). Fetch stages of pinned sources record none: their readers check the
  pinned hashes or commit directly; caches' sidecar files are checked by their own stage;
- ``_inputs``: the SHA-256 of each upstream result the stage read (``require_current``/``require_outputs``).
A result is current (``result_staleness`` is None) only if both hashes equal the current ones, every
recorded output still has its recorded bytes, and every recorded input still has the recorded bytes and
is itself current (checked recursively). An output under a root listed in
``provenance.local_only_roots`` (data/raw, data/interim: gitignored, so absent from a fresh clone) may be
absent without making the result stale; ``require_outputs`` refuses to hand such a file to a stage until
it is regenerated. A stage that reads another stage's outputs calls ``require_outputs`` first, so it
never runs on inputs produced by another config or code, changed after they were written, or produced
from upstream results that have since changed.
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


def _refuse_synthetic(p: Path, source) -> None:
    if pd.Series(source).astype(str).str.contains("synthetic", case=False).any():
        raise ForbiddenInputError(f"refusing to use {p}: its 'source' column contains synthetic rows "
                                  "(v1 demo data)")


def _source_values(df: pd.DataFrame):
    """The ``source`` column, or index level, of ``df``; None if it has neither."""
    if "source" in df.columns:
        return df["source"]
    if "source" in [n for n in (df.index.names or []) if n is not None]:
        return df.index.get_level_values("source")
    return None


def read_table(cfg: Config, path: str | Path, **kw) -> pd.DataFrame:
    p = check_readable(cfg, path)
    suf = p.suffix.lower()
    if suf == ".parquet":
        reader = pd.read_parquet
    elif suf in (".csv", ".txt"):
        reader = pd.read_csv
    else:
        raise ValueError(f"unsupported table format: {p}")
    df = reader(p, **kw)
    src = _source_values(df)
    if src is None and (kw.get("columns") is not None or kw.get("usecols") is not None):
        # the read projected other columns: read the file again without the projection, every other
        # option (separator, encoding, skiprows, comment, header, index_col, ...) kept, and check that
        src = _source_values(reader(p, **{k: v for k, v in kw.items() if k not in ("columns", "usecols")}))
    if src is not None:
        _refuse_synthetic(p, src)
    return df


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    if p.suffix.lower() == ".parquet":
        df.to_parquet(tmp, index=False)
    elif p.suffix.lower() == ".csv":
        df.to_csv(tmp, index=False, lineterminator="\n")      # pandas' default is os.linesep
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
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_clean(obj), fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, p)
    return p


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_text(text: str, path: str | Path) -> Path:
    """UTF-8 text with ``\n`` line endings on every platform."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return p


def write_result(cfg: Config, obj: dict, name: str, outputs: list | tuple = (),
                 inputs: list | tuple | dict = ()) -> Path:
    """Write ``results/<name>`` with ``_provenance`` (config and code hashes of this run: the snapshot
    taken when ``mshi.run.run`` started, else the current ones), ``_outputs`` (SHA-256 of each file in
    ``outputs``, keyed by ``Config.root_key``) and ``_inputs`` (SHA-256 of each upstream result in
    ``inputs``, as read through ``require_current`` in this process; a dict ``{name: sha256}`` carries over
    the inputs of a result being re-recorded), so later stages and tests can tell a current result from a
    stale one (module docstring)."""
    from .runlog import provenance
    prov = (cfg.invocation or {}).get("provenance") or provenance(cfg)
    rec = {k: v for k, v in obj.items() if k not in ("_provenance", "_outputs", "_inputs")}
    rec["_provenance"] = {"config_sha256": prov["config_sha256"], "code_sha256": prov["code_sha256"]}
    if outputs:
        rec["_outputs"] = {cfg.root_key(p): sha256_file(p) for p in outputs}
    if isinstance(inputs, dict):
        ins = dict(inputs)
    else:
        unread = [u for u in inputs if u not in cfg.reads]
        if unread:
            raise ValueError(f"write_result({name}): inputs {unread} were not read through require_current")
        ins = {u: cfg.reads[u] for u in inputs}
    if ins:
        rec["_inputs"] = ins
    return write_json(rec, cfg.path("results", name))


def _show(cfg: Config, key: str) -> str:
    p = cfg.from_root_key(key)
    try:
        return p.resolve().relative_to(cfg.repo_root.resolve()).as_posix()
    except ValueError:
        return str(p)


def local_only_roots(cfg: Config) -> set[str]:
    """Path roots whose files are not committed (configs/v3.yaml ``provenance.local_only_roots``)."""
    return set((cfg.get("provenance") or {}).get("local_only_roots", []))


def _read_result(cfg: Config, name: str) -> tuple[dict | None, str | None]:
    """(parsed result, SHA-256 of the bytes parsed); (None, None) if ``results/<name>`` does not exist."""
    p = cfg.path("results", name)
    if not p.is_file():
        return None, None
    raw = p.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def result_staleness(cfg: Config, obj: dict | None, _memo: dict | None = None) -> str | None:
    """None if ``obj`` (a result written by ``write_result``) is current (module docstring); otherwise a
    short reason. ``_memo`` caches the verdict per upstream result within one check."""
    from .runlog import provenance
    memo = {} if _memo is None else _memo
    if obj is None:
        return "missing"
    got = obj.get("_provenance")
    if not got:
        return "no provenance recorded"
    cur = provenance(cfg)
    diff = [k.replace("_sha256", "") for k in ("config_sha256", "code_sha256") if got.get(k) != cur[k]]
    if diff:
        return f"produced with a different {' and '.join(diff)}"
    local = local_only_roots(cfg)
    for key, digest in sorted((obj.get("_outputs") or {}).items()):
        p = cfg.from_root_key(key)
        if not p.is_file():
            if key.partition(":")[0] in local:
                continue            # not committed, so absent from a fresh clone; require_outputs checks it
            return f"missing its output {_show(cfg, key)}"
        if sha256_file(p) != digest:
            return f"its output {_show(cfg, key)} changed after the run"
    for up, digest in sorted((obj.get("_inputs") or {}).items()):
        up_obj, up_digest = _read_result(cfg, up)
        if up_obj is None:
            return f"its input results/{up} is missing"
        if up_digest != digest:
            return f"its input results/{up} changed after it was read"
        if up not in memo:
            memo[up] = None                                   # (no cycles exist; guards against one)
            memo[up] = ("records an incomplete run" if str(up_obj.get("status", "")).startswith("incomplete")
                        else result_staleness(cfg, up_obj, memo))
        if memo[up]:
            return f"its input results/{up} is not current ({memo[up]})"
    return None


def require_current(cfg: Config, name: str) -> dict:
    """``results/<name>``, if it is current (``result_staleness``) and records a complete run; raises
    StaleInputError otherwise. Records the bytes read in ``cfg.reads`` (a stage lists the results it
    used as ``inputs`` of its own result). Called by every stage before it reads another stage's outputs."""
    obj, digest = _read_result(cfg, name)
    if obj is not None and str(obj.get("status", "")).startswith("incomplete"):
        raise StaleInputError(f"results/{name} records an incomplete run ({obj['status']}); re-run its stage")
    why = result_staleness(cfg, obj)
    if why:
        raise StaleInputError(f"results/{name}: {why}; re-run the stage that writes it (or `make all`)")
    cfg.reads[name] = digest
    return obj


def require_outputs(cfg: Config, name: str, paths) -> dict:
    """``require_current(name)``, and every file in ``paths`` is one of the outputs it records (so its
    bytes were verified) and is present on this machine. Returns the result."""
    obj = require_current(cfg, name)
    recorded = obj.get("_outputs") or {}
    for p in paths:
        key = cfg.root_key(p)
        if key not in recorded:
            raise StaleInputError(f"{p} is not an output recorded in results/{name}; re-run the stage that "
                                  "writes it (or `make all`)")
        if not Path(p).is_file():
            raise StaleInputError(f"{_show(cfg, key)}, an output of results/{name}, is not on this machine "
                                  f"({key.partition(':')[0]} files are not committed); re-run the stage that "
                                  "writes it (or `make all`)")
    return obj
