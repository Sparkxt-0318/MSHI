"""Fetch stages for gridded sources: WorldClim 2.1 (2.5') and SoilGrids 2.0 (0.05 deg WCS).

Ports of the handoff downloads (``get_soilgrids05.py``; WorldClim was fetched by hand in the
prototype). Raw rasters go to data/raw/ (gitignored) and are never committed: WorldClim's terms
restrict redistribution [UNVERIFIED: worldclim.org could not be reached from this environment].
"""
from __future__ import annotations

import logging
import zipfile

import requests

from ..config import Config
from ..io import sha256_file, write_result
from ..netutil import DownloadError, download

log = logging.getLogger("mshi.rasters")


def worldclim_dir(cfg: Config):
    w = cfg["sources"]["worldclim"]
    return cfg.path("raw", "worldclim", w["version"], w["resolution"])


def worldclim_path(cfg: Config, i: int):
    return worldclim_dir(cfg) / cfg["sources"]["worldclim"]["file_pattern"].format(i=i)


def soilgrids_path(cfg: Config, var: str):
    sg = cfg["sources"]["soilgrids"]
    return cfg.path("raw", "soilgrids", sg["version"], "0p05", sg["file_pattern"].format(var=var))


def fetch_worldclim(cfg: Config) -> dict:
    w = cfg["sources"]["worldclim"]
    n = cfg["features"]["worldclim_vars"]
    out_dir = worldclim_dir(cfg)
    tifs = [worldclim_path(cfg, i) for i in range(1, n + 1)]
    zpath = out_dir.parent / w["url"].rsplit("/", 1)[-1]
    if not all(t.exists() for t in tifs):
        # unpinned (WorldClim publishes no checksum): an existing complete zip is reused (downloads are
        # written to .part and renamed only when complete), and its hash is recorded below
        download(w["url"], zpath, sha256=w.get("sha256"), reuse_existing=True)
        with zipfile.ZipFile(zpath) as z:
            for t in tifs:
                z.extract(t.name, out_dir)
    zip_sha = sha256_file(zpath) if zpath.exists() else None
    if w.get("sha256") is None:
        log.warning("WorldClim zip hash is not pinned in configs/v3.yaml; recorded %s", zip_sha)
    res = {"source": "worldclim", "version": w["version"], "resolution": w["resolution"], "url": w["url"],
           "zip_sha256": zip_sha, "zip_sha256_pinned": w.get("sha256"),
           "tif_sha256": {t.name: sha256_file(t) for t in tifs}}
    write_result(cfg, res, "fetch_worldclim.json")
    return res


def fetch_soilgrids(cfg: Config) -> dict:
    sg = cfg["sources"]["soilgrids"]
    files = {}
    s = requests.Session()
    for v in sg["variables"]:
        p = soilgrids_path(cfg, v)
        if not (p.exists() and p.stat().st_size > sg["min_valid_bytes"]):
            params = {"map": f"/map/{v}.map", "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "GetCoverage",
                      "COVERAGEID": f"{v}_{sg['depth']}_{sg['statistic']}", "FORMAT": "image/tiff",
                      "SUBSET": [f"long({sg['lon'][0]},{sg['lon'][1]})", f"lat({sg['lat'][0]},{sg['lat'][1]})"],
                      "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
                      "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
                      "SCALESIZE": f"long({sg['size'][0]}),lat({sg['size'][1]})"}
            download(sg["wcs_url"], p, params=params, session=s)
            with open(p, "rb") as fh:
                head = fh.read(200)
            if head[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
                p.unlink()
                raise DownloadError(f"SoilGrids WCS returned a non-TIFF response for {v}: "
                                    f"{head.decode('utf-8', 'replace')!r}")
        files[p.name] = sha256_file(p)
    res = {"source": "soilgrids", "version": sg["version"], "wcs_url": sg["wcs_url"], "depth": sg["depth"],
           "statistic": sg["statistic"], "size": sg["size"], "files_sha256": files}
    write_result(cfg, res, "fetch_soilgrids.json")
    return res
