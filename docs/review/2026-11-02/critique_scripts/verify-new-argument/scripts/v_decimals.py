"""Finding 06: reconstruct the '>=4-decimal coordinates' stratification from the raw SRDB strings.
Record->site mapping recomputed with build_sites_v3.py's own to_sites() labelling (L86-93) on the QC records."""
import sys, re, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
from statsmodels.stats.proportion import proportion_confint
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import V, samp, LC, REP_B
r = pd.read_parquet(f"{V}/out/v3/records_v3.parquet")
base = r[~r.f_offland & ~r.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5.0 / 6371.0)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site_id"] = [f"v3qc_{i:05d}" for i in lab]
st = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet")
chk = qc.groupby("site_id").agg(lat=("lat", "mean"), lon=("lon", "mean")).reindex(st.site_id)
assert np.allclose(chk.lat.values, st.lat.values) and np.allclose(chk.lon.values, st.lon.values), "site mapping mismatch"
raw = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", dtype=str, low_memory=False)
raw["rec_id"] = "srdb_" + raw.index.astype(str)
cos = pd.read_csv(f"{V}/out/cosore_annual_derived.csv", dtype=str).rename(columns={"site_id": "rec_id", "latitude": "Latitude", "longitude": "Longitude"})
rs = pd.concat([raw[["rec_id", "Latitude", "Longitude"]], cos[["rec_id", "Latitude", "Longitude"]]])
qc = qc.merge(rs, on="rec_id", how="left")
def ndec(x):
    x = str(x).strip(); return len(x.split(".")[1]) if "." in x else 0
qc["dlat"] = qc.Latitude.map(ndec); qc["dlon"] = qc.Longitude.map(ndec); qc["dmin"] = qc[["dlat", "dlon"]].min(axis=1)
def dms_like(x):
    """fractional part equal (to 1e-6) to a whole number of arc-minutes or arc-seconds"""
    v = abs(float(x)); fr = v - np.floor(v)
    m = fr * 60; s = fr * 3600
    return ("min" if abs(m - round(m)) < 1e-4 * 60 / 60 * 6 else ("sec" if abs(s - round(s)) < 6e-3 else "no"))
qc["dms_lat"] = qc.Latitude.map(dms_like); qc["dms_lon"] = qc.Longitude.map(dms_like)
four = qc[(qc.dmin >= 4)]
print("QC records with >=4 decimals in both coords:", len(four), "| DMS-like (minute-level both):", int(((four.dms_lat == "min") & (four.dms_lon == "min")).sum()),
      "| minute-or-second in both:", int((four.dms_lat.isin(["min", "sec"]) & four.dms_lon.isin(["min", "sec"])).sum()))
raw["dlat"] = raw.Latitude.map(ndec); raw["dlon"] = raw.Longitude.map(ndec)
rr = raw[(raw.dlat >= 4) & (raw.dlon >= 4)]
rr_dl = rr.Latitude.map(dms_like); rr_do = rr.Longitude.map(dms_like)
print("ALL SRDB rows with >=4 decimals in both coords:", len(rr), "| minute-level both:", int(((rr_dl == "min") & (rr_do == "min")).sum()),
      "| second-level (not minute) in both or mixed:", int((rr_dl.isin(["min", "sec"]) & rr_do.isin(["min", "sec"])).sum() - ((rr_dl == "min") & (rr_do == "min")).sum()))
# site-level: every record >= 4 decimals ; any record >= 4 decimals
g = qc.groupby("site_id").agg(all4=("dmin", lambda x: bool((x >= 4).all())), any4=("dmin", lambda x: bool((x >= 4).any())),
                              alldms=("dms_lat", lambda x: False))
dd = qc.assign(nodms=~(qc.dms_lat.isin(["min", "sec"]) & qc.dms_lon.isin(["min", "sec"])))
g["all4_nodms"] = dd.groupby("site_id").apply(lambda x: bool(((x.dmin >= 4) & x.nodms).all()))
st = st.merge(g, left_on="site_id", right_index=True)
st["plot_forest"] = st.ecosystem.replace(REP_B).eq("Forest")
inbox = (st.lon.between(25, 180) & st.lat.between(-10, 80)) | (st.lon.between(-125, -66) & st.lat.between(24, 50))
st["code"] = np.where(inbox, samp(LC, st.lon.values, st.lat.values), np.nan)
for sample, m in [("Q1 (all continents in boxes)", inbox & (st.code > 0)), ("N2b (Asia+NA, pre-WorldClim drop)", inbox & (st.code > 0) & st.continent.isin(["Asia", "North America"]))]:
    f = st[m & st.plot_forest]
    for crit in ["all4", "any4", "all4_nodms"]:
        ff = f[f[crit]]; k = int(np.isin(ff.code, [1, 2, 3, 4, 5]).sum()); n = len(ff)
        lo, hi = proportion_confint(k, n, method="wilson") if n else (np.nan, np.nan)
        print(f"{sample} | forest plots with {crit}: n={n}, in IGBP1-5 pixels {k} = {k/max(n,1):.3f} [Wilson {lo:.3f}, {hi:.3f}]")
    k = int(np.isin(f.code, [1, 2, 3, 4, 5]).sum()); print(f"{sample} | all forest plots: {k}/{len(f)} = {k/len(f):.3f}")
# naive float-based count on site means
def ndec_float(v): s = repr(float(v)); return len(s.split(".")[1]) if "." in s else 0
st["site_float_dec"] = np.minimum(st.lat.map(ndec_float), st.lon.map(ndec_float))
m = inbox & (st.code > 0)
print("Q1 sites whose site-MEAN floats have >=4 decimals:", int((st[m].site_float_dec >= 4).sum()), "; of which contain a record with <4 decimals:", int(((st[m].site_float_dec >= 4) & ~st[m].all4).sum()))
# --- added: exclude only minute-level DMS (precision ~ +-0.9 km); second-level DMS is ~ +-15 m
dd2 = qc.assign(nomin=~((qc.dms_lat == "min") & (qc.dms_lon == "min")))
g2 = dd2.groupby("site_id").apply(lambda x: bool(((x.dmin >= 4) & x.nomin).all())).rename("all4_nominDMS")
st = st.merge(g2, left_on="site_id", right_index=True)
for sample, m in [("Q1", inbox & (st.code > 0)), ("N2b", inbox & (st.code > 0) & st.continent.isin(["Asia", "North America"]))]:
    ff = st[m & st.plot_forest & st.all4_nominDMS]; k = int(np.isin(ff.code, [1, 2, 3, 4, 5]).sum())
    lo, hi = proportion_confint(k, len(ff), method="wilson")
    print(f"{sample} | forest plots, every record >=4 dec and not minute-level DMS: n={len(ff)}, in IGBP1-5 {k} = {k/len(ff):.3f} [{lo:.3f}, {hi:.3f}]")
