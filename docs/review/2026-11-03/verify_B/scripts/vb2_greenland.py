"""B-2 independent check: is Greenland in North America's kNNDM prediction domain, how big a share, and does it change
the split? Independent of the reviewer's stand-in: (1) mshi.geo.geographic_continent on interior ice-sheet points;
(2) geodesic polygon areas (pyproj, WGS84) of the Natural Earth subunits by continent_geo; (3) a different stand-in
land mask: 0.5-degree cells whose centre lies in ne_50m_land (not the subunits), labelled with geographic_continent,
drawn by the stage's own prediction_domain for five domain seeds, with vs without the Greenland cells; kNNDM on the
real NA analysis-QC coordinates (no outcomes) with the configured settings."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import time
import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import Geod
from mshi.config import load_config
from mshi.geo import subunits, geographic_continent
from mshi.analysis.grid import cell_area_km2
from mshi.analysis import transfer as T
from mshi.analysis import knndm as kn
from mshi.spatial import block_folds

cfg = load_config()
su = subunits(cfg)
Rkm = cfg["site_build"]["earth_radius_km"]
W, K = cfg["phase2"]["within"], cfg["phase2"]["within"]["knndm"]

# (1) interior Greenland points
pts = np.array([[-40.0, 72.0], [-45.0, 65.0], [-35.0, 78.0], [-50.0, 69.0], [-30.0, 81.0]])
c = geographic_continent(cfg, pts[:, 0], pts[:, 1], su)
print("(1) geographic_continent of Greenland ice-sheet points:", list(zip(c.continent_geo, c.geo_subunit)))

# (2) geodesic areas
geod = Geod(ellps="WGS84")
area = su.geometry.apply(lambda g: abs(geod.geometry_area_perimeter(g)[0]) / 1e6)
na = su.continent_geo.eq("North America")
gr = su.SUBUNIT.eq("Greenland")
print(f"(2) geodesic area: Greenland {area[gr].sum()/1e6:.3f} M km2; North America (continent_geo) {area[na].sum()/1e6:.3f} "
      f"M km2; share {area[gr].sum()/area[na].sum():.3f}")

# (3) a different land mask: ne_50m_land
land = gpd.read_file("/home/user/MSHI/data/raw/naturalearth/v5.1.2/ne_50m_land.geojson")
deg = 0.5
lon, lat = np.meshgrid(np.arange(-180 + deg / 2, 180, deg), np.arange(-90 + deg / 2, 90, deg))
g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
g = g[(g.lat > -60)].reset_index(drop=True)     # no NA cell lies south of -60; saves time
p = gpd.GeoDataFrame({"i": np.arange(len(g))}, geometry=gpd.points_from_xy(g.lon, g.lat), crs=4326)
inside = np.unique(gpd.sjoin(p, land[["geometry"]], how="inner", predicate="within").i.values)
g = g.iloc[inside].reset_index(drop=True)
# label only the candidate cells of the Americas/Greenland window (speed): lon -180..-10, lat 5..85
cand = g[(g.lon < -10) & (g.lat > 0)].reset_index(drop=True)
t0 = time.time()
lab = geographic_continent(cfg, cand.lon.values, cand.lat.values, su)
cand["continent_geo"], cand["subunit"] = lab.continent_geo.values, lab.geo_subunit.values
cand["area_km2"] = cell_area_km2(cand.lat.values, deg, Rkm)
print(f"(3) ne_50m_land stand-in: {len(cand)} cells in the window labelled in {time.time()-t0:.0f}s")
nag = cand[cand.continent_geo == "North America"]
isg = nag.subunit.eq("Greenland")
print(f"    North America cells {len(nag)}, Greenland {int(isg.sum())}; Greenland area share {nag.area_km2[isg].sum()/nag.area_km2.sum():.3f}")
cand.to_parquet("ne50land_window_grid.parquet", index=False)

sites = pd.read_parquet("/home/user/MSHI/data/derived/sites_analysis_qc.parquet")
sites = sites[sites.continent_geo == "North America"].sort_values("site_id", kind="mergesort").reset_index(drop=True)
x = np.c_[sites.lon, sites.lat]
kw = {k: v for k, v in K.items() if k not in T.DOMAIN_KEYS}
print(f"    NA analysis-QC sites: {len(x)}; sites in Greenland: {int((sites.geo_subunit == 'Greenland').sum())}")
for seed in (42, 43, 44, 45, 46):
    Ks = {**K, "seed": seed}
    res = {}
    for name, grid in (("with", cand), ("without", cand[~cand.subunit.eq("Greenland")])):
        dom = T.prediction_domain(grid, "North America", Ks)
        n_gr = None
        if name == "with":
            key = set(map(tuple, cand.loc[cand.subunit.eq("Greenland"), ["lon", "lat"]].to_numpy()))
            n_gr = sum(tuple(r) in key for r in dom)
        f, info = kn.knndm_folds(x, dom, **{**kw, "seed": seed}, earth_radius_km=Rkm)
        gij = kn.nearest_km(x, dom, Rkm)
        wb = [kn.fold_match(x, dom, T.fold_labels(list(block_folds(sites.lon.values, sites.lat.values, s, W["block_deg"],
                                                                    W["folds"])), len(x)), Rkm)["W"] for s in W["seeds"]]
        res[name] = (f, info)
        print(f"    seed {seed} {name:7s} Greenland: draws on Greenland {n_gr if n_gr is not None else '-':>4} | q={info['q']} "
              f"sizes={info['fold_sizes']} W={info['W']:.1f} W_random={info['W_random']:.1f} W_blocks={[round(v,1) for v in wb]} "
              f"Gij q50/75/90 = {np.quantile(gij, [.5, .75, .9]).round(0).tolist()} KS p={info['ks']['p']:.2g}")
    fw, fo = res["with"][0], res["without"][0]
    same = len(set(zip(fw.tolist(), fo.tolist()))) == len(np.unique(fw)) == len(np.unique(fo))
    print(f"    seed {seed}: same partition with and without Greenland: {same}")
