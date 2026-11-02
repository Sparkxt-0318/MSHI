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
    p = cfg.path("results", name)
    if not p.exists():
        pytest.skip(f"{p.relative_to(REPO_ROOT)} not present (stage not run)")
    return json.loads(p.read_text())


def raw_available(cfg) -> bool:
    from mshi.data.fetch import cosore_repo_path, naturalearth_path, srdb_csv_path
    return (srdb_csv_path(cfg).exists() and (cosore_repo_path(cfg) / ".git").exists()
            and naturalearth_path(cfg, "ne_50m_admin_0_countries.geojson").exists())


def handoff(cfg, *parts) -> Path:
    return cfg.path("handoff", *parts)
