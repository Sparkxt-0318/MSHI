"""Statistics on the exact locked-test rows (Asia 384 / Europe 235), no features needed."""
import sys, json
import numpy as np, pandas as pd
st = pd.read_parquet(sys.argv[1])
A = st[(st.continent == "Asia") & ~st.site_id.isin(["v3qc_00184", "v3qc_00576", "v3qc_00604"])].reset_index(drop=True)
E = st[(st.continent == "Europe") & ~st.site_id.isin(["v3qc_00559"])].reset_index(drop=True)
ya, ye = A.log_rs.values, E.log_rs.values
ro = np.exp(ye)
gm_asia = np.exp(ya.mean()); am_asia = np.exp(ya).mean()
out = dict(n_asia=len(A), n_eu=len(E),
           eu_multi_record_sites=int((E.n_rec >= 2).sum()),
           mean_log_asia=ya.mean(), mean_log_eu=ye.mean(), diff_log_eu_minus_asia=ye.mean() - ya.mean(),
           asia_geo_mean_exp_meanlog=gm_asia, asia_arith_mean_of_site_values=am_asia, smear_ratio=am_asia / gm_asia,
           eu_arith_mean=ro.mean(), eu_geo_mean=np.exp(ye.mean()),
           var_log_eu_pop=ye.var(), sst_eu=((ye - ye.mean()) ** 2).sum())
rmse = lambda c: float(np.sqrt(np.mean((c - ro) ** 2))); mae = lambda c: float(np.mean(np.abs(c - ro)))
out["rmse_geo_baseline(code)"] = rmse(gm_asia); out["mae_geo_baseline"] = mae(gm_asia)
out["rmse_arith_baseline"] = rmse(am_asia); out["mae_arith_baseline"] = mae(am_asia)
out["rmse_oracle_eu_mean"] = rmse(ro.mean()); out["mae_oracle_eu_median"] = mae(np.median(ro))
MODEL_RMSE, MODEL_MAE, BIAS = 385.5124012620602, 267.0846425913643, -0.04597089804138787
out["model_rmse_rel_to_geo"] = 1 - MODEL_RMSE / out["rmse_geo_baseline(code)"]
out["model_mae_rel_to_geo"] = 1 - MODEL_MAE / out["mae_geo_baseline"]
out["model_rmse_rel_to_arith"] = 1 - MODEL_RMSE / out["rmse_arith_baseline"]
out["model_mae_rel_to_arith"] = 1 - MODEL_MAE / out["mae_arith_baseline"]
out["gC_R2_vs_oracle"] = 1 - (MODEL_RMSE / out["rmse_oracle_eu_mean"]) ** 2
out["model_mean_pred_log"] = ye.mean() + BIAS; out["exp_model_mean_pred_log"] = float(np.exp(ye.mean() + BIAS))
# log-space skill: 1 - RMSE_model/RMSE_null ; R2 0.079 -> RMSE_model = sqrt((1-R2)*var); null = Asia-mean constant
R2 = 0.07899539157825719
rmse_model_log = np.sqrt((1 - R2) * ye.var()); rmse_null_log = np.sqrt(np.mean((ya.mean() - ye) ** 2))
out["rmse_model_log"] = rmse_model_log; out["rmse_null_log_asia_const"] = rmse_null_log; out["skill_log_vs_asia_const"] = 1 - rmse_model_log / rmse_null_log
out["skill_log_vs_eu_own_mean"] = 1 - np.sqrt(1 - R2)
# 2-degree blocks in Europe; 5-degree blocks in Asia
def blocks(df, deg):
    return (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
b2 = pd.Series(blocks(E, 2.0)).value_counts(); out["eu_2deg_blocks"] = len(b2); out["eu_2deg_singletons"] = int((b2 == 1).sum())
b5e = pd.Series(blocks(E, 5.0)).value_counts(); out["eu_5deg_blocks"] = len(b5e)
b5 = pd.Series(blocks(A, 5.0)).value_counts(); out["asia_5deg_blocks"] = len(b5); out["asia_5deg_singletons"] = int((b5 == 1).sum())
print(json.dumps({k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in out.items()}, indent=1))
A.to_parquet("out/asia_384.parquet"); E.to_parquet("out/europe_235.parquet")
