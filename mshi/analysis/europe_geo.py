"""Declared post-hoc sensitivity analysis of the locked test on geographic Europe (the author's decision Q-5 of
2026-11-03; docs/DECISIONS.md D-C1-5 and D-P2-4). The locked result stays primary.

The locked test set is "Europe" by the country rule (the continent of the Natural Earth country polygon), which
puts French Guiana and the Canary Islands in Europe (F-H1). Here the locked model, i.e. the model the locked
result selected, refit on the same Asia training sites by the locked code (``LockedTest``, which verifies the
lock first), is scored on the locked Europe test sites whose geographic continent (``mshi.geo``: overseas
territories by location) is Europe, with the locked metrics and the same site bootstrap. Training data, model
and selection rule are not changed (ground rule 4); only the test set is restricted.

Control: the same computation on the full locked Europe test set must give the locked result's primary metrics
(``clean_test.deviation_atol``); otherwise the stage fails and reports nothing else.
The author's reference, computed outside the pipeline, is compared with the pipeline's value (config
``europe_geo_sensitivity.author_reference``); a difference is reported, not tuned away.
"""
from __future__ import annotations

import numpy as np

from ..config import Config
from ..geo import geographic_continent, subunits
from ..io import read_json, read_table, require_outputs, write_result
from .clean_test import LockedTest

PRIMARY_KEYS = ("n", "r2", "rmse_rs", "mae_rs", "rmse_rs_intercept", "bias_log", "spearman")


class ControlMismatch(RuntimeError):
    """The full locked test set did not reproduce the locked primary metrics; nothing else is reported."""


def _max_diff(a: dict, b: dict) -> float:
    d = [abs(a[k] - b[k]) for k in PRIMARY_KEYS]
    d += [abs(x - y) for k in ("ci_site", "ci_block2") for x, y in zip(a[k], b[k])]
    return float(max(d))


def europe_geo_sensitivity(cfg: Config) -> dict:
    s = cfg["europe_geo_sensitivity"]
    lt = LockedTest(cfg)                                   # verifies the lock (plan, locked block, results)
    L, T = lt.L, lt.T
    fp = cfg.path("interim", "features_v3_qc.parquet")
    require_outputs(cfg, "features.json", [fp])
    locked = read_json(cfg.repo_path(cfg["clean_test"]["locked_results"]["qc"]["file"]))   # hash-verified above
    best = locked["selected"]
    d = read_table(cfg, fp)
    geo = geographic_continent(cfg, d.lon.values, d.lat.values, subunits(cfg))
    d = d.assign(continent_geo=geo.continent_geo.values, geo_subunit=geo.geo_subunit.values)
    train_all = d[d.continent == L["train_continent"]]
    test_all = d[d.continent == L["test_continent"]]

    a, e, _f, _m, p = lt.score(train_all, test_all, best["set"], best["learner"])
    full = lt.metrics(e[T].values, p, e.lon.values, e.lat.values, np.full(len(e), a[T].mean()))
    diff = _max_diff(full, locked["primary"])
    if diff > cfg["clean_test"]["deviation_atol"]:
        raise ControlMismatch(f"full locked Europe set: max |diff| {diff:.3g} from the locked primary metrics; "
                              "the sensitivity analysis is not reported")

    keep = test_all.continent_geo.eq(s["test_continent_geo"])
    a2, e2, _f2, _m2, p2 = lt.score(train_all, test_all[keep], best["set"], best["learner"])
    geo_m = lt.metrics(e2[T].values, p2, e2.lon.values, e2.lat.values, np.full(len(e2), a2[T].mean()))
    scored = set(e.site_id)
    excluded = test_all[~keep].sort_values("site_id")
    ref, tol = s["author_reference"], s["reference_tolerance"]
    vs_ref = {"n_equal": geo_m["n"] == ref["n"], "r2_diff": geo_m["r2"] - ref["r2"],
              "ci_site_diff": [x - y for x, y in zip(geo_m["ci_site"], ref["ci_site"])]}
    vs_ref["matches"] = bool(vs_ref["n_equal"] and abs(vs_ref["r2_diff"]) <= tol["r2"]
                             and all(abs(x) <= tol["ci"] for x in vs_ref["ci_site_diff"]))
    res = {"exploratory": True, "declared_post_hoc_sensitivity": True,     # not planned before scoring (rule 3)
           "approved": s["approved"], "primary_result": "the locked result (docs/handoff/results/clean_test_europe.json)",
           "method": ("locked model (selected by the locked rule; refit on the same Asia sites by LockedTest), scored "
                      "on the locked Europe test sites whose geographic continent is Europe; locked metrics and "
                      "site bootstrap; control: the full set reproduces the locked primary metrics"),
           "selected": {"set": best["set"], "learner": best["learner"]},
           "control_full_locked_set": {"n": full["n"], "r2": full["r2"], "max_abs_diff_vs_locked": diff},
           "geographic_europe": geo_m,
           "n_locked_test_sites": int(len(test_all)), "n_scored_locked": int(len(e)),
           "excluded": [{"site_id": r.site_id, "lat": round(float(r.lat), 4), "lon": round(float(r.lon), 4),
                         "country": r.country, "geo_subunit": r.geo_subunit, "continent_geo": r.continent_geo,
                         "was_scored": r.site_id in scored} for r in excluded.itertuples()],
           "author_reference": ref, "vs_author_reference": vs_ref}
    write_result(cfg, res, "europe_geo_sensitivity.json", inputs=["features.json"])
    return {"n": geo_m["n"], "r2": geo_m["r2"], "ci_site": geo_m["ci_site"], "matches_reference": vs_ref["matches"]}
