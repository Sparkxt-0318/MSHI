"""Exact locked-test row sets (identified by matching rmse_rs_intercept to full precision) and quantities computable without features."""
import sys, json
import numpy as np, pandas as pd
W = sys.argv[1]
s = pd.read_parquet(f"{W}/out/v3/sites_v3_qc.parquet")
A = s[(s.continent == "Asia") & ~s.site_id.isin(["v3qc_00184", "v3qc_00576", "v3qc_00604"])].reset_index(drop=True)
E = s[(s.continent == "Europe") & (s.site_id != "v3qc_00559")].reset_index(drop=True)
A.to_parquet(f"{W}/out/asia_384.parquet"); E.to_parquet(f"{W}/out/europe_235.parquet")
ya, ye = A.log_rs.values, E.log_rs.values
O = np.exp(ye)
out = dict(n_asia=len(A), n_eu=len(E))
out["asia_mean_log"] = float(ya.mean()); out["eu_mean_log"] = float(ye.mean())
out["delta_eu_minus_asia_log"] = float(ye.mean() - ya.mean())
out["sd_log_asia"] = float(ya.std()); out["sd_log_eu"] = float(ye.std())
def rm(c): return float(np.sqrt(np.mean((c - O) ** 2)))
def ma(c): return float(np.mean(np.abs(c - O)))
gm = np.exp(ya.mean()); am = np.exp(ya).mean(); sm = np.exp(ya.mean() + ya.var(ddof=1) / 2)
out["baselines_gC"] = {
  "code: exp(mean log Asia) [geometric mean]": dict(value=round(gm, 1), rmse=round(rm(gm), 2), mae=round(ma(gm), 2)),
  "arithmetic mean of Asia site Rs": dict(value=round(am, 1), rmse=round(rm(am), 2), mae=round(ma(am), 2)),
  "lognormal-smeared exp(mean+var/2)": dict(value=round(sm, 1), rmse=round(rm(sm), 2), mae=round(ma(sm), 2)),
  "oracle: Europe arithmetic mean": dict(value=round(O.mean(), 1), rmse=round(rm(O.mean()), 2), mae=round(ma(O.mean()), 2)),
  "oracle: Europe median": dict(value=round(np.median(O), 1), rmse=round(rm(np.median(O)), 2), mae=round(ma(np.median(O)), 2)),
}
out["reported_model"] = dict(rmse_rs=385.5124012620602, mae_rs=267.0846425913643, rmse_rs_intercept=386.9086311104987)
# intercept-only R2 on Europe (log space) and log-space RMSE of intercept
out["intercept_r2_log"] = float(1 - np.sum((ye - ya.mean()) ** 2) / np.sum((ye - ye.mean()) ** 2))
out["intercept_rmse_log"] = float(np.sqrt(np.mean((ye - ya.mean()) ** 2)))
# model log RMSE implied by R2 = 0.07899539157825719
r2 = 0.07899539157825719
mse_m = (1 - r2) * np.mean((ye - ye.mean()) ** 2)
out["model_rmse_log_implied"] = float(np.sqrt(mse_m))
out["skill_log_vs_asia_mean"] = float(1 - np.sqrt(mse_m) / out["intercept_rmse_log"])
# observed site Rs used as truth = exp(mean log) = geometric mean of records; compare with arithmetic mean of records via SRDB? (n_rec)
out["eu_sites_with_2plus_records"] = int((E.n_rec >= 2).sum())
# 2-degree blocks in Europe
b = (np.floor(E.lon / 2).astype(int).astype(str) + "_" + np.floor(E.lat / 2).astype(int).astype(str)).values
u, c = np.unique(b, return_counts=True)
out["eu_2deg_blocks"] = dict(n_blocks=int(len(u)), singletons=int((c == 1).sum()), max_sites=int(c.max()),
                             top5=sorted(c.tolist(), reverse=True)[:5])
print(json.dumps(out, indent=1))
