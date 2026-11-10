"""27_a2_ceiling.py - Analysis 2: a ceiling on explainable variance.

Question: what is the largest R2 that any model built on gridded predictors (constant within a
0.05-degree cell) could reach on this data, and how does observed skill compare with it?

1. One-way random-effects decomposition of record-level log Rs in cells with >= 2 records
   (ANOVA / method-of-moments estimator for unbalanced data; REML via statsmodels as a check).
   95% intervals: 2000 bootstrap resamples of cells (seed 42).
2. Within-cell part split by record-pair type: same study & same year (plot-scale heterogeneity +
   measurement error), same study & different years (+ interannual variation), different studies
   (+ between-study method differences), the last split by same/different year. "Same year" = the two
   12-month windows overlap (|delta Study_midyear| <= 0.5; SRDB codes calendar year X as X.5 and
   Jul X-1..Jun X as X.0); pairs with a missing year form their own class. Sensitivities: exact
   mid-year equality (first run), excluding multi-year means. Statistic: mean of (y_i - y_j)^2 / 2
   over pairs, averaging within cell first (each cell weighted equally); pair-weighted version also
   reported. Bootstrap over cells.
   Nested model (primary noise model B2): same-study pairs estimate s2_rec, different-study pairs
   s2_study + s2_rec (moments; REML with statsmodels as a check).
3. Semivariogram of site-level log Rs (cell means) per large continent: great-circle lags, bins
   0-10-25-50-100-200-400-800-1600-3200 km, pair counts, first-bin semivariance / sill, and a weighted
   least-squares exponential model with nugget (Cressie weights N_h / gamma_h^2).
4. Upper bound on R2 for a predictor constant within a cell:
     B1 (one-way, records exchangeable): 1 - s2_within * mean(1/n_i) / Var(site means)
     B2 (nested, primary): 1 - mean_i[s2_study * sum_j (n_ij/n_i)^2 + s2_rec / n_i] / Var(site means)
     B3 (short-range): 1 - semivariance(0-10 km) / Var(site means)
   Intervals are percentiles of the bound itself: conditional on the scope's sites (component
   replicates only) and with the scope's sites resampled (the same seed-42 resamples as the A1 R2
   intervals), which matters for small continents.
   Sensitivity: pooled (ANOVA, cells weighted by n_i - 1) vs equal cell weights; cells with >= 3
   records; by continent; excluding COSORE; excluding exact-duplicate values across studies.
   Semivariogram bound: 1 - nugget / sill.
5. Analysis 1 R2 values as a fraction of the bound for the test continent's sites.
6. Within-cell variance by measurement method (IRGA vs alkali absorption / soda lime vs gas
   chromatography, and cross-method pairs) and by ecosystem type. COSORE multi-chamber port-years give
   an independent estimate of plot-scale variance within a site-year.

Usage: python -I audit/27_a2_ceiling.py
Outputs (audit/outputs/a2/): a2_results.json, pair_components_<v>.csv, semivariogram_<v>.csv,
  bounds_<v>.csv, fraction_of_bound_<v>.csv, method_ecosystem_<v>.csv
"""
from __future__ import annotations

import itertools
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

warnings.filterwarnings("ignore")
OUTD = C.OUT / "a2"
OUTD.mkdir(parents=True, exist_ok=True)
BINS = [0, 10, 25, 50, 100, 200, 400, 800, 1600, 3200]
LARGE = ["Asia", "North America", "Europe"]


def anova_components(y, g):
    """Unbalanced one-way random effects, method of moments. y values, g group labels."""
    df = pd.DataFrame({"y": y, "g": g})
    st = df.groupby("g")["y"].agg(["size", "mean", "var"])
    st = st[st["size"] >= 2]
    df = df[df["g"].isin(st.index)]
    N, k = len(df), len(st)
    if k < 3:
        return dict(s2_within=np.nan, s2_between=np.nan, share_within=np.nan, n_cells=k, n_records=N)
    gm = df["y"].mean()
    ssw = float(((st["size"] - 1) * st["var"]).sum())
    ssb = float((st["size"] * (st["mean"] - gm) ** 2).sum())
    msw, msb = ssw / (N - k), ssb / (k - 1)
    n0 = (N - (st["size"] ** 2).sum() / N) / (k - 1)
    s2a = max((msb - msw) / n0, 0.0)
    return dict(s2_within=msw, s2_between=s2a, share_within=msw / (msw + s2a) if (msw + s2a) > 0 else np.nan,
                n_cells=k, n_records=N, s2_within_equal_cells=float(st["var"].mean()))


def boot_cells(rec, fn, n_boot=C.N_BOOT, seed=C.SEED):
    """Bootstrap over cells: resample cells with replacement, relabel duplicates as new cells."""
    cells = rec["cell"].unique()
    grp = {c: idx for c, idx in rec.groupby("cell").indices.items()}
    rng = np.random.default_rng(seed)
    out = []
    y = rec["log_rs"].values
    for _ in range(n_boot):
        pick = rng.choice(cells, size=len(cells), replace=True)
        idx = np.concatenate([grp[c] for c in pick])
        lab = np.concatenate([np.full(len(grp[c]), j) for j, c in enumerate(pick)])
        out.append(fn(y[idx], lab))
    return out


def reml_check(rec):
    import statsmodels.formula.api as smf
    try:
        m = smf.mixedlm("log_rs ~ 1", rec, groups=rec["cell"]).fit(reml=True)
        s2a = float(m.cov_re.iloc[0, 0])
        s2e = float(m.scale)
        return {"s2_within": s2e, "s2_between": s2a, "share_within": s2e / (s2a + s2e)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def pairs_table(rec):
    """All within-cell record pairs with type labels and half squared differences.
    Same year = both mid-years known and |delta mid-year| <= 0.5, i.e. the two 12-month windows overlap
    (SRDB convention: calendar year X = X.5, Jul X-1 to Jun X = X.0). Pairs with a missing year get
    their own 'year_unknown' type. `same_year_exact` keeps the first-run definition (equal mid-year)
    and `multi_year` marks pairs involving a multi-year mean (YearsOfData > 1), both for sensitivity."""
    rows = []
    for cell, g in rec.groupby("cell"):
        if len(g) < 2:
            continue
        v = g[["log_rs", "study_id", "year", "meas_method", "ecosystem", "source", "rs_annual",
               "years_of_data"]].values
        for a, b in itertools.combinations(range(len(v)), 2):
            ya, sa, ta, ma, ea, soa, ra, da = v[a]
            yb, sb, tb, mb, eb, sob, rb, db = v[b]
            same_study = sa == sb
            known = pd.notna(ta) and pd.notna(tb)
            same_year = known and abs(float(ta) - float(tb)) <= 0.5
            same_year_exact = known and ta == tb
            pre = "same_study_" if same_study else "diff_study_"
            ptype = pre + ("year_unknown" if not known else ("same_year" if same_year else "diff_year"))
            ptype_exact = pre + ("year_unknown" if not known else ("same_year" if same_year_exact else "diff_year"))
            multi = (pd.notna(da) and float(da) > 1) or (pd.notna(db) and float(db) > 1)
            rows.append({"cell": cell, "ptype": ptype, "ptype_exact": ptype_exact, "hsd": 0.5 * (ya - yb) ** 2,
                         "same_study": same_study, "same_year": same_year, "year_known": known,
                         "multi_year": multi, "m_a": ma, "m_b": mb, "e_a": ea, "e_b": eb,
                         "cosore": (soa == "cosore") or (sob == "cosore"),
                         "exact_dup": (not same_study) and abs(ra - rb) < 1e-9})
    return pd.DataFrame(rows)


def comp_stat(pt: pd.DataFrame, mask, weight="cell"):
    p = pt[mask]
    if p.empty:
        return np.nan, 0, 0
    if weight == "cell":
        val = p.groupby("cell")["hsd"].mean().mean()
    else:
        val = p["hsd"].mean()
    return float(val), int(len(p)), int(p["cell"].nunique())


def boot_comp(pt: pd.DataFrame, mask, n_boot=C.N_BOOT, seed=C.SEED):
    p = pt[mask]
    if p["cell"].nunique() < 5:
        return np.nan, np.nan
    cm = p.groupby("cell")["hsd"].mean().values
    rng = np.random.default_rng(seed)
    bs = [cm[rng.integers(0, len(cm), len(cm))].mean() for _ in range(n_boot)]
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def semivariogram(sites: pd.DataFrame):
    lat, lon, z = sites["lat"].values, sites["lon"].values, sites["log_rs"].values
    n = len(z)
    i, j = np.triu_indices(n, k=1)
    dkm = C.haversine_km(lat[i], lon[i], lat[j], lon[j])
    sv = 0.5 * (z[i] - z[j]) ** 2
    rows = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (dkm >= lo) & (dkm < hi)
        rows.append({"lag_lo_km": lo, "lag_hi_km": hi, "n_pairs": int(m.sum()),
                     "mean_lag_km": float(dkm[m].mean()) if m.any() else np.nan,
                     "gamma": float(sv[m].mean()) if m.any() else np.nan})
    tab = pd.DataFrame(rows)
    var = float(np.var(z, ddof=1))
    fit = fit_exponential(tab)
    return tab, var, fit


def fit_exponential(tab, max_lag_km=1600.0, max_range_km=5000.0):
    """Exponential model with nugget, WLS with Cressie weights, fitted to bins with >= 30 pairs and
    upper lag <= 1600 km (beyond that the continental-scale trend makes the field non-stationary).
    Range parameter bounded to <= 5000 km. Reported as supplementary; the primary short-range
    statistic is the empirical first-bin semivariance."""
    from scipy.optimize import least_squares
    t = tab[(tab["n_pairs"] >= 30) & tab["gamma"].notna() & (tab["lag_hi_km"] <= max_lag_km)]
    if len(t) < 4:
        return {}
    h, g, w = t["mean_lag_km"].values, t["gamma"].values, t["n_pairs"].values

    def model(p, h):
        c0, c1, a = p
        return c0 + c1 * (1 - np.exp(-h / a))

    def resid(p):
        m = model(p, h)
        return np.sqrt(w) * (g - m) / np.maximum(m, 1e-6)

    best = None
    for a0 in (50, 200, 800, 2000):
        r = least_squares(resid, x0=[g[0] * 0.8, max(g.max() - g[0], 0.01), a0],
                          bounds=([0, 0, 1], [5, 5, max_range_km]))
        if best is None or r.cost < best.cost:
            best = r
    c0, c1, a = best.x
    return {"nugget": float(c0), "partial_sill": float(c1), "range_par_km": float(a),
            "practical_range_km": float(3 * a), "sill": float(c0 + c1), "nugget_share": float(c0 / (c0 + c1)),
            "range_at_bound": bool(a >= max_range_km * 0.999), "fit_max_lag_km": max_lag_km}


def boot_first_bin(sites, max_km=10.0, n_boot=C.N_BOOT, seed=C.SEED):
    """Short-lag semivariance gamma(0-max_km) / Var(sites) with a bootstrap over sites (pairs among
    resampled sites; duplicated sites contribute zero-distance self pairs, which are dropped)."""
    lat, lon, z = sites["lat"].values, sites["lon"].values, sites["log_rs"].values
    n = len(z)
    i, j = np.triu_indices(n, k=1)
    d = C.haversine_km(lat[i], lon[i], lat[j], lon[j])
    m = d < max_km
    pi, pj = i[m], j[m]
    est = float(np.mean(0.5 * (z[pi] - z[pj]) ** 2) / np.var(z, ddof=1)) if m.any() else np.nan
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        w = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        ww = w[pi] * w[pj]
        if ww.sum() == 0:
            continue
        g = np.sum(ww * 0.5 * (z[pi] - z[pj]) ** 2) / ww.sum()
        mu = np.sum(w * z) / w.sum()
        var = np.sum(w * (z - mu) ** 2) / (w.sum() - 1)
        bs.append(g / var)
    return est, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), int(m.sum())


def nested_components(pt: pd.DataFrame, same_cells_only=False):
    """Method of moments for y = mu_cell + s_study(cell) + e. Same-study pairs estimate s2_rec;
    different-study pairs estimate s2_study + s2_rec. Cell-weighted means."""
    ss = pt[pt["same_study"]]
    ds = pt[~pt["same_study"]]
    if same_cells_only:
        both = set(ss["cell"]) & set(ds["cell"])
        ss, ds = ss[ss["cell"].isin(both)], ds[ds["cell"].isin(both)]
    if ss.empty or ds.empty:
        return np.nan, np.nan
    s2_rec = ss.groupby("cell")["hsd"].mean().mean()
    s2_sr = ds.groupby("cell")["hsd"].mean().mean()
    return float(s2_rec), float(max(s2_sr - s2_rec, 0.0))


def boot_nested(pt: pd.DataFrame, n_boot=C.N_BOOT, seed=C.SEED, same_cells_only=False):
    cells = pt["cell"].unique()
    idx = pt.groupby("cell").indices
    rng = np.random.default_rng(seed)
    out = []
    hsd, same, cell = pt["hsd"].values, pt["same_study"].values, pt["cell"].values
    for _ in range(n_boot):
        pick = rng.choice(cells, len(cells), replace=True)
        ii = np.concatenate([idx[c] for c in pick])
        lab = np.concatenate([np.full(len(idx[c]), k) for k, c in enumerate(pick)])
        sub = pd.DataFrame({"cell": lab, "hsd": hsd[ii], "same_study": same[ii]})
        out.append(nested_components(sub, same_cells_only))
    return np.array(out)


def site_noise_nested(rec: pd.DataFrame, s2_study: float, s2_rec: float) -> pd.Series:
    """Var(site mean - true cell mean) = s2_study * sum_j (n_ij/n_i)^2 + s2_rec / n_i."""
    cnt = rec.groupby(["cell", "study_id"]).size().rename("nij").reset_index()
    ni = cnt.groupby("cell")["nij"].transform("sum")
    cnt["w2"] = (cnt["nij"] / ni) ** 2
    agg = cnt.groupby("cell").agg(sum_w2=("w2", "sum"), n=("nij", "sum"))
    return s2_study * agg["sum_w2"] + s2_rec / agg["n"]


def reml_nested(rec):
    import statsmodels.formula.api as smf
    try:
        # string column -> patsy treats it as categorical; avoid C() because the module alias C
        # (mshi_common) shadows patsy's C() in the formula namespace
        rec = rec.assign(study_cat=rec["study_id"].astype(str))
        m = smf.mixedlm("log_rs ~ 1", rec, groups=rec["cell"], re_formula="1",
                        vc_formula={"study": "0 + study_cat"}).fit(reml=True)
        return {"s2_cell": float(m.cov_re.iloc[0, 0]), "s2_study": float(m.vcomp[0]), "s2_rec": float(m.scale)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def bound_sites(s2w, sites):
    var = float(sites["log_rs"].var(ddof=1))
    inv_n = float((1.0 / sites["n_records"]).mean())
    return 1.0 - s2w * inv_n / var, var, inv_n


def main() -> int:
    rec_all = pd.read_csv(C.OUT / "clean_records.csv", low_memory=False)
    ix, iy = C.cell_index(rec_all["lat"].values, rec_all["lon"].values)
    rec_all["cell"] = ix.astype(np.int64) * 10000 + iy
    results = {"created": C.now_utc(), "versions": C.versions(), "variants": {}}
    for v in ["strict", "incl_missing"]:
        rec = rec_all[~rec_all["cov_missing"]] if v == "strict" else rec_all
        rec = rec.reset_index(drop=True)
        sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
        R = {}
        # ---- 1. variance components ----
        multi = rec[rec.groupby("cell")["cell"].transform("size") >= 2]
        comp = anova_components(multi["log_rs"].values, multi["cell"].values)
        bs = boot_cells(multi, lambda y, g: anova_components(y, g))
        for k in ["s2_within", "s2_between", "share_within"]:
            arr = np.array([b[k] for b in bs])
            comp[k + "_lo"], comp[k + "_hi"] = float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))
        comp["reml"] = reml_check(multi)
        comp["var_records_all"] = float(rec["log_rs"].var(ddof=1))
        comp["var_records_multi"] = float(multi["log_rs"].var(ddof=1))
        R["components"] = comp
        # sensitivity variants of the within-cell variance
        sens = {}
        m3 = rec[rec.groupby("cell")["cell"].transform("size") >= 3]
        sens["cells_3plus"] = anova_components(m3["log_rs"].values, m3["cell"].values)
        nc = multi[multi["source"] != "cosore"]
        sens["no_cosore"] = anova_components(nc["log_rs"].values, nc["cell"].values)
        for c in LARGE + ["South & Central America"]:
            mc = multi[multi["continent"] == c]
            sens[f"continent_{c}"] = anova_components(mc["log_rs"].values, mc["cell"].values)
        R["components_sensitivity"] = sens
        # ---- 2. pair components ----
        pt = pairs_table(multi)
        pt.to_csv(OUTD / f"pairs_{v}.csv.gz", index=False, compression="gzip")
        prow = []
        masks = {
            "all_pairs": np.ones(len(pt), bool),
            "same_study_same_year": pt["ptype"] == "same_study_same_year",
            "same_study_diff_year": pt["ptype"] == "same_study_diff_year",
            "diff_study_any_year": ~pt["same_study"],
            "diff_study_same_year": pt["ptype"] == "diff_study_same_year",
            "diff_study_diff_year": pt["ptype"] == "diff_study_diff_year",
            "year_unknown_any_study": ~pt["year_known"],
            "diff_study_excl_exact_dups": (~pt["same_study"]) & (~pt["exact_dup"]),
            "all_pairs_no_cosore": ~pt["cosore"],
            "sens_exact_year: same_study_same_year": pt["ptype_exact"] == "same_study_same_year",
            "sens_exact_year: same_study_diff_year": pt["ptype_exact"] == "same_study_diff_year",
            "sens_exact_year: diff_study_same_year": pt["ptype_exact"] == "diff_study_same_year",
            "sens_exact_year: diff_study_diff_year": pt["ptype_exact"] == "diff_study_diff_year",
            "sens_no_multi_year: same_study_same_year": (pt["ptype"] == "same_study_same_year") & ~pt["multi_year"],
            "sens_no_multi_year: same_study_diff_year": (pt["ptype"] == "same_study_diff_year") & ~pt["multi_year"],
            "sens_no_multi_year: diff_study_any_year": (~pt["same_study"]) & ~pt["multi_year"],
        }
        for name, mk in masks.items():
            val, npairs, ncells = comp_stat(pt, mk, "cell")
            valp, _, _ = comp_stat(pt, mk, "pair")
            lo, hi = boot_comp(pt, mk)
            prow.append({"component": name, "half_sq_diff_cellw": val, "lo": lo, "hi": hi,
                         "half_sq_diff_pairw": valp, "n_pairs": npairs, "n_cells": ncells})
        pc = pd.DataFrame(prow)
        pc.to_csv(OUTD / f"pair_components_{v}.csv", index=False)
        R["pair_components"] = pc.to_dict("records")
        R["exact_duplicate_pairs_across_studies"] = int(pt["exact_dup"].sum())
        # ---- 6. method and ecosystem ----
        def mclass(m):
            if not isinstance(m, str):
                return "unknown"
            m = m.lower()
            if m in ("irga", "igra"):
                return "IRGA"
            if m in ("alkali absorption", "soda lime"):
                return "alkali/soda lime"
            if m.startswith("gas chromat"):
                return "GC"
            return "other"
        pt["mc_a"], pt["mc_b"] = pt["m_a"].map(mclass), pt["m_b"].map(mclass)
        mrow = []
        for lab, mk in {
            "IRGA-IRGA": (pt["mc_a"] == "IRGA") & (pt["mc_b"] == "IRGA"),
            "alkali/soda lime-alkali/soda lime": (pt["mc_a"] == "alkali/soda lime") & (pt["mc_b"] == "alkali/soda lime"),
            "GC-GC": (pt["mc_a"] == "GC") & (pt["mc_b"] == "GC"),
            "IRGA-alkali/soda lime": ((pt["mc_a"] == "IRGA") & (pt["mc_b"] == "alkali/soda lime")) | ((pt["mc_b"] == "IRGA") & (pt["mc_a"] == "alkali/soda lime")),
            "IRGA-GC": ((pt["mc_a"] == "IRGA") & (pt["mc_b"] == "GC")) | ((pt["mc_b"] == "IRGA") & (pt["mc_a"] == "GC")),
            "IRGA-IRGA diff study": (pt["mc_a"] == "IRGA") & (pt["mc_b"] == "IRGA") & ~pt["same_study"],
        }.items():
            val, npairs, ncells = comp_stat(pt, mk)
            lo, hi = boot_comp(pt, mk)
            mrow.append({"group": "method", "label": lab, "half_sq_diff_cellw": val, "lo": lo, "hi": hi,
                         "n_pairs": npairs, "n_cells": ncells})
        for eco in ["Forest", "Grassland", "Agriculture", "Shrubland", "Wetland", "Savanna", "Desert", "Tundra"]:
            mk = (pt["e_a"] == eco) & (pt["e_b"] == eco)
            val, npairs, ncells = comp_stat(pt, mk)
            lo, hi = boot_comp(pt, mk)
            mrow.append({"group": "ecosystem", "label": eco, "half_sq_diff_cellw": val, "lo": lo, "hi": hi,
                         "n_pairs": npairs, "n_cells": ncells})
        mk = pt["e_a"].notna() & pt["e_b"].notna() & (pt["e_a"] != pt["e_b"])
        val, npairs, ncells = comp_stat(pt, mk)
        lo, hi = boot_comp(pt, mk)
        mrow.append({"group": "ecosystem", "label": "mixed ecosystem types", "half_sq_diff_cellw": val, "lo": lo,
                     "hi": hi, "n_pairs": npairs, "n_cells": ncells})
        # method-specific ANOVA bounds where enough cells
        me = pd.DataFrame(mrow)
        me.to_csv(OUTD / f"method_ecosystem_{v}.csv", index=False)
        R["method_ecosystem"] = me.to_dict("records")
        # ---- 3. semivariograms (site level, per large continent) ----
        sv_rows, sv_sum = [], {}
        for c in LARGE + ["All"]:
            s = sites if c == "All" else sites[sites["continent"] == c]
            tab, var, fit = semivariogram(s)
            tab.insert(0, "continent", c)
            sv_rows.append(tab)
            est, lo, hi, npairs = boot_first_bin(s, 10.0)
            est25, lo25, hi25, npairs25 = boot_first_bin(s, 25.0)
            plateau = tab[(tab["lag_lo_km"] >= 400) & (tab["lag_hi_km"] <= 1600)]
            plateau_gamma = float(np.average(plateau["gamma"], weights=plateau["n_pairs"])) if len(plateau) else np.nan
            sv_sum[c] = {"n_sites": len(s), "variance": var, "fit_exp_le1600km": fit,
                         "gamma_0_10km_share": est, "gamma_0_10km_share_lo": lo, "gamma_0_10km_share_hi": hi,
                         "n_pairs_0_10km": npairs, "gamma_0_25km_share": est25, "gamma_0_25km_share_lo": lo25,
                         "gamma_0_25km_share_hi": hi25, "n_pairs_0_25km": npairs25,
                         "gamma_plateau_400_1600km": plateau_gamma,
                         "gamma_0_10km": float(tab.iloc[0]["gamma"])}
        pd.concat(sv_rows).to_csv(OUTD / f"semivariogram_{v}.csv", index=False)
        R["semivariogram"] = sv_sum
        # ---- nested study effects (primary noise model) ----
        s2_rec, s2_study = nested_components(pt)
        bn = boot_nested(pt)
        s2_rec_sc, s2_study_sc = nested_components(pt, same_cells_only=True)
        nested = {"s2_rec": s2_rec, "s2_rec_lo": float(np.nanpercentile(bn[:, 0], 2.5)),
                  "s2_rec_hi": float(np.nanpercentile(bn[:, 0], 97.5)), "s2_study": s2_study,
                  "s2_study_lo": float(np.nanpercentile(bn[:, 1], 2.5)), "s2_study_hi": float(np.nanpercentile(bn[:, 1], 97.5)),
                  "same_cells_only": {"s2_rec": s2_rec_sc, "s2_study": s2_study_sc,
                                      "n_cells": int(len(set(pt.loc[pt.same_study, 'cell']) & set(pt.loc[~pt.same_study, 'cell'])))},
                  "reml_nested": reml_nested(multi)}
        # pair-weighted (record-count weighting) version
        ssp, dsp = pt.loc[pt["same_study"], "hsd"].mean(), pt.loc[~pt["same_study"], "hsd"].mean()
        nested["pair_weighted"] = {"s2_rec": float(ssp), "s2_study": float(max(dsp - ssp, 0))}
        pt3 = pt[pt["cell"].isin(m3["cell"].unique())]
        nested["cells_3plus"] = dict(zip(["s2_rec", "s2_study"], nested_components(pt3)))
        ptn = pt[~pt["cosore"]]
        nested["no_cosore"] = dict(zip(["s2_rec", "s2_study"], nested_components(ptn)))
        for c in LARGE:
            ptc = pt[pt["cell"].isin(multi.loc[multi["continent"] == c, "cell"].unique())]
            nested[f"continent_{c}"] = dict(zip(["s2_rec", "s2_study"], nested_components(ptc)))
        R["nested"] = nested
        # ---- 4. bounds ----
        # Interval conventions (after independent review):
        #   lo/hi           conditional on the scope's sites: percentiles of the bound over the 2000
        #                   variance-component bootstrap replicates (cells resampled)
        #   lo_uncond/hi_*  also resampling the scope's sites (C.boot_idx, seed 42 = the resamples used
        #                   for the A1 R2 intervals), replicate b paired with component replicate b
        brow = []
        boot_one = np.array([b["s2_within"] for b in bs])
        comp_mats = {}  # per scope: (z, sum_w2, inv_n) aligned to the scope's site order

        def site_terms(r, s):
            cnt = r.groupby(["cell", "study_id"]).size().rename("nij").reset_index()
            ni = cnt.groupby("cell")["nij"].transform("sum")
            cnt["w2"] = (cnt["nij"] / ni) ** 2
            agg = cnt.groupby("cell").agg(sum_w2=("w2", "sum"), n=("nij", "sum")).reindex(s["cell"])
            return agg["sum_w2"].values, 1.0 / agg["n"].values

        def add_bound(scope, label, s, r, noise_sites, noise_rec, extra=None):
            var_s = float(s["log_rs"].var(ddof=1))
            row = {"scope": scope, "estimator": label, "n_sites": len(s), "var_sites": var_s,
                   "mean_noise_sites": float(noise_sites), "r2max_sites": 1 - noise_sites / var_s,
                   "n_records": len(r), "var_records": float(r["log_rs"].var(ddof=1)),
                   "r2max_records": 1 - noise_rec / float(r["log_rs"].var(ddof=1)) if noise_rec is not None else np.nan}
            if extra:
                row.update(extra)
            brow.append(row)

        for scope in ["All"] + C.CONTINENT_ORDER:
            s = sites if scope == "All" else sites[sites["continent"] == scope]
            r = rec if scope == "All" else rec[rec["continent"] == scope]
            if len(s) < 20:
                continue
            rr = r.copy()
            z = s["log_rs"].values
            var_s = float(np.var(z, ddof=1))
            sw2, inv_n = site_terms(rr, s)
            comp_mats[scope] = (s["cell"].values, z, sw2, inv_n)
            idx = C.boot_idx(len(s))
            zb = z[idx]
            var_b = zb.var(axis=1, ddof=1)
            # B1 pooled one-way ANOVA: records exchangeable within cell
            w = comp["s2_within"]
            b1_cond = 1 - boot_one * inv_n.mean() / var_s
            b1_unc = 1 - boot_one * inv_n[idx].mean(axis=1) / var_b
            add_bound(scope, "B1 pooled one-way (records exchangeable)", s, r, w * inv_n.mean(), w,
                      {"lo": np.nanpercentile(b1_cond, 2.5), "hi": np.nanpercentile(b1_cond, 97.5),
                       "lo_uncond": np.nanpercentile(b1_unc, 2.5), "hi_uncond": np.nanpercentile(b1_unc, 97.5),
                       "share_boot_bound_le0": float(np.mean(b1_unc <= 0))})
            # B2 nested study effects (primary)
            noise = s2_study * sw2.mean() + s2_rec * inv_n.mean()
            b2_cond = 1 - (bn[:, 1] * sw2.mean() + bn[:, 0] * inv_n.mean()) / var_s
            b2_unc = 1 - (bn[:, 1] * sw2[idx].mean(axis=1) + bn[:, 0] * inv_n[idx].mean(axis=1)) / var_b
            add_bound(scope, "B2 nested study effects (primary)", s, r, noise, s2_study + s2_rec,
                      {"lo": np.nanpercentile(b2_cond, 2.5), "hi": np.nanpercentile(b2_cond, 97.5),
                       "lo_uncond": np.nanpercentile(b2_unc, 2.5), "hi_uncond": np.nanpercentile(b2_unc, 97.5),
                       "share_boot_bound_le0": float(np.mean(b2_unc <= 0))})
            comp_mats[scope] = comp_mats[scope] + (b2_unc,)
            for lab, comps in [("B2 sensitivity: record-count (pair) weighting", nested["pair_weighted"]),
                               ("B2 sensitivity: cells with 3+ records", nested["cells_3plus"]),
                               ("B2 sensitivity: excluding COSORE", nested["no_cosore"]),
                               ("B2 sensitivity: same cells for both pair types",
                                {"s2_rec": s2_rec_sc, "s2_study": s2_study_sc})]:
                if np.isfinite(comps["s2_rec"]) and np.isfinite(comps["s2_study"]):
                    nz = comps["s2_study"] * sw2.mean() + comps["s2_rec"] * inv_n.mean()
                    add_bound(scope, lab, s, r, nz, comps["s2_study"] + comps["s2_rec"])
            ck = f"continent_{scope}"
            if ck in nested and np.isfinite(nested[ck]["s2_rec"]):
                nz = nested[ck]["s2_study"] * sw2.mean() + nested[ck]["s2_rec"] * inv_n.mean()
                add_bound(scope, "B2 sensitivity: continent-specific components", s, r, nz,
                          nested[ck]["s2_study"] + nested[ck]["s2_rec"])
            # B3 short-range semivariance (predictors smooth beyond 10 km); its interval already
            # resamples sites
            if scope in sv_sum:
                sd = sv_sum[scope]
                brow.append({"scope": scope, "estimator": "B3 short-lag semivariance (0-10 km)", "n_sites": len(s),
                             "var_sites": sd["variance"], "mean_noise_sites": sd["gamma_0_10km"],
                             "r2max_sites": 1 - sd["gamma_0_10km_share"], "lo": 1 - sd["gamma_0_10km_share_hi"],
                             "hi": 1 - sd["gamma_0_10km_share_lo"], "lo_uncond": 1 - sd["gamma_0_10km_share_hi"],
                             "hi_uncond": 1 - sd["gamma_0_10km_share_lo"], "n_pairs": sd["n_pairs_0_10km"]})
        bt = pd.DataFrame(brow)
        bt.to_csv(OUTD / f"bounds_{v}.csv", index=False)
        R["bounds"] = bt.to_dict("records")
        # ---- 5. Analysis 1 skill as a fraction of the bound ----
        # ratio_b = R2_b / bound_b on the same 2000 test-site resamples (seed 42) as the A1 intervals.
        # R2_b uses the seed-averaged XGBoost prediction stored in predictions_<v>.parquet, whose R2 is
        # 0.0005-0.006 above the mean of per-seed R2 reported in A1 (point estimates use the A1 value).
        a1f = C.OUT / "a1" / f"transfer_{v}.csv"
        pf = C.OUT / "a1" / f"predictions_{v}.parquet"
        if a1f.exists() and pf.exists():
            a1 = pd.read_csv(a1f)
            preds = pd.read_parquet(pf)
            prim = bt[bt["estimator"] == "B2 nested study effects (primary)"].set_index("scope")
            b3 = bt[bt["estimator"].str.startswith("B3")].set_index("scope")
            fr = a1[a1["model"].isin(["ols_P", "ols_TP", "xgb"])].copy()
            rows5 = []
            for _, r5 in fr.iterrows():
                E = r5["test"]
                if E not in comp_mats:
                    continue
                cells, z, sw2, inv_n, b2_unc = comp_mats[E]
                pp = preds[(preds["kind"] == r5["kind"]) & (preds["train"] == r5["train"]) &
                           (preds["test"] == E) & (preds["model"] == r5["model"])].set_index("cell").reindex(cells)
                obs, pr = pp["obs"].values, pp["pred"].values
                idx = C.boot_idx(len(obs))
                ob, pb = obs[idx], pr[idx]
                r2b = 1 - ((ob - pb) ** 2).sum(axis=1) / ((ob - ob.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
                ratio = r2b / b2_unc
                ok = b2_unc > 0
                bound = prim.loc[E, "r2max_sites"]
                rows5.append({"kind": r5["kind"], "train": r5["train"], "test": E, "n_train": r5["n_train"],
                              "n_test": r5["n_test"], "model": r5["model"], "r2": r5["r2"], "r2_lo": r5["r2_lo"],
                              "r2_hi": r5["r2_hi"], "bound_B2": bound, "bound_B2_lo": prim.loc[E, "lo_uncond"],
                              "bound_B2_hi": prim.loc[E, "hi_uncond"], "fraction_of_B2": r5["r2"] / bound,
                              "fraction_of_B2_lo": float(np.percentile(ratio[ok], 2.5)),
                              "fraction_of_B2_hi": float(np.percentile(ratio[ok], 97.5)),
                              "share_boot_bound_le0": float(np.mean(~ok)),
                              "fraction_unstable": bool(np.mean(~ok) > 0.025 or prim.loc[E, "lo_uncond"] < 0.2),
                              "bound_B3": b3["r2max_sites"].get(E, np.nan),
                              "fraction_of_B3": r5["r2"] / b3["r2max_sites"].get(E, np.nan) if E in b3.index else np.nan})
            fr5 = pd.DataFrame(rows5)
            fr5.to_csv(OUTD / f"fraction_of_bound_{v}.csv", index=False)
            R["fraction_of_bound"] = fr5.to_dict("records")
        results["variants"][v] = R
        print(f"[{v}] one-way: within={comp['s2_within']:.3f} [{comp['s2_within_lo']:.3f},{comp['s2_within_hi']:.3f}] "
              f"share_within={comp['share_within']:.3f} [{comp['share_within_lo']:.3f},{comp['share_within_hi']:.3f}] "
              f"cells={comp['n_cells']} records={comp['n_records']} REML={comp['reml']}", flush=True)
        print(f"[{v}] nested: s2_rec={s2_rec:.3f} [{nested['s2_rec_lo']:.3f},{nested['s2_rec_hi']:.3f}] "
              f"s2_study={s2_study:.3f} [{nested['s2_study_lo']:.3f},{nested['s2_study_hi']:.3f}] "
              f"same-cells={s2_rec_sc:.3f}/{s2_study_sc:.3f} REML={nested['reml_nested']}", flush=True)
        print(pc.round(3).to_string(), flush=True)
        print(bt.round(3).to_string(), flush=True)
        print(me.round(3).to_string(), flush=True)
        print({c: {k: (round(x, 3) if isinstance(x, float) else x) for k, x in sd.items() if k != 'fit_exp_le1600km'} for c, sd in sv_sum.items()}, flush=True)
        print({c: sd["fit_exp_le1600km"] for c, sd in sv_sum.items()}, flush=True)
    # SRDB's own per-record error fields as a cross-check of the within-study component.
    # Rs_annual_err is "typically plot-to-plot" error in g C m-2; whether it is an SD or an SE is not
    # recorded, so CV^2 is a lower bound for plot-scale variance on the log scale if it is an SE.
    d = C.load_srdb()[["Record_number", "Rs_annual_err", "Rs_interann_err"]].copy()
    for col in ["Rs_annual_err", "Rs_interann_err"]:
        d[col + "_nonnumeric"] = d[col].notna() & pd.to_numeric(d[col], errors="coerce").isna()
        d[col] = pd.to_numeric(d[col], errors="coerce")
    cr = rec_all[rec_all["source"] == "srdb"].merge(d, left_on="record_number", right_on="Record_number", how="left")
    out_err = {}
    for col in ["Rs_annual_err", "Rs_interann_err"]:
        e = cr[cr[col].notna() & (cr[col] > 0)]
        cv = (e[col] / e["rs_annual"]).values
        out_err[col] = {"n_records": int(len(e)), "share_of_srdb_clean_records": float(len(e) / len(cr)),
                        "n_nonnumeric_in_clean_records": int(cr[col + "_nonnumeric"].sum()),
                        "median_cv": float(np.median(cv)) if len(cv) else None,
                        "mean_cv2_log_variance_approx": float(np.mean(cv ** 2)) if len(cv) else None,
                        "median_cv2": float(np.median(cv ** 2)) if len(cv) else None}
    results["srdb_error_fields_check"] = out_err
    print("SRDB error fields:", out_err, flush=True)
    # COSORE plot-scale check
    py = pd.read_csv(C.OUT / "cosore_port_years.csv")
    py = py[py["full_year"] & py["rs_annual"].between(C.RS_MIN, C.RS_MAX)]
    py["log_rs"] = np.log(py["rs_annual"])
    g = py.groupby(["dataset", "year"])["log_rs"].agg(["size", "var"])
    g = g[g["size"] >= 2]
    results["cosore_port_level"] = {
        "n_dataset_years_multi_port": int(len(g)), "n_datasets": int(g.reset_index()["dataset"].nunique()),
        "mean_within_site_year_var_log": float(g["var"].mean()) if len(g) else None,
        "pooled_within_var_log": float(((g["size"] - 1) * g["var"]).sum() / (g["size"] - 1).sum()) if len(g) else None,
    }
    print("COSORE port-level:", results["cosore_port_level"], flush=True)
    C.write_json(results, OUTD / "a2_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
