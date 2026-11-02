"""Does the MODIS cache key notice a value-changing edit in extract_points (outside the hashed function list)?"""
import sys, json, copy
root, sand = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
import pandas as pd
from mshi.config import load_config, Config
from mshi.data import modis as M
import mshi.netutil as N
from mshi.runlog import code_sha256
base = load_config("/home/user/MSHI/configs/v3.yaml")
d = copy.deepcopy(base.data)
for k in ("interim", "results"):
    d["paths"][k] = f"{sand}/{k}"
cfg = Config(d, source=base.source)
pts = pd.DataFrame({"lat": [45.0, 45.01], "lon": [10.0, 10.02]})
pts["site_key"] = M.site_key(pts.lat, pts.lon).values
M.modis_point_set = lambda c: pts
N.check_reachable = lambda *a, **k: None
from types import SimpleNamespace
from datetime import datetime, timezone
class Cat:
    def search(self, collections, **kw):
        w = datetime(2021, 1, 1, tzinfo=timezone.utc)
        if collections[0].startswith("modis-17"):
            its = [SimpleNamespace(id=f"MOD17A3HGF.A{y}", datetime=w, properties={}, assets={"Npp_500m": SimpleNamespace(href=f"mem://{y}")}) for y in range(2020, 2025)]
        else:
            its = [SimpleNamespace(id="MOD11A2.A2021001", datetime=w, properties={}, assets={"LST_Day_1km": SimpleNamespace(href="mem://d"), "LST_Night_1km": SimpleNamespace(href="mem://n")})]
        return SimpleNamespace(item_collection=lambda: its)
import pystac_client
pystac_client.Client.open = staticmethod(lambda *a, **k: Cat())
M.TokenCache.get = lambda self, force=False: "tok"
M.read_windows = lambda href, sub, kind, m: {k: 100.0 for k in sub.site_key}
r = M.modis_points(cfg)
df = M.load_modis_points(cfg)
prov = json.loads(open(f"{sand}/results/modis_points.json").read())["_provenance"]["code_sha256"][:12]
print(f"package={root.split('/')[-1]} code_sha256={code_sha256()[:12]} key.code={r['cache_key']['code_sha256'][:12]} cached={r.get('cached', False)} npp={df.npp.tolist()} json_prov={prov}")
