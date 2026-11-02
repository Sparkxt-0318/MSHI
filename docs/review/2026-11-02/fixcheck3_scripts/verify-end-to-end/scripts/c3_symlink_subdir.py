"""Claim 3: Config.root_key (a6c00bc) raises for outputs under a symlinked sub-directory of a path root.

Run: GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 /home/user/MSHI/.venv/bin/python -I -B c3_symlink_subdir.py V PKG LAYOUT LABEL
  PKG    = new (the checked-out package, /home/user/MSHI) | old (git archive 9e17a36 in V/old9e)
  LAYOUT = subdir   (raw/worldclim and raw/soilgrids are symlinks to V/c3/<LABEL>/bigdisk/...)
           plain    (no symlinks)
           rootlink (raw itself is a symlink to V/c3/<LABEL>/elsewhere/raw)
Only mshi.data.rasters.download is faked (synthetic zip / TIFF-magic bytes); the network is guarded.
"""
import copy
import io
import json
import sys
import zipfile
from pathlib import Path

V = Path(sys.argv[1])
PKG, LAYOUT, LABEL = sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, str(V / "old9e") if PKG == "old" else "/home/user/MSHI")

import requests  # noqa: E402


def guard(self, request, **kw):
    raise requests.exceptions.ConnectionError(f"verify network guard: refused {request.url}")


requests.sessions.Session.send = guard

import mshi  # noqa: E402
from mshi.config import Config, load_config  # noqa: E402
import mshi.data.rasters as RA  # noqa: E402
import mshi.run as R  # noqa: E402

assert Path(mshi.__file__).resolve().parents[1] == (V / "old9e" if PKG == "old" else Path("/home/user/MSHI")), mshi.__file__

DOWNLOADS = []


def fake_download(url, dest, sha256=None, retries=4, timeout=600, session=None, params=None,
                  reuse_existing=False, sleep=None):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if params and "COVERAGEID" in params:
        body = b"II*\x00" + params["COVERAGEID"].encode() * 2000          # TIFF magic, > min_valid_bytes
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for i in range(1, 20):
                zi = zipfile.ZipInfo(f"wc2.1_2.5m_bio_{i}.tif", date_time=(2020, 1, 1, 0, 0, 0))
                z.writestr(zi, b"II*\x00" + f"layer{i}".encode() * 100)
        body = buf.getvalue()
    if dest.exists() and reuse_existing and not sha256:
        return {"path": str(dest), "sha256": None, "downloaded": False}
    dest.write_bytes(body)
    DOWNLOADS.append(dest.name)
    import hashlib
    return {"path": str(dest), "sha256": hashlib.sha256(body).hexdigest(), "downloaded": True}


RA.download = fake_download

root = V / "c3" / LABEL
root.mkdir(parents=True, exist_ok=True)
base = load_config()
data = copy.deepcopy(base.data)
for r in ("raw", "interim", "derived", "results", "figures"):
    data["paths"][r] = str(root / "sb" / r)
raw = root / "sb" / "raw"
if LAYOUT == "subdir":
    raw.mkdir(parents=True, exist_ok=True)
    for name in ("worldclim", "soilgrids"):
        (root / "bigdisk" / name).mkdir(parents=True, exist_ok=True)
        if not raw.joinpath(name).is_symlink():
            raw.joinpath(name).symlink_to(root / "bigdisk" / name, target_is_directory=True)
elif LAYOUT == "rootlink":
    (root / "elsewhere" / "raw").mkdir(parents=True, exist_ok=True)
    (root / "sb").mkdir(parents=True, exist_ok=True)
    if not raw.is_symlink():
        raw.symlink_to(root / "elsewhere" / "raw", target_is_directory=True)
else:
    raw.mkdir(parents=True, exist_ok=True)
cfg = Config(data, source=base.source)          # out_root None: not a smoke run

code = R.run(["fetch_worldclim", "fetch_soilgrids"], cfg)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
out = {"pkg": PKG, "layout": LAYOUT, "label": LABEL, "exit": code, "downloads": DOWNLOADS,
       "stages": [(r["stage"], r["status"][:400]) for r in recs[-2:]]}
for name in ("fetch_worldclim.json", "fetch_soilgrids.json"):
    p = cfg.path("results", name)
    if p.exists():
        j = json.loads(p.read_text())
        out[name] = {"_outputs_keys": sorted(j.get("_outputs", {}))[:3], "n_outputs": len(j.get("_outputs", {}))}
        if PKG == "new":
            from mshi.io import result_staleness
            out[name]["staleness"] = result_staleness(cfg, j)
    else:
        out[name] = "not written"
if PKG == "new":
    from mshi.data.rasters import worldclim_path
    try:
        out["root_key_tif1"] = cfg.root_key(worldclim_path(cfg, 1))
    except ValueError as e:
        out["root_key_tif1"] = f"ValueError: {e}"
print(json.dumps(out, indent=1))
(V / "logs" / f"c3_{LABEL}.json").write_text(json.dumps(out, indent=1))
