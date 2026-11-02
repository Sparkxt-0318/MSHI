"""Stage timing, provenance, environment capture and the append-only run log."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

PACKAGES = ["numpy", "pandas", "scipy", "sklearn", "statsmodels", "xgboost", "pyarrow", "rasterio",
            "geopandas", "pyproj", "pystac_client", "requests", "rdata", "matplotlib", "yaml", "shapely",
            "pyogrio"]
# Paths whose uncommitted changes (including new, untracked files) mark a run as "+dirty".
PROVENANCE_PATHS = ["mshi", "configs", "tests", "Makefile", "pyproject.toml", "environment.yml",
                    "requirements-lock.txt", "docs/handoff"]
_GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}   # never rewrite .git/index (concurrent sessions)


def package_versions() -> dict:
    out = {"python": platform.python_version()}
    for name in PACKAGES:
        try:
            m = importlib.import_module(name)
            out[name] = getattr(m, "__version__", "?")
        except Exception:  # noqa: BLE001 - optional packages may be missing in a minimal env
            out[name] = None
    try:
        import rasterio
        out["gdal"] = rasterio.__gdal_version__
    except Exception:  # noqa: BLE001
        pass
    return out


def git_commit(repo_root: Path) -> str | None:
    """HEAD commit, with ``+dirty`` if code, config, tests, environment files or the handoff bundle have
    uncommitted changes or untracked files. Uses no optional locks, so it never writes .git/index."""
    r = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True,
                       env=_GIT_ENV)
    if r.returncode != 0:
        return None
    dirty = subprocess.run(["git", "-C", str(repo_root), "--no-optional-locks", "status", "--porcelain",
                            "--untracked-files=normal", "--"] + PROVENANCE_PATHS,
                           capture_output=True, text=True, env=_GIT_ENV).stdout.strip()
    return r.stdout.strip() + ("+dirty" if dirty else "")


@lru_cache(maxsize=4)
def _code_sha256_cached(pkg_dir: str, stamp: tuple) -> str:
    h = hashlib.sha256()
    for f in sorted(Path(pkg_dir).rglob("*.py")):
        h.update(f.relative_to(pkg_dir).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def code_sha256(pkg_dir: Path | None = None) -> str:
    """SHA-256 over the source of every module in the ``mshi`` package (path + bytes, sorted)."""
    pkg = Path(pkg_dir) if pkg_dir else Path(__file__).resolve().parent
    stamp = tuple(sorted((f.as_posix(), f.stat().st_mtime_ns, f.stat().st_size) for f in pkg.rglob("*.py")))
    return _code_sha256_cached(str(pkg), stamp)


def provenance(cfg) -> dict:
    """Recorded in every stage result JSON: the config and code that produced it (no timestamps, no
    commit id, so the file is unchanged by commits that do not touch code or config)."""
    return {"config_sha256": cfg.sha256(), "code_sha256": code_sha256()}


@contextmanager
def stage_timer(log_path: Path, stage: str, extra: dict | None = None):
    """Append one JSON line per stage run to ``log_path`` (start/end UTC, seconds, status, provenance)."""
    start = time.time()
    rec = {"stage": stage, "start_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if extra:
        rec.update(extra)
    status = "ok"
    try:
        yield rec
    except BaseException as e:  # noqa: BLE001 - record failures of any kind, then re-raise
        status = f"error: {type(e).__name__}: {e}"
        raise
    finally:
        rec["seconds"] = round(time.time() - start, 2)
        rec["end_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec["status"] = rec.get("status_override", status)
        rec.pop("status_override", None)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
