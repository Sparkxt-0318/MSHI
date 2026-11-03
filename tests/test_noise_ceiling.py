"""Noise ceiling: 3-level REML variance components by continent (mshi/analysis/noise_ceiling.py; Phase 2 item 3).

Offline and synthetic: records simulated from the nested model with known components, sandboxed site builds and few
bootstrap replicates (the code paths are those of the full run). No real outcome is scored.
"""
import json

import numpy as np
import pandas as pd
import pytest

from mshi.analysis import noise_ceiling as NC
from mshi.config import Config
from mshi.io import StaleInputError, write_result, write_table
from test_robustness import sandbox

CONTINENTS = ["Asia", "Europe", "Oceania"]
SITES = {"Asia": 40, "Europe": 32, "Oceania": 10}        # Oceania < phase2.min_test_sites (30): supplementary


@pytest.fixture(scope="module", autouse=True)
def frozen_code_hash():
    """Other modules of the package may be edited while this file runs; freeze the code hash for its duration so
    results written and checked here agree."""
    from mshi import runlog
    h = runlog.code_sha256()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runlog, "code_sha256", lambda pkg_dir=None: h)
        yield h


def settings(data: dict, **nc) -> None:
    """Test settings: three continents, few replicates, and the config key this module needs that configs/v3.yaml does
    not have yet (``optimizer``)."""
    data["phase2"]["continents"] = list(CONTINENTS)
    data["phase2"]["noise_ceiling"].update({"n_boot": 6, "seed": 7, "min_records_per_site": 2, "optimizer": "lbfgs",
                                            **nc})


def simulate(seed: int, n_sites: int, s2: tuple[float, float, float], studies=(1, 4), records=(1, 4)):
    """Nested design: per site 1-3 studies (``studies`` bounds), per study 1-3 records; log Rs = 6.5 + a + b + e.
    Returns (y, site, study) as integer codes in site and study order."""
    rng = np.random.default_rng(seed)
    y, site, study, t = [], [], [], 0
    for i in range(n_sites):
        a = rng.normal(0, np.sqrt(s2[0]))
        for _j in range(rng.integers(*studies)):
            b = rng.normal(0, np.sqrt(s2[1]))
            for _k in range(rng.integers(*records)):
                y.append(6.5 + a + b + rng.normal(0, np.sqrt(s2[2])))
                site.append(i)
                study.append(t)
            t += 1
    return np.array(y), np.array(site), np.array(study)


def synth_tables(seed: int = 0, s2=(0.3, 0.1, 0.05)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Records and sites of an analysis build: nested model per continent, every 5th site a singleton, a COSORE record
    at every 7th site, one Study_number reused at two Asian sites, one site outside the analysed continents. The locked
    ``continent`` column holds a value no stage may use."""
    rng = np.random.default_rng(seed)
    recs, k, sn = [], 0, 100
    for c, n in list(SITES.items()) + [("Antarctica", 1)]:
        for i in range(n):
            sid = f"v3aqc_{k:05d}"
            a = rng.normal(0, np.sqrt(s2[0]))
            for j in range(1 if i % 5 == 0 else int(rng.integers(1, 4))):
                sn += 1
                study = 100 if (c == "Asia" and i in (1, 2) and j == 0) else sn       # Study_number 100 at 2 sites
                b = rng.normal(0, np.sqrt(s2[1]))
                for _r in range(1 if i % 5 == 0 else int(rng.integers(1, 4))):
                    recs.append({"rec_id": f"srdb_{len(recs)}", "src": "srdb", "Study_number": float(study),
                                 "site": sid, "cont": c, "log_rs": 6.5 + a + b + rng.normal(0, np.sqrt(s2[2]))})
            if i % 7 == 3:
                recs.append({"rec_id": f"d2020_COSORE_{k}", "src": "cosore", "Study_number": np.nan, "site": sid,
                             "cont": c, "log_rs": 6.5 + a + rng.normal(0, np.sqrt(s2[1] + s2[2]))})
            k += 1
    r = pd.DataFrame(recs)
    r["site_id_qc"] = r.site
    r["site_id_repo"] = r.site.str.replace("v3aqc_", "v3arepo_")
    r["continent"] = "not-a-continent"
    r["rs"] = np.exp(r.log_rs)
    g = r.groupby("site")
    st = pd.DataFrame({"site_id": g.size().index, "n_rec": g.size().values, "log_rs": g.log_rs.mean().values,
                       "continent_geo": g.cont.first().values, "lat": 10.0, "lon": 20.0})
    st["continent"] = "not-a-continent"
    return r.drop(columns=["site", "cont"]), st


def record_build(sand: Config, r: pd.DataFrame, st: pd.DataFrame) -> list:
    """The synthetic tables recorded as outputs of a current build_sites_analysis result."""
    paths = [write_table(r, sand.path("derived", "records_analysis.parquet")),
             write_table(st, sand.path("derived", "sites_analysis_qc.parquet")),
             write_table(st.assign(site_id=st.site_id.str.replace("v3aqc_", "v3arepo_")),
                         sand.path("derived", "sites_analysis_repo.parquet"))]
    write_result(sand, {"synthetic": True}, "build_sites_analysis.json", outputs=paths)
    return paths


@pytest.fixture(scope="module")
def staged(cfg, tmp_path_factory):
    sand = sandbox(cfg, tmp_path_factory.mktemp("noise"), edit=settings)
    r, st = synth_tables()
    record_build(sand, r, st)
    summary = NC.noise_ceiling(sand)
    raw = sand.path("results", NC.RESULT).read_bytes()
    return sand, r, st, summary, raw, json.loads(raw)


# ---------------------------------------------------------------- model

def test_recovers_known_variance_components():
    y, site, study = simulate(11, 400, (0.3, 0.1, 0.05))
    fit = NC.fit_nested(y, site, study, "lbfgs")
    assert fit["status"] == "ok" and fit["chosen"] == "interior" and not fit["boundary"]
    assert fit["s2_site"] == pytest.approx(0.3, rel=0.2)
    assert fit["s2_study"] == pytest.approx(0.1, rel=0.25)
    assert fit["s2_record"] == pytest.approx(0.05, rel=0.15)
    assert fit["n"]["sites"] == 400 and fit["n"]["records"] == len(y) and fit["n"]["studies"] == study[-1] + 1


def test_array_model_is_n3s_formula_model():
    """The VCSpec construction is the model of N3's vc_formula {"study": "0 + C(study)"} (same estimates)."""
    import statsmodels.formula.api as smf
    y, site, study = simulate(3, 60, (0.3, 0.1, 0.05))
    mine = NC._fit_candidate("interior", y, site, study, "lbfgs")
    d = pd.DataFrame({"log_rs": y, "site": site, "study": [f"{s}_{t}" for s, t in zip(site, study)]})
    n3 = smf.mixedlm("log_rs ~ 1", d, groups=d["site"], re_formula="1",
                     vc_formula={"study": "0 + C(study)"}).fit(reml=True, method="lbfgs")
    assert mine["usable"]
    assert mine["s2_site"] == pytest.approx(float(np.asarray(n3.cov_re)[0, 0]), rel=1e-6)
    assert mine["s2_study"] == pytest.approx(float(n3.vcomp[0]), rel=1e-6)
    assert mine["s2_record"] == pytest.approx(float(n3.scale), rel=1e-6)
    assert mine["llf"] == pytest.approx(float(n3.llf), rel=1e-9)


def test_boundary_model_kept_where_lbfgs_stops_short():
    """Simulated without a study effect. With the pinned scipy/statsmodels, lbfgs reports convergence of the interior
    model at s2_study ~ 0.014 with a REML log-likelihood ~1.9 below the s2_study = 0 model; the stage keeps the
    latter."""
    y, site, study = simulate(5, 30, (0.25, 0.0, 0.12))
    fit = NC.fit_nested(y, site, study, "lbfgs")
    c = fit["candidates"]
    assert fit["status"] == "ok" and fit["boundary"]
    best = max(v["llf"] for v in c.values() if v["usable"])
    assert c[fit["chosen"]]["llf"] == best
    assert fit["s2_study"] / (fit["s2_site"] + fit["s2_study"] + fit["s2_record"]) < NC.ZERO_SHARE


def test_choose_prefers_highest_llf_and_breaks_ties_in_candidate_order():
    def c(llf, usable=True):
        return {"usable": usable, "llf": llf}
    assert NC.choose({"interior": c(-80.0), "no_study": c(-79.5), "no_site": c(-86.0)}) == "no_study"
    assert NC.choose({"interior": c(-79.5 - NC.LLF_TIE / 2), "no_study": c(-79.5), "no_site": c(-86.0)}) == "interior"
    assert NC.choose({"interior": c(-70.0, False), "no_study": c(-79.5), "no_site": c(-79.0)}) == "no_site"
    assert NC.choose({k: c(-1.0, False) for k in NC.CANDIDATES}) is None


def test_degenerate_data_fail_cleanly():
    """Constant log Rs: no candidate is usable, nothing raises, and every warning is recorded, not emitted."""
    import warnings
    site, study = np.array([0, 0, 0, 0, 1, 1, 1, 1]), np.array([0, 0, 1, 1, 2, 2, 3, 3])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fit = NC.fit_nested(np.full(8, 6.0), site, study, "lbfgs")
    assert fit["status"] == "failed" and caught == []
    assert all(not c["usable"] for c in fit["candidates"].values())
    assert any(c["warnings"] for c in fit["candidates"].values())


def test_unidentified_and_too_few_sites_are_not_fitted():
    y, site, study = simulate(2, 20, (0.3, 0.1, 0.05), studies=(1, 2))           # one study per site
    assert NC.fit_nested(y, site, study, "lbfgs")["status"] == "unidentified"
    y, site, study = simulate(2, 20, (0.3, 0.1, 0.05), records=(1, 2))           # one record per study
    assert NC.fit_nested(y, site, study, "lbfgs")["status"] == "unidentified"
    y, site, study = simulate(2, 1, (0.3, 0.1, 0.05), studies=(3, 4))
    assert NC.fit_nested(y, site, study, "lbfgs")["status"] == "too_few_sites"


# ---------------------------------------------------------------- ceilings and pairs

def test_ceiling_formulas_on_a_hand_computed_case():
    """Sites: a singleton; 4 records in 2 studies of 1 and 3 records; 4 records in one study."""
    out = NC.ceilings(0.3, 0.1, 0.05, n_rec=np.array([1, 4, 4]), n_study=np.array([1, 2, 1]),
                      w2=np.array([1.0, (1 / 4) ** 2 + (3 / 4) ** 2, 1.0]))
    assert out["total"] == pytest.approx(0.45)
    assert out["ceiling_independent_study"] == pytest.approx(0.3 / 0.45)
    assert out["ceiling_same_study"] == pytest.approx(0.4 / 0.45)
    # v = 0.1 + 0.05; 0.1 * 10/16 + 0.05/4; 0.1 + 0.05/4  -> mean 0.1125
    assert out["mean_noise_site_mean"] == pytest.approx(0.1125)
    assert out["ceiling_site_mean"] == pytest.approx(0.3 / (0.3 + 0.1125))
    # the brief's formula: 0.1/1 + 0.05; 0.1/2 + 0.05/4; 0.1/1 + 0.05/4 -> mean 0.325/3
    assert out["ceiling_site_mean_equal_study_weights"] == pytest.approx(0.3 / (0.3 + 0.325 / 3))
    assert out["share_site"] + out["share_study"] + out["share_record"] == pytest.approx(1.0)


def test_site_mean_noise_formula_matches_simulation():
    """v_i = s2_study * sum_j (m_ij/n_i)^2 + s2_record/n_i is the variance of a site mean around its site effect."""
    rng = np.random.default_rng(0)
    m = np.array([1, 3])                                                   # studies of 1 and 3 records
    b = rng.normal(0, np.sqrt(0.1), (200_000, 2))
    e = rng.normal(0, np.sqrt(0.05), (200_000, 4))
    means = (b[:, 0] + e[:, 0] + 3 * b[:, 1] + e[:, 1:].sum(1)) / 4
    v = NC.ceilings(0.3, 0.1, 0.05, np.array([4]), np.array([2]), np.array([((m / 4) ** 2).sum()]))
    assert np.var(means) == pytest.approx(v["mean_noise_site_mean"], rel=0.01)


def tiny_group() -> NC.Group:
    r = pd.DataFrame({"site_id": ["s1", "s1", "s1", "s2", "s2", "s3"], "study": ["a", "a", "b", "c", "c", "d"],
                      "rec_id": list("uvwxyz"), "log_rs": [1.0, 2.0, 4.0, 5.0, 5.5, 3.0],
                      "src": "srdb", "Study_number": [1.0, 1.0, 2.0, 3.0, 3.0, 4.0]})
    st = pd.DataFrame({"site_id": ["s1", "s2", "s3"], "n_rec": [3, 2, 1], "log_rs": [7 / 3, 5.25, 3.0]})
    return NC.make_group("g", r, st)


def test_pair_sums_on_a_hand_computed_case():
    g = tiny_group()
    # s1: same-study pair (1, 2): 0.5; different-study (1, 4), (2, 4): 4.5 + 2.0
    assert g.pair_same[0].tolist() == [0.5, 1.0] and g.pair_diff[0].tolist() == [6.5, 2.0]
    assert g.pair_same[1].tolist() == [0.125, 1.0] and g.pair_diff[1].tolist() == [0.0, 0.0]
    assert g.pair_same[2].tolist() == [0.0, 0.0] and g.pair_diff[2].tolist() == [0.0, 0.0]
    p = NC.pair_stats(g, np.array([1, 1, 1]))
    assert p["pairs_same_study"] == pytest.approx(0.625 / 2) and p["pairs_diff_study"] == pytest.approx(6.5 / 2)
    p = NC.pair_stats(g, np.array([0, 2, 1]))                    # s1 not drawn, s2 drawn twice
    assert p["pairs_same_study"] == pytest.approx(0.125) and np.isnan(p["pairs_diff_study"])
    assert g.n_rec.tolist() == [3, 2, 1] and g.n_study.tolist() == [2, 1, 1]
    assert g.w2.tolist() == pytest.approx([(2 / 3) ** 2 + (1 / 3) ** 2, 1.0, 1.0])


def test_cluster_bootstrap_relabels_duplicated_sites_and_their_studies():
    g = tiny_group()
    y, site, study = NC.replicate(g, np.array([0, 0, 1, 2]), min_records=2)       # s1 twice; s3 below the minimum
    assert y.tolist() == [1.0, 2.0, 4.0, 1.0, 2.0, 4.0, 5.0, 5.5]
    assert site.tolist() == [0, 0, 0, 1, 1, 1, 2, 2]                            # the copies are distinct sites
    assert study.tolist() == [0, 0, 1, 2, 2, 3, 4, 4]                           # ... with distinct studies
    n = NC.identification(site, study)
    assert n == {"sites": 3, "studies": 5, "records": 8, "sites_2plus_studies": 2, "studies_2plus_records": 3}


def test_draws_are_within_continent_and_pooled_is_their_union(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=settings)
    s = NC.Settings.from_cfg(sand)
    r, st = synth_tables()
    rr, sst, _ = NC.prepare(r, st, s)
    groups = NC.build_groups(rr, sst, s.continents)
    off = np.cumsum([0] + [len(groups[c].site_ids) for c in CONTINENTS])
    for d in NC.draws(groups, s):
        for i, c in enumerate(CONTINENTS):
            assert len(d[c]) == len(groups[c].site_ids) and d[c].min() >= 0 and d[c].max() < len(groups[c].site_ids)
            assert np.array_equal(groups[NC.POOLED].site_ids[off[i] + d[c]], groups[c].site_ids[d[c]])
        assert np.array_equal(d[NC.POOLED], np.concatenate([off[i] + d[c] for i, c in enumerate(CONTINENTS)]))


def test_study_ids_nest_srdb_studies_in_sites_and_make_each_cosore_record_a_study():
    r = pd.DataFrame({"rec_id": ["srdb_1", "srdb_2", "dX"], "src": ["srdb", "srdb", "cosore"],
                      "Study_number": [12.0, 12.0, np.nan], "site_id": ["a", "b", "a"]})
    assert NC.study_ids(r, "site_id").tolist() == ["a_12", "b_12", "cosore_dX"]
    with pytest.raises(ValueError, match="no Study_number"):
        NC.study_ids(r.assign(Study_number=np.nan), "site_id")


def test_summarise_boot_counts_outcomes_and_uses_defined_replicates_only():
    stats = dict.fromkeys(NC.FIT_STATS + NC.PAIR_STATS, np.nan)
    reps = [{"stats": {**stats, "s2_site": v}, "status": "ok", "chosen": "interior", "boundary": False, "dropped": []}
            for v in (0.1, 0.2, 0.3, 0.4)]
    reps.append({"stats": stats, "status": "unidentified", "chosen": None, "boundary": False, "dropped": []})
    reps.append({"stats": stats, "status": "failed", "chosen": None, "boundary": False, "dropped": list(NC.CANDIDATES)})
    reps[0].update(chosen="no_study", boundary=True)
    ci, counts = NC.summarise_boot(reps, (0.0, 1.0))
    assert ci["s2_site"] == {"ci": [0.1, 0.4], "n_boot_used": 4} and ci["s2_study"] == {"ci": None, "n_boot_used": 0}
    assert counts["n"] == 6 and counts["ok"] == 4 and counts["unidentified"] == 1 and counts["failed"] == 1
    assert counts["boundary"] == 1 and counts["kept_candidate"] == {"interior": 3, "no_study": 1, "no_site": 0}
    assert counts["dropped_candidate"] == {k: 1 for k in NC.CANDIDATES}


# ---------------------------------------------------------------- the stage

def test_stage_result(staged):
    sand, r, st, summary, _raw, res = staged
    assert res["exploratory"] is True and res["method"] and res["variant"] == "qc"
    assert res["settings"]["continent_column"] == "continent_geo"
    assert set(res["groups"]) == set(CONTINENTS) | {NC.POOLED}
    assert res["data"]["sites_outside_continents"]["n"] == 1                         # the Antarctic site
    assert res["data"]["cosore_records"] == int(((r.src == "cosore") & ~r.site_id_qc.isin(
        st[st.continent_geo == "Antarctica"].site_id)).sum())
    for c, n in SITES.items():
        g = res["groups"][c]
        assert g["n"]["sites"] == n and g["supplementary"] == (n < sand["phase2"]["min_test_sites"])
        assert g["n"]["sites_fit"] == int((st[st.continent_geo == c].n_rec >= 2).sum())
        assert g["fit"]["status"] == "ok" and g["bootstrap"]["n"] == 6
        for k in ("independent_study", "same_study", "site_mean"):
            assert 0 <= g["ceilings"][k]["estimate"] <= 1
    assert res["groups"]["Asia"]["n"]["srdb_studies_at_2plus_sites"] == 1
    pooled = res["groups"][NC.POOLED]
    assert pooled["n"]["sites"] == sum(SITES.values())
    assert pooled["n"]["records"] == sum(res["groups"][c]["n"]["records"] for c in CONTINENTS)
    assert set(res["_outputs"]) == {"figures:phase2/noise_ceiling.png", "figures:phase2/noise_ceiling.pdf"}
    assert list(res["_inputs"]) == ["build_sites_analysis.json"]
    assert summary["groups"]["Asia"]["site_mean"] == res["groups"]["Asia"]["ceilings"]["site_mean"]["estimate"]


def test_stage_estimates_follow_the_records(staged):
    """The stage's point estimates are those of fit_nested on the continent's sites with >= 2 records, and its pair
    statistics are N3's (brute force over the records)."""
    sand, r, st, _summary, _raw, res = staged
    sst = st[st.continent_geo == "Europe"]
    rr = r[r.site_id_qc.isin(sst.site_id)].assign(site_id=lambda x: x.site_id_qc)
    rr["study"] = NC.study_ids(rr, "site_id")
    rr = rr.sort_values(["site_id", "study", "rec_id"])
    fit_rr = rr[rr.groupby("site_id").log_rs.transform("size") >= 2]
    site = pd.factorize(fit_rr.site_id)[0]
    study = pd.factorize(fit_rr.site_id + "|" + fit_rr.study)[0]
    fit = NC.fit_nested(fit_rr.log_rs.to_numpy(), site, study, "lbfgs")
    comp = res["groups"]["Europe"]["components"]
    assert comp["s2_site"]["estimate"] == fit["s2_site"] and comp["s2_study"]["estimate"] == fit["s2_study"]
    same, diff = [], []
    for _sid, g in rr.groupby("site_id"):
        v, s_ = g.log_rs.to_numpy(), g.study.to_numpy()
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                (same if s_[i] == s_[j] else diff).append(0.5 * (v[i] - v[j]) ** 2)
    pairs = res["groups"]["Europe"]["pairs"]
    assert pairs["same_study"]["semivariance"]["estimate"] == pytest.approx(np.mean(same), rel=1e-12)
    assert pairs["diff_study"]["semivariance"]["estimate"] == pytest.approx(np.mean(diff), rel=1e-12)
    assert pairs["same_study"]["n_pairs"] == len(same) and pairs["diff_study"]["n_pairs"] == len(diff)


def test_stage_is_deterministic(staged):
    sand, _r, _st, _summary, raw, _res = staged
    NC.noise_ceiling(sand)
    assert sand.path("results", NC.RESULT).read_bytes() == raw


def test_processes_give_the_same_result(staged, cfg, tmp_path):
    _sand, r, st, _summary, raw, _res = staged
    sand2 = sandbox(cfg, tmp_path, edit=lambda d: settings(d, n_jobs=2))
    record_build(sand2, r, st)
    NC.noise_ceiling(sand2)
    a, b = json.loads(raw), json.loads(sand2.path("results", NC.RESULT).read_bytes())
    for k in ("_provenance", "_inputs"):     # config hashes (here and in the upstream result) differ in n_jobs only
        a.pop(k), b.pop(k)
    assert a == b


def test_refuses_a_changed_records_table(staged, cfg, tmp_path):
    _sand, r, st, *_ = staged
    sand = sandbox(cfg, tmp_path, edit=settings)
    paths = record_build(sand, r, st)
    write_table(r.assign(log_rs=r.log_rs + 0.1), paths[0])          # changed after build_sites_analysis recorded it
    with pytest.raises(StaleInputError, match="changed after the run"):
        NC.noise_ceiling(sand)
    assert not sand.path("results", NC.RESULT).exists()


def test_refuses_records_that_do_not_match_the_site_table(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=settings)
    r, st = synth_tables()
    record_build(sand, r, st.assign(n_rec=np.where(st.index == 0, st.n_rec + 1, st.n_rec)))
    with pytest.raises(ValueError, match="record count or mean log Rs"):
        NC.noise_ceiling(sand)


def test_records_of_sites_missing_from_the_site_table_are_left_out_and_counted(cfg, tmp_path):
    """As in a smoke run, whose site tables are a subset while the records table is not."""
    sand = sandbox(cfg, tmp_path, edit=lambda d: settings(d, n_boot=2))
    r, st = synth_tables()
    keep = st[st.continent_geo != "Oceania"]
    record_build(sand, r, keep)
    NC.noise_ceiling(sand)
    res = json.loads(sand.path("results", NC.RESULT).read_text())
    assert res["data"]["records_of_sites_not_in_site_table"] == int((~r.site_id_qc.isin(keep.site_id)).sum())
    assert res["groups"]["Oceania"]["n"]["sites"] == 0 and res["groups"]["Oceania"]["fit"]["status"] == "too_few_sites"
    assert res["groups"]["Oceania"]["bootstrap"]["too_few_sites"] == 2


def test_config_must_name_the_optimizer(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=lambda d: (settings(d), d["phase2"]["noise_ceiling"].pop("optimizer")))
    with pytest.raises(KeyError, match="optimizer"):
        NC.Settings.from_cfg(sand)


def test_figure_written(staged):
    sand, *_ = staged
    for suffix in ("png", "pdf"):
        p = sand.path("figures", "phase2", f"noise_ceiling.{suffix}")
        assert p.is_file() and p.stat().st_size > 1000
