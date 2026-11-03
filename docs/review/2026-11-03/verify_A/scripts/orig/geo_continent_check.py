"""mshi.geo.geographic_continent on known places; the open-ocean subunits; overlapping subunits; the Russia rule;
determinism of the first-match rule for points in two subunits."""
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config  # noqa: E402
from mshi.geo import OPEN_OCEAN, geographic_continent, subunits  # noqa: E402

cfg = load_config()
su = subunits(cfg)
pd.set_option("display.width", 250)
print("subunits:", len(su))
oo = su[su.CONTINENT.eq(OPEN_OCEAN)]
print(f"open-ocean subunits ({len(oo)}):")
print(oo[["ADMIN", "SUBUNIT", "REGION_UN", "SUBREGION", "continent_geo"]].to_string())
print("continent_geo values:", su.continent_geo.value_counts().to_dict())
print("Russian subunits:", su[su.ADMIN.eq("Russia")][["SUBUNIT", "CONTINENT"]].values.tolist())
print("subunits with SUBUNIT/ADMIN containing Russia but ADMIN != Russia:",
      su[su.SUBUNIT.str.contains("Russia") & ~su.ADMIN.eq("Russia")][["ADMIN", "SUBUNIT"]].values.tolist())

places = {  # name: (lon, lat, expected)
    "French Guiana (Paracou)": (-52.92, 5.27, "South America"), "Guadeloupe": (-61.55, 16.25, "North America"),
    "Martinique": (-61.0, 14.65, "North America"), "Reunion": (55.5, -21.1, "Africa"), "Mayotte": (45.15, -12.82, "Africa"),
    "New Caledonia": (165.5, -21.5, "Oceania"), "Tahiti": (-149.43, -17.65, "Oceania"),
    "Saint Pierre and Miquelon": (-56.18, 46.78, "North America"), "Tenerife": (-16.63, 28.29, "Africa"),
    "Gran Canaria": (-15.6, 27.95, "Africa"), "Madeira": (-16.95, 32.75, "Africa"), "Azores": (-25.67, 37.75, "Europe"),
    "Ceuta": (-5.32, 35.89, "Africa"), "Melilla": (-2.94, 35.29, "Africa"),
    "Svalbard": (15.6, 78.2, "Europe"), "Faroe Islands": (-6.9, 62.0, "Europe"), "Iceland": (-19.0, 64.9, "Europe"),
    "Greenland": (-50.0, 70.0, "North America"), "Hawaii (Big Island)": (-155.3, 19.8, "Oceania"),
    "Kauai": (-159.5, 22.05, "Oceania"), "Alaska (Fairbanks)": (-147.7, 64.84, "North America"),
    "Attu (Aleutians, east longitude)": (173.2, 52.9, "North America"), "Guam": (144.79, 13.45, "Oceania"),
    "Puerto Rico": (-66.5, 18.2, "North America"), "American Samoa": (-170.7, -14.3, "Oceania"),
    "Galapagos": (-90.4, -0.7, "South America"), "Easter Island": (-109.35, -27.12, "Oceania"),
    "Falklands": (-59.0, -51.7, "South America"), "South Georgia": (-36.5, -54.3, "South America"),
    "Bermuda": (-64.75, 32.3, "North America"), "Kaliningrad": (20.5, 54.7, "Europe"), "Moscow": (37.6, 55.75, "Europe"),
    "Urals 59.9E": (59.9, 57.0, "Europe"), "Urals 60.1E": (60.1, 57.0, "Asia"), "Sakhalin": (142.7, 50.0, "Asia"),
    "Chukotka east of 180": (-174.0, 66.0, "Asia"), "Wrangel west of 180": (179.5, 71.3, "Asia"),
    "Wrangel east of 180": (-179.5, 71.3, "Asia"), "Crimea": (34.1, 44.95, "Europe"),
    "Istanbul (European side; Turkey kept whole)": (28.97, 41.01, "Asia"), "Cairo": (31.24, 30.04, "Africa"),
    "Sinai (Egypt kept whole)": (33.8, 29.5, "Africa"), "Panama": (-79.5, 9.0, "North America"),
    "Papua (Indonesia)": (138.5, -4.0, "Asia"), "Papua New Guinea": (145.0, -6.0, "Oceania"),
    "Cyprus": (33.0, 35.0, "Asia"), "Antarctica": (0.0, -80.0, "Antarctica"), "Tasmania": (146.5, -42.0, "Oceania"),
    "Madagascar": (47.0, -19.0, "Africa"), "Sri Lanka": (80.7, 7.8, "Asia"), "Maldives": (73.5, 4.2, "Asia"),
    "Seychelles (Mahe)": (55.45, -4.65, "Africa"), "Mauritius": (57.55, -20.25, "Africa"),
    "Fiji east of 180": (-179.85, -16.6, "Oceania"), "Fiji (Viti Levu)": (178.0, -17.8, "Oceania"),
    "Kiribati (Kiritimati)": (-157.4, 1.87, "Oceania"), "Tonga": (-175.2, -21.2, "Oceania"),
    "Malta": (14.45, 35.9, "Europe"), "Gibraltar": (-5.35, 36.14, "Europe"), "Sicily": (14.0, 37.5, "Europe"),
    "Trinidad": (-61.3, 10.45, "North America"), "Aruba": (-69.97, 12.52, "North America"),
    "Curacao": (-68.95, 12.17, "North America"), "Bonaire": (-68.27, 12.17, "North America"),
    "Saint Helena": (-5.7, -15.95, "Africa"), "Kerguelen": (69.5, -49.3, None), "Heard Island": (73.5, -53.1, None),
    "Bouvet": (3.4, -54.43, None), "Cocos (Keeling)": (96.85, -12.15, None), "Christmas Island": (105.63, -10.48, None),
    "Socotra": (53.8, 12.5, "Asia"), "Canary 20 km off coast": (-15.6, 28.35, "Africa"),
    "Portugal 20 km off": (-9.65, 38.7, "Europe"), "mid-Atlantic": (-30.0, 30.0, None),
    "lon exactly 180 (Russia)": (180.0, 68.0, "Asia"), "lon exactly -180 (Russia)": (-180.0, 68.0, "Asia"),
    "north pole": (0.0, 90.0, None), "south pole": (0.0, -90.0, "Antarctica"),
}
lon = [v[0] for v in places.values()]
lat = [v[1] for v in places.values()]
got = geographic_continent(cfg, lon, lat, su)
got.index = list(places)
got["expected"] = [v[2] for v in places.values()]
got["ok"] = [(e is None) or (g == e) for g, e in zip(got.continent_geo, got.expected)]
print(got.to_string())
print("unexpected:", got[~got.ok].index.tolist())

# overlapping subunits: points (record coordinates and a 0.25-deg grid) inside more than one subunit
A = pd.read_parquet("/home/user/MSHI/data/derived/records_analysis.parquet")
pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(A.lon, A.lat), crs=4326)
j = gpd.sjoin(pts, su, how="inner", predicate="within")
dup = j.index[j.index.duplicated()].unique()
print("records inside more than one subunit:", len(dup))
gx, gy = np.meshgrid(np.arange(-179.875, 180, 0.25), np.arange(-89.875, 90, 0.25))
gp = gpd.GeoDataFrame(geometry=gpd.points_from_xy(gx.ravel(), gy.ravel()), crs=4326)
jg = gpd.sjoin(gp, su, how="inner", predicate="within")
d2 = jg[jg.index.duplicated(keep=False)]
print("0.25-deg cell centres inside more than one subunit:", d2.index.nunique())
if len(d2):
    print(d2.groupby(level=0).apply(lambda x: tuple(sorted(zip(x.SUBUNIT, x.continent_geo)))).value_counts().head(20))
# do overlapping pairs ever disagree on continent_geo?
if len(d2):
    nun = d2.groupby(level=0).continent_geo.nunique()
    print("   of which with different continent_geo:", int((nun > 1).sum()))
