"""Run tests/ against the sandbox (what `make test` does after `make all`): load_config() with no path returns
the sandbox config, so conftest's cfg fixture and load_result read the sandbox results/.

python -I -B pytest_sandbox.py CONFIG_YAML BASETEMP test_file_or_nodeid [...]
"""
import sys

sys.path.insert(0, "/home/user/MSHI")

import mshi.config as C  # noqa: E402

SB_YAML = sys.argv[1]
_real = C.load_config


def _patched(path=None, out_root=None):
    return _real(path or SB_YAML, out_root)


C.load_config = _patched

import pytest  # noqa: E402

sys.exit(pytest.main(["-p", "no:cacheprovider", f"--basetemp={sys.argv[2]}", "-q", "-rA",
                      "-o", "console_output_style=classic", *sys.argv[3:]]))
