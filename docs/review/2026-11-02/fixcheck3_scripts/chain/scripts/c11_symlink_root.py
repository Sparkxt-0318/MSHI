"""root_key resolves symlinks: an output reached through a symlinked sub-directory of a root (e.g.
data/raw/worldclim -> a shared download store) is 'not under any configured path root'."""
import sys, json, os, zipfile, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import numpy as np
import cc, author
logging.basicConfig(level=logging.WARNING)
from mshi.run import run
from mshi.data import rasters as RA
from mshi.io import write_json, sha256_file
base = cc.SCR / "work" / "c11"
cc.reset(base)

def prepare(sand, shared=None):
    """A cached WorldClim zip (+ its sidecar for this request), so fetch_worldclim needs no network."""
    w = sand["sources"]["worldclim"]
    n = sand["features"]["worldclim_vars"]
    wdir = sand.path("raw", "worldclim")
    if shared:
        shared.mkdir(parents=True, exist_ok=True)
        wdir.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(shared, wdir)                     # data/raw/worldclim -> shared store
    out_dir = RA.worldclim_dir(sand)
    zpath = out_dir.parent / w["url"].rsplit("/", 1)[-1]
    zpath.parent.mkdir(parents=True, exist_ok=True)
    tmp = base / "tif_src"
    tmp.mkdir(exist_ok=True)
    with zipfile.ZipFile(zpath, "w") as z:
        for i in range(1, n + 1):
            t = tmp / RA.worldclim_path(sand, i).name
            author.wgs_raster(t, np.full((180, 360), float(i)))
            z.write(t, t.name)
    request = RA._request_sha256(w, RA.WORLDCLIM_REQUEST, n_layers=n)
    write_json({"request_sha256": request, "url": w["url"], "sha256": {zpath.name: sha256_file(zpath)}},
               zpath.with_name(zpath.name + ".source.json"))

for tag, shared in [("plain", None), ("symlinked", base / "shared_store" / "worldclim")]:
    sand = cc.full_sand(tag, base=base)
    prepare(sand, shared)
    code = run(["fetch_worldclim"], sand)
    print(f"{tag}: exit {code}", cc.statuses(sand))
