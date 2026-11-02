"""The pipeline can never read the v1 synthetic demo table, and the locked test refuses to run if tampered with."""
import copy
import re
import shutil

import pandas as pd
import pytest

from mshi.analysis.clean_test import LockedPlanError, clean_test, verify_lock
from mshi.config import Config, canonical_sha256
from mshi.io import ForbiddenInputError, read_table

DEMO = "legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet"


def test_demo_table_refused_in_legacy(cfg):
    with pytest.raises(ForbiddenInputError):
        read_table(cfg, cfg.repo_path(DEMO))


def test_demo_table_refused_by_hash_anywhere(cfg, tmp_path):
    copy_ = tmp_path / "training_features.parquet"
    shutil.copy(cfg.repo_path(DEMO), copy_)
    with pytest.raises(ForbiddenInputError, match="forbidden"):
        read_table(cfg, copy_)


def test_non_allowlisted_legacy_tables_refused(cfg):
    for rel in ["legacy/data/processed/training_features.parquet",
                "legacy/data/processed/us_validation_features.parquet"]:
        with pytest.raises(ForbiddenInputError):
            read_table(cfg, cfg.repo_path(rel))


def test_allowlisted_v2_tables_readable(cfg):
    for rel in cfg["legacy_allowlist"]:
        d = read_table(cfg, cfg.repo_path(rel))
        assert len(d) in (615, 274)
        assert "synthetic" not in set(d.source)


def test_demo_hash_is_the_synthetic_table(cfg):
    d = pd.read_parquet(cfg.repo_path(DEMO))          # direct read, test only: confirm what we forbid
    assert len(d) == 3000 and set(d.source) == {"synthetic"}


def test_config_does_not_reference_v1_tables(cfg):
    text = cfg.source.read_text()
    assert "training_features.parquet" not in text
    assert "SYNTHETIC" not in text


# ---------------------------------------------------------------- locked plan

def _tampered_cfg(cfg, tmp_path, *, plan_text=None, sha_text=None, locked_edit=None):
    data = copy.deepcopy(cfg.data)
    plan_src = cfg.repo_path(data["clean_test"]["plan"])
    plan = tmp_path / "ANALYSIS_PLAN_LOCKED.md"
    plan.write_bytes(plan_src.read_bytes() if plan_text is None else plan_text.encode())
    side = tmp_path / "ANALYSIS_PLAN_LOCKED.sha256"
    side.write_text(plan_src.with_suffix(".sha256").read_text() if sha_text is None else sha_text)
    data["clean_test"]["plan"] = str(plan)
    if locked_edit:
        locked_edit(data["clean_test"]["locked"])
    return Config(data, source=cfg.source, out_root=tmp_path / "out")


def test_lock_ok_on_repo(cfg):
    info = verify_lock(cfg)
    assert info["plan_sha256"] == "9d50e120c42fa8b4ffdac7b98be1cfa461d4c22b7eac7f9a4aaf01e0befe3dac"


def test_lock_refuses_modified_plan(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    bad = _tampered_cfg(cfg, tmp_path, plan_text=orig.replace("seeds (42, 43, 44)", "seeds (1, 2, 3)"))
    with pytest.raises(LockedPlanError, match="modified"):
        verify_lock(bad)


def test_lock_refuses_whitespace_change(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    with pytest.raises(LockedPlanError):
        verify_lock(_tampered_cfg(cfg, tmp_path, plan_text=orig + "\n"))


def test_lock_refuses_mismatched_sidecar(cfg, tmp_path):
    bad = _tampered_cfg(cfg, tmp_path, sha_text="0" * 64 + "  ANALYSIS_PLAN_LOCKED.md\n")
    with pytest.raises(LockedPlanError, match="recorded hash"):
        verify_lock(bad)


@pytest.mark.parametrize("edit", [
    lambda L: L["cv_seeds"].__setitem__(0, 7),
    lambda L: L["sets"]["C8"].append("bio02"),
    lambda L: L.__setitem__("tie_margin", 0.02),
    lambda L: L["xgb"].__setitem__("max_depth", 6),
    lambda L: L.__setitem__("test_continent", "North America"),
])
def test_lock_refuses_edited_test_definition(cfg, tmp_path, edit):
    with pytest.raises(LockedPlanError, match="must not change"):
        verify_lock(_tampered_cfg(cfg, tmp_path, locked_edit=edit))


def test_clean_test_stage_writes_nothing_when_refused(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    bad = _tampered_cfg(cfg, tmp_path, plan_text=orig.replace("Europe", "Africa"))
    with pytest.raises(LockedPlanError):
        clean_test(bad)
    assert not (tmp_path / "out").exists()


def test_locked_definition_matches_plan_text(cfg):
    """The config's locked block says what the plan says (catches a config that drifted before hashing)."""
    plan = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    L = cfg["clean_test"]["locked"]
    assert canonical_sha256(L) == cfg["clean_test"]["locked_sha256"]
    assert "C8 = " + ", ".join(L["sets"]["C8"]) in plan
    x = L["xgb"]
    assert (f"n_estimators={x['n_estimators']}, max_depth={x['max_depth']}, learning_rate={x['learning_rate']}, "
            f"subsample={x['subsample']}, colsample_bytree={x['colsample_bytree']}") in plan
    assert f"min_child_weight={x['min_child_weight']}" in plan and f"reg_alpha={x['reg_alpha']}" in plan
    assert f"reg_lambda={x['reg_lambda']}" in plan and "random_state=0" in plan
    rf = L["rf"]
    assert f"RF: {rf['n_estimators']} trees, min_samples_leaf={rf['min_samples_leaf']}, max_features={rf['max_features']}" in plan
    assert "seeds (" + ", ".join(map(str, L["cv_seeds"])) + ")" in plan
    assert "5-fold spatial-block CV within Asia (5° × 5° blocks)" in plan
    assert "within 0.01" in plan and "2,000-draw site" in plan and "2° spatial-block bootstrap" in plan
    assert "seeds 0–19" in plan
    assert re.search(r"Train = Asia sites; Test = Europe sites", plan)
    for s in ["C8+NPP", "C8+MODIS", "C8+SOIL", "ALL"]:
        assert f"- {s} = " in plan
