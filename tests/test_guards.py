"""The pipeline can never read the v1 synthetic demo table, and the locked test refuses to run if its plan,
definition or locked results are tampered with, whatever the config says."""
import ast
import copy
import hashlib
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

import mshi
from mshi.analysis import clean_test as CT
from mshi.analysis.clean_test import LockedPlanError, clean_test, verify_lock
from mshi.config import Config, canonical_sha256, load_config
from mshi.io import ForbiddenInputError, read_table

DEMO = "legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet"
PKG = Path(mshi.__file__).resolve().parent


# ---------------------------------------------------------------- demo table and legacy guard

def test_demo_table_refused_in_legacy(cfg):
    with pytest.raises(ForbiddenInputError):
        read_table(cfg, cfg.repo_path(DEMO))


def test_demo_table_refused_by_hash_anywhere(cfg, tmp_path):
    copy_ = tmp_path / "training_features.parquet"
    shutil.copy(cfg.repo_path(DEMO), copy_)
    with pytest.raises(ForbiddenInputError, match="forbidden"):
        read_table(cfg, copy_)


def test_demo_table_refused_inside_a_directory_dataset(cfg, tmp_path):
    ds = tmp_path / "training_features.parquet"
    ds.mkdir()
    shutil.copy(cfg.repo_path(DEMO), ds / "part-0.parquet")
    with pytest.raises(ForbiddenInputError, match="forbidden"):
        read_table(cfg, ds)


def test_reencoded_demo_table_refused_by_content(cfg, tmp_path):
    d = pd.read_parquet(cfg.repo_path(DEMO))          # direct read, test only
    d.to_parquet(tmp_path / "resaved.parquet", index=False, compression="gzip")
    d.to_csv(tmp_path / "export.csv", index=False)
    for f in ["resaved.parquet", "export.csv"]:
        with pytest.raises(ForbiddenInputError, match="synthetic"):
            read_table(cfg, tmp_path / f)


def test_legacy_path_check_is_case_insensitive(cfg):
    with pytest.raises(ForbiddenInputError):
        read_table(cfg, cfg.repo_root / "LEGACY" / "data" / "processed" / "training_features.parquet")


def test_non_allowlisted_legacy_tables_refused(cfg):
    for rel in ["legacy/data/processed/training_features.parquet",
                "legacy/data/processed/us_validation_features.parquet"]:
        with pytest.raises(ForbiddenInputError):
            read_table(cfg, cfg.repo_path(rel))


def test_allowlisted_v2_tables_readable_and_hash_pinned(cfg):
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in cfg["legacy_allowlist"].values())
    for rel in cfg["legacy_allowlist"]:
        d = read_table(cfg, cfg.repo_path(rel))
        assert len(d) in (615, 274)
        assert "synthetic" not in set(d.source)


def test_allowlisted_table_with_other_bytes_refused(cfg):
    data = copy.deepcopy(cfg.data)
    rel = next(iter(data["legacy_allowlist"]))
    data["legacy_allowlist"][rel] = "0" * 64
    with pytest.raises(ForbiddenInputError, match="pinned"):
        read_table(Config(data, source=cfg.source), cfg.repo_path(rel))


def test_demo_hash_is_the_synthetic_table(cfg):
    d = pd.read_parquet(cfg.repo_path(DEMO))          # direct read, test only: confirm what we forbid
    assert len(d) == 3000 and set(d.source) == {"synthetic"}


def test_config_does_not_reference_v1_tables(cfg):
    text = cfg.source.read_text()
    assert "training_features.parquet" not in text
    assert "SYNTHETIC" not in text


def test_no_direct_table_reads_outside_io():
    """mshi.io.read_table is the only table reader in the package (the guard cannot be bypassed)."""
    pat = re.compile(r"\b(pd|pandas)\.read_(parquet|csv|feather|excel|table|json|pickle|hdf|orc|sql|fwf)\b"
                     r"|\bpq\.read_table\b|\bpyarrow\.parquet\b|\bpyarrow\.csv\b|\bpl\.read_")
    offenders = [f"{f.relative_to(PKG)}:{i}" for f in PKG.rglob("*.py") if f.name != "io.py"
                 for i, line in enumerate(f.read_text().splitlines(), 1) if pat.search(line)]
    assert offenders == []


# ---------------------------------------------------------------- locked plan

def _tampered_cfg(cfg, tmp_path, *, plan_text=None, sha_text=None, locked_edit=None, rehash=False):
    data = copy.deepcopy(cfg.data)
    plan_src = cfg.repo_path(data["clean_test"]["plan"])
    plan = tmp_path / "ANALYSIS_PLAN_LOCKED.md"
    plan.write_bytes(plan_src.read_bytes() if plan_text is None else plan_text.encode())
    side = tmp_path / "ANALYSIS_PLAN_LOCKED.sha256"
    side.write_text(plan_src.with_suffix(".sha256").read_text() if sha_text is None else sha_text)
    data["clean_test"]["plan"] = str(plan)
    if locked_edit:
        locked_edit(data["clean_test"]["locked"])
    if rehash:                         # the "fix" a developer might try: paste the new hash into the config
        data["clean_test"]["locked_sha256"] = canonical_sha256(data["clean_test"]["locked"])
        if plan_text is not None:
            h = hashlib.sha256(plan.read_bytes()).hexdigest()
            data["clean_test"]["plan_sha256"] = h
            side.write_text(f"{h}  ANALYSIS_PLAN_LOCKED.md\n")
    return Config(data, source=cfg.source, out_root=tmp_path / "out")


def test_lock_ok_on_repo(cfg):
    info = verify_lock(cfg)
    assert info["plan_sha256"] == "9d50e120c42fa8b4ffdac7b98be1cfa461d4c22b7eac7f9a4aaf01e0befe3dac"
    assert info["locked_sha256"] == cfg["clean_test"]["locked_sha256"] == CT.LOCKED_SHA256
    assert info["locked_results_sha256"]["qc"].startswith("b091795f")


def test_config_hashes_equal_code_anchors(cfg):
    ct = cfg["clean_test"]
    assert ct["plan_sha256"] == CT.PLAN_SHA256
    assert ct["locked_sha256"] == CT.LOCKED_SHA256 == canonical_sha256(ct["locked"])
    assert {k: v["sha256"] for k, v in ct["locked_results"].items()} == CT.LOCKED_RESULT_SHA256


def test_lock_refuses_modified_plan(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    bad = _tampered_cfg(cfg, tmp_path, plan_text=orig.replace("seeds (42, 43, 44)", "seeds (1, 2, 3)"))
    with pytest.raises(LockedPlanError, match="modified"):
        verify_lock(bad)


def test_lock_refuses_modified_plan_even_if_config_and_sidecar_rehashed(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    bad = _tampered_cfg(cfg, tmp_path, plan_text=orig.replace("Europe", "Africa"), rehash=True)
    with pytest.raises(LockedPlanError):
        verify_lock(bad)


def test_lock_refuses_whitespace_change(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    with pytest.raises(LockedPlanError):
        verify_lock(_tampered_cfg(cfg, tmp_path, plan_text=orig + "\n"))


def test_lock_refuses_mismatched_sidecar(cfg, tmp_path):
    bad = _tampered_cfg(cfg, tmp_path, sha_text="0" * 64 + "  ANALYSIS_PLAN_LOCKED.md\n")
    with pytest.raises(LockedPlanError, match="does not record the locked hash"):
        verify_lock(bad)


EDITS = {
    "cv_seed": lambda L: L["cv_seeds"].__setitem__(0, 7),
    "C8 extra var": lambda L: L["sets"]["C8"].append("bio02"),
    "tie_margin": lambda L: L.__setitem__("tie_margin", 0.05),
    "xgb depth": lambda L: L["xgb"].__setitem__("max_depth", 6),
    "test NA": lambda L: L.__setitem__("test_continent", "North America"),
    "train Europe": lambda L: L.__setitem__("train_continent", "Europe"),
    "cv_folds": lambda L: L.__setitem__("cv_folds", 10),
    "cv_block_deg": lambda L: L.__setitem__("cv_block_deg", 2.0),
    "bootstrap_n": lambda L: L.__setitem__("bootstrap_n", 200),
    "bootstrap_seed": lambda L: L.__setitem__("bootstrap_seed", 1),
    "model_seed": lambda L: L.__setitem__("model_seed", 3),
    "C8+NPP without npp": lambda L: L["sets"]["C8+NPP"].remove("npp"),
    "drop C8+SOIL": lambda L: L["sets"].pop("C8+SOIL"),
    "ols_tp": lambda L: L.__setitem__("ols_tp", ["bio01", "bio05"]),
    "ols_tp_log": lambda L: L.__setitem__("ols_tp_log", []),
    "block_bootstrap_deg": lambda L: L.__setitem__("block_bootstrap_deg", 5.0),
    "seed_spread": lambda L: L.__setitem__("seed_spread", [0, 1]),
    "learners": lambda L: L.__setitem__("ml_learners", ["XGB"]),
    "ci": lambda L: L.__setitem__("ci_quantiles", [0.05, 0.95]),
    "aoa whisker": lambda L: L["aoa_whisker"].__setitem__("iqr_multiplier", 3.0),
    "di groups": lambda L: L.__setitem__("di_groups", 4),
    "rf predict threads": lambda L: L["rf"].__setitem__("predict_n_jobs", 2),
}


@pytest.mark.parametrize("rehash", [False, True], ids=["as-is", "rehashed"])
@pytest.mark.parametrize("name", sorted(EDITS))
def test_lock_refuses_edited_test_definition(cfg, tmp_path, name, rehash):
    bad = _tampered_cfg(cfg, tmp_path, locked_edit=EDITS[name], rehash=rehash)
    with pytest.raises(LockedPlanError, match="must not change") as e:
        verify_lock(bad)
    # the refusal never hands over the replacement hash
    assert canonical_sha256(bad["clean_test"]["locked"]) not in str(e.value)


def test_alternative_config_file_cannot_change_the_test(cfg, tmp_path):
    data = copy.deepcopy(cfg.data)
    data["clean_test"]["locked"]["test_continent"] = "North America"
    data["clean_test"]["locked_sha256"] = canonical_sha256(data["clean_test"]["locked"])
    p = tmp_path / "exploratory.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(LockedPlanError):
        verify_lock(load_config(p))


def test_lock_refuses_modified_locked_result(cfg, tmp_path):
    data = copy.deepcopy(cfg.data)
    src = cfg.repo_path(data["clean_test"]["locked_results"]["qc"]["file"])
    alt = tmp_path / "clean_test_europe.json"
    alt.write_text(src.read_text().replace('"r2": 0.0', '"r2": 0.5', 1) + " ")
    data["clean_test"]["locked_results"]["qc"]["file"] = str(alt)
    with pytest.raises(LockedPlanError, match="locked result"):
        verify_lock(Config(data, source=cfg.source))


def test_clean_test_stage_writes_nothing_when_refused(cfg, tmp_path):
    orig = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    bad = _tampered_cfg(cfg, tmp_path, plan_text=orig.replace("Europe", "Africa"))
    with pytest.raises(LockedPlanError):
        clean_test(bad)
    assert not (tmp_path / "out").exists()


def test_locked_test_class_verifies_the_lock(cfg, tmp_path):
    bad = _tampered_cfg(cfg, tmp_path, locked_edit=EDITS["tie_margin"], rehash=True)
    with pytest.raises(LockedPlanError):
        CT.LockedTest(bad)


def _plan_line(plan: str, start: str) -> str:
    return next(line for line in plan.splitlines() if line.lstrip("- ").startswith(start))


def test_locked_definition_matches_plan_text(cfg):
    """Every value in the config's locked block that the plan states is compared with the plan text."""
    plan = cfg.repo_path(cfg["clean_test"]["plan"]).read_text()
    L = cfg["clean_test"]["locked"]
    C8 = L["sets"]["C8"]
    assert "C8 = " + ", ".join(C8) in plan
    soil = re.search(r"5–15 cm mean\s+at 0\.05° \(([^)]+)\)", plan).group(1).split(", ")
    modis = _plan_line(plan, "C8+MODIS = C8 + ").split("C8 + ")[1].split("(")[0].strip().split(", ")
    assert _plan_line(plan, "C8+NPP = ").strip().endswith("C8 + npp")
    assert "C8+SOIL = C8 + 8 SoilGrids variables" in plan and "ALL = C8 + SOIL + MODIS" in plan
    assert L["sets"] == {"C8": C8, "C8+NPP": C8 + ["npp"], "C8+MODIS": C8 + modis, "C8+SOIL": C8 + soil,
                         "ALL": C8 + soil + modis}
    assert list(L["sets"]) == ["C8", "C8+NPP", "C8+MODIS", "C8+SOIL", "ALL"]
    assert f"Train = {L['train_continent']} sites; Test = {L['test_continent']} sites" in plan
    assert "OLS-TP: log Rs ~ bio01 + ln(bio12)" in plan
    assert L["ols_tp"] == ["bio01", "bio12"] and L["ols_tp_log"] == ["bio12"]
    assert L["ml_learners"] == ["XGB", "RF"] and "- XGB: " in plan and "- RF: " in plan
    x = L["xgb"]
    assert (f"n_estimators={x['n_estimators']}, max_depth={x['max_depth']}, learning_rate={x['learning_rate']}, "
            f"subsample={x['subsample']}, colsample_bytree={x['colsample_bytree']}, "
            f"min_child_weight={x['min_child_weight']}") in plan.replace("\n  ", " ")
    assert f"reg_alpha={x['reg_alpha']}, reg_lambda={x['reg_lambda']}, random_state={L['model_seed']}" in plan
    rf = L["rf"]
    assert (f"RF: {rf['n_estimators']} trees, min_samples_leaf={rf['min_samples_leaf']}, "
            f"max_features={rf['max_features']}, random_state={L['model_seed']}") in plan
    deg = int(L["cv_block_deg"])
    assert f"Mean R² over {L['cv_folds']}-fold spatial-block CV within Asia ({deg}° × {deg}° blocks)" in plan
    assert "seeds (" + ", ".join(map(str, L["cv_seeds"])) + ")" in plan
    assert f"if another candidate is within {L['tie_margin']} and has fewer predictors" in plan
    assert f"95% CI from a {L['bootstrap_n']:,}-draw site" in plan and L["ci_quantiles"] == [0.025, 0.975]
    assert f"from a {int(L['block_bootstrap_deg'])}° spatial-block bootstrap" in plan
    assert f"refit with seeds {L['seed_spread'][0]}–{L['seed_spread'][1]}" in plan
    w = L["aoa_whisker"]
    assert w["quantiles"] == [0.25, 0.75] and f"(Q3 + {w['iqr_multiplier']}·IQR)" in plan


def test_locked_constants_match_prototype(cfg):
    """Values the plan does not state are compared with the prototype docs/handoff/scripts/clean_test.py."""
    src = cfg.path("handoff", "scripts", "clean_test.py").read_text()
    L = cfg["clean_test"]["locked"]
    assert f"def boot_ci(y, p, lon=None, lat=None, deg=None, n={L['bootstrap_n']}, seed={L['bootstrap_seed']})" in src
    assert f"np.quantile(bs, {str(L['ci_quantiles'][0]).lstrip('0')})" in src
    assert f"for tr, va in folds(a, {L['aoa_cv_seed']}):" in src
    assert f"n_repeats={L['aoa_perm_repeats']}, random_state={L['aoa_perm_seed']}" in src
    assert f"default_rng({L['aoa_diff_seed']})" in src
    assert f"inside.sum() > {L['aoa_min_group']} and (~inside).sum() > {L['aoa_min_group']}" in src
    assert f"np.array_split(np.argsort(di_e), {L['di_groups']})" in src
    q = L["aoa_whisker"]["quantiles"]
    assert f"np.quantile(train_di, [{str(q[0]).lstrip('0')}, {str(q[1]).lstrip('0')}])" in src
    assert f"for s in range({L['seed_spread'][1] + 1})" in src
    assert 'cands = [(s, l) for s in SETS for l in ["XGB", "RF"]] + [("TP", "OLS-TP")]' in src
    assert "n_jobs=2" in src and L["rf"]["n_jobs"] == 2 and L["xgb"]["n_jobs"] == 2


# Hash of the syntax tree (docstrings removed) of the locked-test code. If this test fails, the locked
# analysis code changed: if the change alters nothing the plan defines, record why in docs/DECISIONS.md and
# update the pin; otherwise it is a deviation from the locked plan (ground rule 4).
LOCKED_CODE_AST_SHA256 = "66368bfad339558031a911988b60ba714b16fd3caeef08fbf9537e3d2c0eac35"


def _ast_digest(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        tree = ast.parse(Path(p).read_text())
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and body
                    and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
        h.update(ast.dump(tree, annotate_fields=True, include_attributes=False).encode())
    return h.hexdigest()


@pytest.mark.skipif(sys.version_info[:2] != (3, 13), reason="AST dumps are pinned for Python 3.13 (environment.yml)")
def test_locked_code_unchanged():
    assert _ast_digest([PKG / "analysis" / "clean_test.py", PKG / "spatial.py"]) == LOCKED_CODE_AST_SHA256
