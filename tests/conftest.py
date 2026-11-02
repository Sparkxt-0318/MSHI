import json
from pathlib import Path

import pytest

from mshi.config import REPO_ROOT, load_config


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def results_dir(cfg):
    return cfg.path("results")


def load_result(cfg, name):
    """A committed result; skipped if absent (stage not run), FAILS if it was produced by other code or
    config than the current checkout (re-run `make all`), so a stale file can never pass a regression test."""
    from mshi.io import result_staleness
    p = cfg.path("results", name)
    if not p.exists():
        pytest.skip(f"{p.relative_to(REPO_ROOT)} not present (stage not run)")
    obj = json.loads(p.read_text())
    stale = result_staleness(cfg, obj)
    if stale:
        pytest.fail(f"{p.relative_to(REPO_ROOT)} is stale ({stale}); run `make all`")
    return obj


def raw_available(cfg) -> bool:
    from mshi.data.fetch import cosore_repo_path, naturalearth_path, srdb_csv_path
    return (srdb_csv_path(cfg).exists() and (cosore_repo_path(cfg) / ".git").exists()
            and naturalearth_path(cfg, "ne_50m_admin_0_countries.geojson").exists())


def handoff(cfg, *parts) -> Path:
    return cfg.path("handoff", *parts)
