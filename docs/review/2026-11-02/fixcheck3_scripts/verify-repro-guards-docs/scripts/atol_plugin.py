"""pytest plugin: point mshi.config.DEFAULT_CONFIG at an edited copy of configs/v3.yaml (scratch)."""
import os
from pathlib import Path

import mshi.config as C

C.DEFAULT_CONFIG = Path(os.environ["ATOL_CFG"])
print("atol_plugin: DEFAULT_CONFIG ->", C.DEFAULT_CONFIG)

import pytest

SEEN = set()


@pytest.fixture(autouse=True)
def _record_atol(request):
    if "cfg" in request.fixturenames:
        SEEN.add(request.getfixturevalue("cfg")["clean_test"]["deviation_atol"])
    yield


def pytest_sessionfinish(session, exitstatus):
    print("\natol_plugin: deviation_atol values seen by tests:", SEEN)
