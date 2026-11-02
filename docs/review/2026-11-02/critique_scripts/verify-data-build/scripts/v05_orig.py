import sys, numpy as np, pandas as pd
from rasterio.transform import Affine
from rasterio.windows import from_bounds
from pyproj import Transformer
V = sys.argv[1]; P = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/processed"
T = 1111950.5197; PS = T / 2400
tf = Transformer.from_crs("EPSG:4326", "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext", always_xy=True)
d = pd.concat([pd.read_parquet(f"{P}/training_features_v2.parquet"), pd.read_parquet(f"{P}/us_validation_features_v2.parquet")])
x, y = tf.transform(d.longitude.values, d.latitude.values)
d["h"] = np.floor((x + 20015109.354) / T).astype(int); d["v"] = np.floor((10007554.677 - y) / T).astype(int)
fo = []
for _, s in d.iterrows():
    tr = Affine(PS, 0, -20015109.354 + s.h * T, 0, -PS, 10007554.677 - s.v * T)
    xs, ys = tf.transform([s.longitude - .025, s.longitude + .025] * 2, [s.latitude - .025] * 2 + [s.latitude + .025] * 2)
    w = from_bounds(min(xs), min(ys), max(xs), max(ys), tr).round_offsets().round_lengths()
    rr = np.arange(int(w.row_off), int(w.row_off + w.height)); cc = np.arange(int(w.col_off), int(w.col_off + w.width))
    fo.append(1 - np.outer((rr >= 0) & (rr < 2400), (cc >= 0) & (cc < 2400)).mean())
d["frac_out"] = fo
print(f"original 889 sites: window partly outside tile: {(d.frac_out > 0).sum()}, >=25%: {(d.frac_out >= .25).sum()}")
k = d.dropna(subset=["npp"]); sim = k.npp * (1 - k.frac_out)
print(f"sites with committed NPP: {len(k)}; r(committed, committed*(1-frac_out)) = {np.corrcoef(k.npp, sim)[0,1]:.4f}  (upper bound on r if the bug were the only difference)")
