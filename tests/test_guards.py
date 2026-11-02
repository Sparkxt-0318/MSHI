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


def test_directory_datasets_refused(cfg, tmp_path):
    """read_table reads single files only, so no member of a directory can escape the checks (a symlinked
    legacy table or a symlinked sub-directory inside a dataset used to be read)."""
    ds = tmp_path / "training_features.parquet"
    ds.mkdir()
    shutil.copy(cfg.repo_path(DEMO), ds / "part-0.parquet")
    with pytest.raises(ForbiddenInputError, match="directory"):
        read_table(cfg, ds)
    link = tmp_path / "dirlink.parquet"
    link.mkdir()
    (link / "part-0.parquet").symlink_to(cfg.repo_path("legacy/data/processed/training_features.parquet"))
    with pytest.raises(ForbiddenInputError, match="directory"):
        read_table(cfg, link)
    with pytest.raises(ForbiddenInputError, match="legacy"):            # the member itself: legacy rule
        read_table(cfg, link / "part-0.parquet")


def test_source_column_checked_even_when_the_read_projects_other_columns(cfg, tmp_path):
    d = pd.read_parquet(cfg.repo_path(DEMO))          # direct read, test only
    d.to_parquet(tmp_path / "resaved.parquet", index=False, compression="gzip")
    d.to_csv(tmp_path / "export.csv", index=False)
    with pytest.raises(ForbiddenInputError, match="synthetic"):
        read_table(cfg, tmp_path / "resaved.parquet", columns=["longitude", "latitude"])
    with pytest.raises(ForbiddenInputError, match="synthetic"):
        read_table(cfg, tmp_path / "export.csv", usecols=["longitude", "latitude"])
    with pytest.raises(ForbiddenInputError, match="synthetic"):
        read_table(cfg, tmp_path / "export.csv", usecols=lambda c: c != "source")
    ok = d.assign(source="srdb")[["longitude", "latitude", "source"]]
    ok.to_parquet(tmp_path / "real.parquet", index=False)
    assert read_table(cfg, tmp_path / "real.parquet", columns=["longitude"]).shape == (3000, 1)


def test_source_checked_as_an_index_and_under_header_changing_options(cfg, tmp_path):
    """Third review: 'source' restored as a (multi-)index, and CSV projections combined with options that
    change which line is the header, escaped the content check."""
    d = pd.read_parquet(cfg.repo_path(DEMO))          # direct read, test only
    d.set_index("source").to_parquet(tmp_path / "source_index.parquet")
    d.set_index(["source", "longitude"]).to_parquet(tmp_path / "multiindex.parquet")
    d.to_csv(tmp_path / "export.csv", index=False)
    (tmp_path / "preamble.csv").write_text("# exported from v1\n" + (tmp_path / "export.csv").read_text())
    for f, kw in [("source_index.parquet", {}), ("multiindex.parquet", {}),
                  ("source_index.parquet", {"columns": ["longitude"]}),
                  ("export.csv", {"index_col": "source"}),
                  ("preamble.csv", {"skiprows": 1, "usecols": ["longitude", "latitude"]}),
                  ("preamble.csv", {"comment": "#", "usecols": ["longitude"]})]:
        with pytest.raises(ForbiddenInputError, match="synthetic"):
            read_table(cfg, tmp_path / f, **kw)


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


# ---------------------------------------------------------------- reproduction targets

# A literal copy of docs/handoff/PROMPT_mshi_v3.md section 4 "Reproduction targets", in the encoding of
# docs/DECISIONS.md D-P1-10 ("exact" -> abs 0; ±x% -> rel; "±0.01 R²" -> abs 0.01 for the R² and its CI
# bounds; Europe n, given without tolerance, -> exact). COSORE 66 comes from the handoff's prep_log
# (sources table) and the 189 row is INFO only (prep_log D8). The targets gate Phase 1 (ground rule 2), so
# loosening one in the config must fail this test, not only change the table.
BRIEF_TARGETS = {
    "srdb_repo_filter_records": {"value": 4771, "abs": 0},
    "cosore_sites": {"value": 66, "abs": 0},
    "records_after_coord_check": {"value": 4781, "rel": 0.01},
    "records_after_qc": {"value": 3694, "rel": 0.01},
    "qc_removed_by": {"f_method": {"value": 450, "rel": 0.02}, "f_quality": {"value": 260, "rel": 0.02},
                      "f_coverage": {"value": 252, "rel": 0.02}, "f_ecosys": {"value": 243, "rel": 0.02},
                      "f_dup": {"value": 57, "rel": 0.02}},
    "sites_qc_by_continent": {"Asia": {"value": 387, "rel": 0.02}, "North America": {"value": 257, "rel": 0.02},
                              "Europe": {"value": 236, "rel": 0.02}, "South America": {"value": 42, "rel": 0.02},
                              "Africa": {"value": 26, "rel": 0.02}, "Oceania": {"value": 23, "rel": 0.02}},
    "sites_qc_total": {"value": 971, "rel": 0.02},
    "sites_repo_total": {"value": 1225, "rel": 0.02},
    "locked_test": {"selected": "OLS-TP", "asia_cv_r2": {"value": 0.143, "abs": 0.01},
                    "europe_n": {"value": 235, "abs": 0}, "europe_r2": {"value": 0.079, "abs": 0.01},
                    "europe_ci_lo": {"value": 0.013, "abs": 0.01}, "europe_ci_hi": {"value": 0.125, "abs": 0.01}},
    "npp_corr_original_sites": {"value": 0.982, "abs": 0.01, "n_sites": 889},
    "npp_recovered_sites": {"value": 189, "info_only": True},
}
BRIEF_ROWS = [
    "| SRDB records after repo filters | 4,771 | exact |",
    "| Records after coordinate check / after QC | 4,781 / 3,694 | ±1% |",
    "| QC removals: method / quality / coverage / ecosystem / duplicate | 450 / 260 / 252 / 243 / 57 | ±2% |",
    "| QC sites by continent: Asia / N America / Europe / S America / Africa / Oceania | 387 / 257 / 236 / 42 / "
    "26 / 23 (total 971) | ±2% |",
    "| Repo-filter sites total | 1,225 | ±2% |",
    "| Locked test: selected model; Asia spatial-CV R²; Europe n; Europe R² and site-bootstrap CI | OLS-TP; 0.143; "
    "235; 0.079 [0.013, 0.125] | same model; ±0.01 R² |",
    "| NPP correlation with the repo's committed NPP at the original 889 sites | r = 0.982 | ±0.01 |",
]


def test_reproduction_targets_are_the_briefs(cfg):
    text = cfg.path("handoff", "PROMPT_mshi_v3.md").read_text()
    for row in BRIEF_ROWS:                     # the literal copy above still matches its source
        assert row in text, row
    assert "reproduces exactly 66 sites" in cfg.path("handoff", "prep_log.md").read_text()
    assert cfg["reproduction_targets"] == BRIEF_TARGETS


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


def test_lock_refuses_dropping_a_locked_variant(cfg, tmp_path):
    data = copy.deepcopy(cfg.data)
    data["clean_test"]["variants"] = ["qc"]          # the plan-specified repo-filter sensitivity dropped
    with pytest.raises(LockedPlanError, match="every locked variant"):
        verify_lock(Config(data, source=cfg.source))


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


# Hashes of the syntax tree (docstrings removed) of the locked-test code. If a test fails, the locked
# analysis code changed: if the change alters nothing the plan defines, record why in docs/DECISIONS.md and
# update the pin; otherwise it is a deviation from the locked plan (ground rule 4).
# - the whole of clean_test.py (anchors, lock checks, the stage wrapper) and spatial.py: updated in R-P1-20
#   (stage wrapper: require_outputs, deviation_atol from the config, every locked variant required) and in
#   R-P1-21 (stage wrapper: the re-run records features.json as its input);
# - the LockedTest class alone (selection, scoring, metrics, AOA): unchanged since D-P1-9.
LOCKED_CODE_AST_SHA256 = "0feeaa0fc7298d54a402ea0901b7b4d85250e5871f8b5d4f627c74473c5a586f"
LOCKED_TEST_CLASS_AST_SHA256 = "9487b2b4a22e06f1326f58fbf008ee5de0067fc25f0263e80f7ca18952b11a66"


def _strip_docstrings(tree):
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return tree


def _ast_digest(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        tree = _strip_docstrings(ast.parse(Path(p).read_text()))
        h.update(ast.dump(tree, annotate_fields=True, include_attributes=False).encode())
    return h.hexdigest()


def _class_digest(path, name) -> str:
    tree = _strip_docstrings(ast.parse(Path(path).read_text()))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


@pytest.mark.skipif(sys.version_info[:2] != (3, 13), reason="AST dumps are pinned for Python 3.13 (environment.yml)")
def test_locked_code_unchanged():
    assert _ast_digest([PKG / "analysis" / "clean_test.py", PKG / "spatial.py"]) == LOCKED_CODE_AST_SHA256


@pytest.mark.skipif(sys.version_info[:2] != (3, 13), reason="AST dumps are pinned for Python 3.13 (environment.yml)")
def test_locked_computation_unchanged():
    assert _class_digest(PKG / "analysis" / "clean_test.py", "LockedTest") == LOCKED_TEST_CLASS_AST_SHA256


def test_deviation_tolerance_is_the_documented_one(cfg):
    """The tolerance that decides PASS ('identical') vs DEVIATION for the locked-test re-runs is anchored
    here, as the reproduction targets are (docs/DECISIONS.md D-P1-10): moving it into the config must not
    let a config edit turn a deviation from the locked result into a PASS (ground rule 4)."""
    assert cfg["clean_test"]["deviation_atol"] == 1e-9


# ---------------------------------------------------------------- bytes on every platform

HASHED = ["mshi/io.py", "configs/v3.yaml", "docs/handoff/ANALYSIS_PLAN_LOCKED.md",
          "docs/handoff/results/clean_test_europe.json", "docs/handoff/results/clean_test_europe_repo_sensitivity.json",
          "results/reproduction_check.md", "data/derived/cosore_annual.csv",
          "legacy/data/processed/training_features_v2.parquet"]


def test_hashed_files_are_checked_out_without_line_ending_conversion(cfg):
    """Code, plan, locked results, recorded outputs and allow-listed tables are hashed byte for byte, so a
    CRLF checkout (Git for Windows' default core.autocrlf) must not change them (.gitattributes)."""
    import subprocess
    out = subprocess.run(["git", "-C", str(cfg.repo_root), "check-attr", "text", "--", *HASHED],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert [ln.rsplit(": ", 1)[-1] for ln in out] == ["unset"] * len(HASHED), out


def test_local_only_roots_are_exactly_the_gitignored_roots(cfg):
    """A recorded output may be absent only under a root that is not committed (mshi.io.local_only_roots)."""
    import subprocess
    from mshi.io import local_only_roots
    ignored = set()
    for root, rel in cfg["paths"].items():
        r = subprocess.run(["git", "-C", str(cfg.repo_root), "check-ignore", "-q", "--no-index", f"{rel}/x.parquet"])
        if r.returncode == 0:
            ignored.add(root)
    assert local_only_roots(cfg) == ignored == {"raw", "interim"}


def test_written_files_use_lf_line_endings(cfg, tmp_path, monkeypatch):
    import os
    from mshi.io import write_json, write_table, write_text
    monkeypatch.setattr(os, "linesep", "\r\n")                         # pandas' default line terminator
    paths = [write_table(pd.DataFrame({"a": [1, 2]}), tmp_path / "t.csv"), write_json({"a": [1, 2]}, tmp_path / "t.json"),
             write_text("a\nb\n", tmp_path / "t.md")]
    assert all(b"\r" not in p.read_bytes() for p in paths)
