"""Shared loaders for the verifier's proxy re-analyses (N2b spec from exp_forest_bias.py)."""
import numpy as np, pandas as pd, rasterio
V = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument"
LC = "/home/user/MSHI/data/raw/modis/landcover_igbp_2023.tif"
REP_B = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest", "Mixed forests": "Forest"}
REP_C = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
         "Mixed forests": "Forest", "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"}


def samp(path, lon, lat):
    with rasterio.open(path) as s:
        return np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)


def sites(fill=False):
    """N2b sample (exp_forest_bias.py L23-31) with proxy climate. fill=False drops the 4 sites with no proxy (n=577)."""
    d = pd.read_parquet(f"{V}/out/sites_qc_proxy.parquet")
    d["plot_forest"] = d.ecosystem.replace(REP_B).eq("Forest").astype(int)
    d["pt"] = d.ecosystem.replace(REP_C)
    inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
    d = d[inbox & d.continent.isin(["Asia", "North America"])].copy()
    if fill:
        import json
        from sklearn.neighbors import BallTree
        clim = pd.read_parquet(f"{V}/out/atlas_clim.parquet")
        t = BallTree(np.radians(clim[["lat", "lon"]].values), metric="haversine")
        m = d.bio01.isna().values
        _, idx = t.query(np.radians(d.loc[m, ["lat", "lon"]].values), k=1)
        d.loc[m, "bio01"] = clim.bio01.values[idx[:, 0]]; d.loc[m, "bio12"] = clim.bio12.values[idx[:, 0]]
    d["lnP"] = np.log(d.bio12)
    d = d.dropna(subset=["log_rs", "bio01", "lnP"]).copy()
    code = samp(LC, d.lon.values, d.lat.values)
    d = d[(code > 0)].copy(); d["code"] = code[code > 0]
    d["pixel_forest"] = np.isin(d.code, [1, 2, 3, 4, 5]).astype(int)
    return d.reset_index(drop=True)


def cells(excl=(13, 15, 16, 17), fill=True):
    g = pd.read_parquet(f"{V}/out/cells_all_codes.parquet")
    inc = [f"n{k}" for k in range(1, 18) if k not in excl]
    g["n"] = g[inc].sum(axis=1)
    g = g[g.n >= 20].copy()
    if fill:
        g["bio01"] = g.bio01.fillna(g.bio01_fill); g["bio12"] = g.bio12.fillna(g.bio12_fill)
    g = g.dropna(subset=["bio01", "bio12"]).copy()
    g["lnP"] = np.log(g.bio12.clip(lower=1))
    g["veg_area_m2"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0)
    for name, codes in [("f", [1, 2, 3, 4, 5]), ("f8", [1, 2, 3, 4, 5, 8]), ("f89", [1, 2, 3, 4, 5, 8, 9])]:
        g[name] = g[[f"n{k}" for k in codes]].sum(axis=1) / g.n
    return g.reset_index(drop=True)
