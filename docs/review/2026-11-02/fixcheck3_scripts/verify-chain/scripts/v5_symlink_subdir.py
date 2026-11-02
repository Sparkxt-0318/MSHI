"""Claim 5: Config.root_key resolves symlinks. Does an output in a symlinked sub-directory of a root (pointing
outside every root) make fetch_worldclim / features error? Controls: plain layout; whole raw root symlinked.
Non-smoke sandboxes; the WorldClim download is a local zip (download patched; no network)."""
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.CRITICAL)
import mshi.data.rasters as RA  # noqa: E402
import mshi.run as R  # noqa: E402
from mshi.data.features import verify_inputs  # noqa: E402

base = vc.reset(vc.WORK / "v5")
src = base / "wc_src.zip"
with zipfile.ZipFile(src, "w") as z:
    for i in range(1, 20):
        z.writestr(vc.CFG["sources"]["worldclim"]["file_pattern"].format(i=i), f"layer {i}")
calls = []


def fake_download(url, dest, sha256=None, **k):
    calls.append(url)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return {"path": str(dest), "sha256": None, "downloaded": True}


RA.download = fake_download


def case(name, layout):
    root = vc.reset(base / name)
    s = vc.full_sand(root / "s")
    layout(s, root)
    n = len(vc.runlog(s))
    code = R.run(["fetch_worldclim"], s)
    st = vc.statuses(s, n)["fetch_worldclim"].replace(str(base), "<v5>")
    tif = RA.worldclim_path(s, 1)
    print(f"[{name}] fetch_worldclim exit {code}: {st[:260]}")
    print(f"    layer 1 on disk: {tif.exists()} (resolved under <v5>/{tif.resolve().relative_to(base)})")
    return s


def plain(s, root):
    pass


def sub_link(s, root):            # data/raw/worldclim -> a shared download store outside every root
    store = root / "shared_store" / "worldclim"
    store.mkdir(parents=True)
    s.path("raw").mkdir(parents=True)
    os.symlink(store, s.path("raw", "worldclim"))


def root_link(s, root):           # the whole raw root is a symlink
    store = root / "shared_raw"
    store.mkdir(parents=True)
    Path(s.path("raw")).parent.mkdir(parents=True, exist_ok=True)
    os.symlink(store, s.path("raw"))


case("plain", plain)
s = case("subdir_symlink", sub_link)
case("root_symlink", root_link)
# with the files already in the shared store (fetched by another checkout), the stage still errors, and
# features' input check raises the same error
n = len(vc.runlog(s))
print("[subdir_symlink] second run (files present): exit", R.run(["fetch_worldclim"], s),
      vc.statuses(s, n)["fetch_worldclim"][:60], "| downloads so far:", len(calls))
try:
    s.root_key(RA.worldclim_path(s, 1))
except ValueError as e:
    print("root_key ValueError:", str(e).replace(str(base), "<v5>")[:200])
