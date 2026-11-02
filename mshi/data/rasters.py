"""Fetch stages for gridded sources: WorldClim 2.1 (2.5') and SoilGrids 2.0 (0.05 deg WCS).

Ports of the handoff downloads (``get_soilgrids05.py``; WorldClim was fetched by hand in the
prototype). Raw rasters go to data/raw/ (gitignored) and are never committed: WorldClim's terms
restrict redistribution [UNVERIFIED: worldclim.org could not be reached from this environment].

Each download has a ``*.source.json`` sidecar recording the request that produced it (SHA-256 of the
configured source fields that determine the bytes) and the file hashes. A file is reused only if its
sidecar matches the current configuration and its bytes still match; otherwise it is fetched again. So a
config edit (another SoilGrids depth or statistic, another WorldClim URL or pinned hash) takes effect, and
a replaced file is not reused silently. The stage results record every raster as an output, and the
``features`` stage refuses rasters that are not those outputs (mshi.io.require_outputs).
"""
from __future__ import annotations

import logging
import zipfile

import requests

from ..config import Config, canonical_sha256
from ..io import read_json, sha256_file, write_json, write_result
from ..netutil import DownloadError, download

log = logging.getLogger("mshi.rasters")

# source fields that determine the downloaded bytes (others, e.g. scale or description, do not)
WORLDCLIM_REQUEST = ("version", "resolution", "url", "sha256", "file_pattern")
SOILGRIDS_REQUEST = ("version", "wcs_url", "depth", "statistic", "lon", "lat", "size", "file_pattern")
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
    out_dir = worldclim_dir(cfg)
    tifs = [worldclim_path(cfg, i) for i in range(1, n + 1)]
    zpath = out_dir.parent / w["url"].rsplit("/", 1)[-1]
    side = out_dir / "worldclim.source.json"
    zside = zpath.with_name(zpath.name + ".source.json")
    request = _request_sha256(w, WORLDCLIM_REQUEST, n_layers=n)
    if not _sidecar_ok(side, request, tifs):
        side.unlink(missing_ok=True)
        for t in tifs:
            t.unlink(missing_ok=True)
        # the zip is reused only if its own sidecar says it was downloaded for this request and is unchanged
        # (WorldClim publishes no checksum; a pinned ``sha256`` is verified by ``download``)
        if not _sidecar_ok(zside, request, [zpath]):
            zside.unlink(missing_ok=True)
            zpath.unlink(missing_ok=True)
            download(w["url"], zpath, sha256=w.get("sha256"))
            write_json({"request_sha256": request, "url": w["url"], "sha256": {zpath.name: sha256_file(zpath)}},
                       zside)
        with zipfile.ZipFile(zpath) as z:
            for t in tifs:
                z.extract(t.name, out_dir)
        write_json({"request_sha256": request, "url": w["url"], "zip_sha256": sha256_file(zpath),
                    "sha256": {t.name: sha256_file(t) for t in tifs}}, side)
    rec = read_json(side)
    if w.get("sha256") is None:
        log.warning("WorldClim zip hash is not pinned in configs/v3.yaml; recorded %s", rec["zip_sha256"])
    elif rec["zip_sha256"] != w["sha256"]:      # cannot happen after a fresh download (verified there)
        raise DownloadError(f"{side}: layers come from a zip with SHA-256 {rec['zip_sha256']}, not the pinned "
                            f"{w['sha256']}; delete {out_dir} and re-run")
    res = {"source": "worldclim", "version": w["version"], "resolution": w["resolution"], "url": w["url"],
           "request_sha256": request, "zip_sha256": rec["zip_sha256"], "zip_sha256_pinned": w.get("sha256"),
           "tif_sha256": {t.name: sha256_file(t) for t in tifs}}
    write_result(cfg, res, "fetch_worldclim.json", outputs=tifs)
    return res


def fetch_soilgrids(cfg: Config) -> dict:
    sg = cfg["sources"]["soilgrids"]
    files, paths = {}, []
    s = requests.Session()
    for v in sg["variables"]:
        p = soilgrids_path(cfg, v)
        side = p.with_name(p.name + ".source.json")
        params = {"map": f"/map/{v}.map", "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "GetCoverage",
                  "COVERAGEID": f"{v}_{sg['depth']}_{sg['statistic']}", "FORMAT": "image/tiff",
                  "SUBSET": [f"long({sg['lon'][0]},{sg['lon'][1]})", f"lat({sg['lat'][0]},{sg['lat'][1]})"],
                  "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
                  "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
                  "SCALESIZE": f"long({sg['size'][0]}),lat({sg['size'][1]})"}
        request = _request_sha256(sg, SOILGRIDS_REQUEST, var=v)
        if not _sidecar_ok(side, request, [p]):
            side.unlink(missing_ok=True)
            p.unlink(missing_ok=True)
            download(sg["wcs_url"], p, params=params, session=s)
            with open(p, "rb") as fh:
                head = fh.read(200)
            if head[:4] not in TIFF_MAGIC or p.stat().st_size <= sg["min_valid_bytes"]:
                p.unlink()
                raise DownloadError(f"SoilGrids WCS returned a non-TIFF or truncated response for {v}: "
                                    f"{head.decode('utf-8', 'replace')!r}")
            write_json({"request_sha256": request, "params": params, "sha256": {p.name: sha256_file(p)}}, side)
        files[p.name] = sha256_file(p)
        paths.append(p)
    res = {"source": "soilgrids", "version": sg["version"], "wcs_url": sg["wcs_url"], "depth": sg["depth"],
           "statistic": sg["statistic"], "size": sg["size"], "files_sha256": files}
    write_result(cfg, res, "fetch_soilgrids.json", outputs=paths)
    return res
