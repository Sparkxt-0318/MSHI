"""Phase A2 + A3 + A4 — site spot checks, per-region correlations, target sanity."""
import numpy as np
import pandas as pd
import rasterio
from pathlib import Path

ROOT = Path("/home/user/MSHI")
SG = ROOT / "data" / "raw" / "soilgrids"
TRAIN = ROOT / "data" / "processed" / "training_features.parquet"
US = ROOT / "data" / "processed" / "us_validation_features.parquet"

VARS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
SCALE = {"soc": 0.1, "nitrogen": 0.01, "phh2o": 0.1,
         "clay": 0.1, "sand": 0.1, "silt": 0.1,
         "bdod": 0.01, "cec": 0.1}

# ─────────────────────────────────────────────────────────────────────────────
# A2 — site spot checks (using 5-15cm tiles; 0-30cm not downloaded)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 96)
print("PHASE A2 — site spot checks (SoilGrids 5-15cm; 0-30cm aggregate not on disk)")
print("=" * 96)

SITES = [
    ("Hubbard Brook NH",  43.94, -71.74, "us",
        {"soc": "50-80 g/kg",  "phh2o": "3.9-4.5", "clay": "5-15%",  "sand": "60-75%", "silt": "15-30%", "nitrogen": "2-5 g/kg"}),
    ("Harvard Forest MA", 42.54, -72.17, "us",
        {"soc": "30-60 g/kg",  "phh2o": "3.7-4.6", "clay": "5-15%",  "sand": "55-70%", "silt": "20-35%", "nitrogen": "1.5-4 g/kg"}),
    ("Negev Desert IL",   30.85,  34.78, "asia",
        {"soc": "<5 g/kg",     "phh2o": "7.5-8.5", "clay": "10-30%", "sand": "40-70%", "silt": "20-40%", "nitrogen": "<0.5 g/kg"}),
]

print(f"{'site':<20s} {'var':<10s} {'extracted':>14s}    reference")
print("-" * 80)
for name, lat, lon, region, ref in SITES:
    for v in VARS:
        p = SG / f"{v}_5-15cm_{region}_5km.tif"
        with rasterio.open(p) as src:
            raw = next(src.sample([(lon, lat)]))[0]
        if raw == 0 or raw < 0:
            extracted = "NODATA"
        else:
            scaled = raw * SCALE[v]
            unit = {"soc":"g/kg","nitrogen":"g/kg","phh2o":"","clay":"%","sand":"%",
                    "silt":"%","bdod":"g/cm3","cec":"cmol/kg"}[v]
            extracted = f"{scaled:.2f} {unit}"
        ref_val = ref.get(v, "—")
        flag = ""
        # Coarse 2x flag — only for variables we have reference numbers
        try:
            if v in ref and isinstance(scaled, float) and v != "phh2o":
                lo_str = ref[v].split("-")[0].lstrip("<>").split()[0]
                lo = float(lo_str)
                hi_str = ref[v].split("-")[-1].split()[0] if "-" in ref[v] else lo_str
                hi = float(hi_str.lstrip("<>"))
                if scaled < lo / 2 or scaled > hi * 2:
                    flag = "  ** off >2x **"
            elif v == "phh2o" and isinstance(scaled, float):
                lo, hi = float(ref[v].split("-")[0]), float(ref[v].split("-")[1])
                if abs(scaled - (lo+hi)/2) > 1.5:
                    flag = "  ** pH off >1.5 **"
        except Exception:
            pass
        print(f"{name:<20s} {v:<10s} {extracted:>14s}    {ref_val}{flag}")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# A3 — per-region correlations
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 96)
print("PHASE A3 — Pearson r(feature, log_rs_annual), per region")
print("=" * 96)

asia = pd.read_parquet(TRAIN)
us = pd.read_parquet(US)
target = "log_rs_annual"
drop = {target, "rs_annual", "longitude", "latitude", "site_id", "source", "region"}
feats = [c for c in asia.columns if c not in drop]

asia_clean = asia.dropna(subset=[target] + feats)
us_clean   = us.dropna(subset=[target] + feats)

print(f"Asia n={len(asia_clean)},  US n={len(us_clean)}\n")
print(f"{'feature':<22s} {'r_Asia':>10s} {'r_US':>10s} {'sign_flip?':>14s}")
print("-" * 60)
rows = []
for f in feats:
    r_a = asia_clean[f].corr(asia_clean[target])
    r_u = us_clean[f].corr(us_clean[target])
    flip = (r_a > 0.05 and r_u < -0.05) or (r_a < -0.05 and r_u > 0.05)
    rows.append((abs(r_a), f, r_a, r_u, flip))
    flag = "  ** flip **" if flip else ""
    print(f"{f:<22s} {r_a:+10.3f} {r_u:+10.3f}        {flag}")

print("\nRanked by |r_Asia| (top drivers in Asia training data):")
for ar, f, r_a, r_u, _ in sorted(rows, reverse=True)[:8]:
    print(f"  {f:<22s} r_Asia={r_a:+.3f}   r_US={r_u:+.3f}")

# ─────────────────────────────────────────────────────────────────────────────
# A4 — target sanity
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 96)
print("PHASE A4 — log_rs_annual distribution sanity")
print("=" * 96)

def summarize(name, df):
    s_log = df["log_rs_annual"].dropna()
    s_rs  = df["rs_annual"].dropna()
    print(f"\n{name}: n={len(df)}, log_rs n_valid={len(s_log)}, "
          f"rs_annual<=0: {(df['rs_annual']<=0).sum()},  "
          f"rs_annual<50: {(df['rs_annual']<50).sum()},  "
          f"rs_annual>5000: {(df['rs_annual']>5000).sum()}")
    qs = s_log.quantile([0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
    print(f"  log_rs   min={qs[0.0]:.2f}  p5={qs[0.05]:.2f}  p25={qs[0.25]:.2f}  "
          f"med={qs[0.5]:.2f}  p75={qs[0.75]:.2f}  p95={qs[0.95]:.2f}  max={qs[1.0]:.2f}")
    print(f"  log_rs   mean={s_log.mean():.3f}  std={s_log.std():.3f}")
    print(f"  rs_annual median={s_rs.median():.0f}  IQR=({s_rs.quantile(0.25):.0f}, {s_rs.quantile(0.75):.0f})")
    # ASCII histogram of log_rs
    bins = np.linspace(3.5, 8.5, 21)  # 0.25 wide
    counts, edges = np.histogram(s_log, bins=bins)
    max_c = max(counts) if counts.max() > 0 else 1
    print(f"  log_rs histogram (range {edges[0]:.1f}-{edges[-1]:.1f}, bin 0.25):")
    for c, lo, hi in zip(counts, edges[:-1], edges[1:]):
        bar = "█" * int(round(40 * c / max_c))
        print(f"    [{lo:4.2f}, {hi:4.2f})  {c:>4d}  {bar}")

summarize("ASIA training", asia)
summarize("US validation", us)

# Side-by-side mean / std comparison
print("\n" + "-" * 60)
ml_a, sd_a = asia["log_rs_annual"].mean(), asia["log_rs_annual"].std()
ml_u, sd_u = us["log_rs_annual"].mean(),   us["log_rs_annual"].std()
print(f"Asia log_rs:  mean={ml_a:.3f}  std={sd_a:.3f}")
print(f"US   log_rs:  mean={ml_u:.3f}  std={sd_u:.3f}")
print(f"Mean shift Asia→US: {ml_u-ml_a:+.3f} log units = "
      f"{(np.exp(ml_u-ml_a)-1)*100:+.1f}% in Rs")
print(f"Std ratio US/Asia: {sd_u/sd_a:.2f}  (1.0 = same spread)")
