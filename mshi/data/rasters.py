"""Fetch stages for gridded sources: WorldClim 2.1 (2.5') and SoilGrids 2.0 (0.05 deg WCS).

Ports of the handoff downloads (``get_soilgrids05.py``; WorldClim was fetched by hand in the
prototype). Raw rasters go to data/raw/ (gitignored) and are never committed: WorldClim's terms
restrict redistribution [UNVERIFIED: worldclim.org could not be reached from this environment].

Each download has a ``*.source.json`` sidecar recording the request that produced it and the file hashes.
A file is reused only if its sidecar matches the current request and its bytes still match; otherwise it is
fetched again. The request covers what determines the bytes: for SoilGrids the WCS URL and the full
parameter set as built by the code (so a config edit, e.g. another depth or statistic, or a code change to
the request takes effect); for WorldClim the zip's URL, version and resolution, and for the extracted layers
the zip's hash, the file pattern and the number of layers. Data already on disk are replaced only after a
complete, verified download (``download`` writes to a temporary file), so a failed or blocked re-fetch never
leaves the stage without its previous files; a pinned WorldClim hash that the zip on disk already has needs
no request. The stage results record every raster as an output, and the ``features`` stage refuses rasters
that are not those outputs (mshi.io.require_outputs).
"""
from __future__ import annotations

import logging
import os
import zipfile

import requests

from ..config import Config, canonical_sha256
from ..io import read_json, sha256_file, write_json, write_result
from ..netutil import DownloadError, download

log = logging.getLogger("mshi.rasters")

# source fields that determine the downloaded zip's bytes, and the extracted layers (others, e.g. the pinned
# hash, which is verified, or the description, do not)
WORLDCLIM_ZIP_REQUEST = ("version", "resolution", "url")
WORLDCLIM_LAYER_REQUEST = ("file_pattern",)
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def worldclim_dir(cfg: Config):
    w = cfg["sources"]["worldclim"]
    return cfg.path("raw", "worldclim", w["version"], w["resolution"])


def worldclim_path(cfg: Config, i: int):
    return worldclim_dir(cfg) / cfg["sources"]["worldclim"]["file_pattern"].format(i=i)


def soilgrids_path(cfg: Config, var: str):
    sg = cfg["sources"]["soilgrids"]
    name = sg["file_pattern"].format(var=var, depth=sg["depth"], statistic=sg["statistic"])
    return cfg.path("raw", "soilgrids", sg["version"], "0p05", name)


def _request_sha256(src: dict, fields, **extra) -> str:
    return canonical_sha256({**{k: src.get(k) for k in fields}, **extra})


def _sidecar_ok(side, request: str, files) -> bool:
    """True if ``side`` records ``request`` and every file in ``files`` exists with its recorded hash."""
    if not side.exists():
        return False
    rec = read_json(side)
    return (rec.get("request_sha256") == request
            and all(f.exists() and rec.get("sha256", {}).get(f.name) == sha256_file(f) for f in files))


def fetch_worldclim(cfg: Config) -> dict:
    w = cfg["sources"]["worldclim"]
    n = cfg["features"]["worldclim_vars"]
    pin = w.get("sha256")
    out_dir = worldclim_dir(cfg)
    tifs = [worldclim_path(cfg, i) for i in range(1, n + 1)]
    zpath = out_dir.parent / w["url"].rsplit("/", 1)[-1]
    side = out_dir / "worldclim.source.json"
    zside = zpath.with_name(zpath.name + ".source.json")
    zreq = _request_sha256(w, WORLDCLIM_ZIP_REQUEST)
    zip_ok = _sidecar_ok(zside, zreq, [zpath]) and (pin is None or read_json(zside)["sha256"][zpath.name] == pin)
    if not zip_ok:
        # replaces the zip on disk only after a complete download that matches the pin (if any); a zip that
        # already has the pinned hash is kept without a request (download skips it)
        info = download(w["url"], zpath, sha256=pin)
        write_json({"request_sha256": zreq, "url": w["url"], "sha256": {zpath.name: info["sha256"]}}, zside)
    zip_sha = read_json(zside)["sha256"][zpath.name]
    lreq = _request_sha256(w, WORLDCLIM_LAYER_REQUEST, n_layers=n, zip_sha256=zip_sha)
    if not _sidecar_ok(side, lreq, tifs):
        side.unlink(missing_ok=True)
        with zipfile.ZipFile(zpath) as z:
            for t in tifs:
                z.extract(t.name, out_dir)
        write_json({"request_sha256": lreq, "url": w["url"], "zip_sha256": zip_sha,
                    "sha256": {t.name: sha256_file(t) for t in tifs}}, side)
    if pin is None:
        log.warning("WorldClim zip hash is not pinned in configs/v3.yaml; recorded %s", zip_sha)
    res = {"source": "worldclim", "version": w["version"], "resolution": w["resolution"], "url": w["url"],
           "request_sha256": zreq, "zip_sha256": zip_sha, "zip_sha256_pinned": pin,
           "tif_sha256": {t.name: sha256_file(t) for t in tifs}}
    write_result(cfg, res, "fetch_worldclim.json", outputs=tifs)
    return res


def soilgrids_params(sg: dict, var: str) -> dict:
    """WCS GetCoverage parameters for one variable (part of the request hash)."""
    return {"map": f"/map/{var}.map", "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "GetCoverage",
            "COVERAGEID": f"{var}_{sg['depth']}_{sg['statistic']}", "FORMAT": "image/tiff",
            "SUBSET": [f"long({sg['lon'][0]},{sg['lon'][1]})", f"lat({sg['lat'][0]},{sg['lat'][1]})"],
            "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
            "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
            "SCALESIZE": f"long({sg['size'][0]}),lat({sg['size'][1]})"}


def fetch_soilgrids(cfg: Config) -> dict:
    sg = cfg["sources"]["soilgrids"]
    files, paths = {}, []
    s = requests.Session()
    for v in sg["variables"]:
        p = soilgrids_path(cfg, v)
        side = p.with_name(p.name + ".source.json")
        params = soilgrids_params(sg, v)
        request = canonical_sha256({"version": sg["version"], "wcs_url": sg["wcs_url"], "params": params,
                                    "file": p.name})
        if not _sidecar_ok(side, request, [p]):
            new = p.with_name(p.name + ".new")          # the file on disk is replaced only by a valid download
            new.unlink(missing_ok=True)
            download(sg["wcs_url"], new, params=params, session=s)
            with open(new, "rb") as fh:
                head = fh.read(200)
            if head[:4] not in TIFF_MAGIC or new.stat().st_size <= sg["min_valid_bytes"]:
                new.unlink()
                raise DownloadError(f"SoilGrids WCS returned a non-TIFF or truncated response for {v}: "
                                    f"{head.decode('utf-8', 'replace')!r}")
            side.unlink(missing_ok=True)
            os.replace(new, p)
            write_json({"request_sha256": request, "params": params, "sha256": {p.name: sha256_file(p)}}, side)
        files[p.name] = sha256_file(p)
        paths.append(p)
    res = {"source": "soilgrids", "version": sg["version"], "wcs_url": sg["wcs_url"], "depth": sg["depth"],
           "statistic": sg["statistic"], "size": sg["size"], "files_sha256": files}
    write_result(cfg, res, "fetch_soilgrids.json", outputs=paths)
    return res
