"""knndm.py / D-P2-7: 'Spherical distances (6,371 km) are within -0.45% to +0.56% of WGS84 geodesics (1-3,000 km)'."""
import numpy as np
from pyproj import Geod
G = Geod(ellps="WGS84")
rng = np.random.default_rng(0)
n = 200000
lat1 = np.degrees(np.arcsin(rng.uniform(-1, 1, n))); lon1 = rng.uniform(-180, 180, n)
az = rng.uniform(0, 360, n); dist = rng.uniform(1e3, 3e6, n)
lon2, lat2, _ = G.fwd(lon1, lat1, az, dist)
p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(lon2 - lon1)
a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
gc = 2 * 6371000.0 * np.arcsin(np.sqrt(a))
rel = gc / dist - 1
print("sphere/WGS84 - 1 over 1-3000 km: min %.4f%%, max %.4f%%" % (100 * rel.min(), 100 * rel.max()))
