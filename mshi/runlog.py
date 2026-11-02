"""Stage timing, environment capture and the append-only run log."""
from __future__ import annotations

import importlib
import json
import platform
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PACKAGES = ["numpy", "pandas", "scipy", "sklearn", "statsmodels", "xgboost", "pyarrow", "rasterio",
            "geopandas", "pyproj", "pystac_client", "requests", "rdata", "matplotlib", "yaml", "shapely",
            "pyogrio"]


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
    r = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    dirty = subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    return r.stdout.strip() + ("+dirty" if dirty else "")


@contextmanager
def stage_timer(log_path: Path, stage: str, extra: dict | None = None):
    """Append one JSON line per stage run to ``log_path`` (start/end UTC, seconds, status)."""
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
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
