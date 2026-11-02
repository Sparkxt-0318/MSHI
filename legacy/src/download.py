"""
download.py — MSHI-Geo data acquisition module (v2: soil respiration target).

Downloads and stages all input datasets required for MSHI-Geo training
and inference. Prints clear manual-download instructions for sources
that require Earthdata authentication or are not amenable to scripted
download.

Run:
    python src/download.py --target cosore
    python src/download.py --target soilgrids --vars soc,nitrogen,phh2o
    python src/download.py --target worldclim
    python src/download.py --target all     # attempt all
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import requests
from tqdm import tqdm


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Source registry (UPDATED for soil respiration target)
# ─────────────────────────────────────────────────────────────────────────────
SOURCES = {
    "cosore": {
        "name": "COSORE — A community database of continuous soil respiration",
        "url": "https://github.com/bpbond/cosore",
        "files": ["cosore_data.csv", "cosore_metadata.csv"],
        "instructions": (
            "COSORE (Bond-Lamberty et al. 2020, Glob. Change Biol.) is a structured\n"
            "database of continuous in-situ soil respiration measurements (~28,000 records).\n\n"
            "OPTION A — R package (recommended for cleanest schema):\n"
            "    install.packages('cosore')   # in R\n"
            "    library(cosore)\n"
            "    db <- csr_database()         # download all\n"
            "    write.csv(db$DESCRIPTION, 'data/raw/cosore/description.csv')\n"
            "    # then export the per-site flux time-series similarly\n\n"
            "OPTION B — Direct download:\n"
            "    1) Visit https://github.com/bpbond/cosore\n"
            "    2) Look for the latest CSV release in 'data-raw/' or in releases.\n"
            "    3) Place files at data/raw/cosore/\n\n"
            "Citation: Bond-Lamberty B et al. 2020. COSORE: A community database for\n"
            "continuous soil respiration and other soil-atmosphere greenhouse gas flux\n"
            "data. Global Change Biology 26: 7268-7283. doi:10.1111/gcb.15353\n"
        ),
    },
    "srdb": {
        "name": "SRDB — Soil Respiration Database (V5)",
        "url": "https://github.com/bpbond/srdb",
        "files": ["srdb-data.csv", "srdb-studies.csv"],
        "instructions": (
            "SRDB (Bond-Lamberty & Thomson 2010, updated through V5) is the canonical\n"
            "compilation of annual and seasonal soil respiration estimates from the\n"
            "literature (~10,000 records). Complements COSORE; we use both.\n\n"
            "DOWNLOAD:\n"
            "    1) Visit https://github.com/bpbond/srdb\n"
            "    2) Download srdb-data.csv (data) and srdb-studies.csv (metadata)\n"
            "    3) Place at data/raw/srdb/\n\n"
            "The key column for our target is 'Rs_annual' (annual soil respiration,\n"
            "g C m-2 yr-1). Filter to records with Rs_annual not null and reasonable\n"
            "ecosystem types.\n\n"
            "Citation: Bond-Lamberty B, Thomson A. 2010. A global database of soil\n"
            "respiration data. Biogeosciences 7: 1915-1926.\n"
        ),
    },
    "soilgrids": {
        "name": "ISRIC SoilGrids 2.0 (5-15cm topsoil mean)",
        "url": "https://maps.isric.org/",
        "files": [
            "soc_5-15cm_asia_5km.tif", "nitrogen_5-15cm_asia_5km.tif",
            "phh2o_5-15cm_asia_5km.tif", "clay_5-15cm_asia_5km.tif",
            "sand_5-15cm_asia_5km.tif", "silt_5-15cm_asia_5km.tif",
            "bdod_5-15cm_asia_5km.tif", "cec_5-15cm_asia_5km.tif",
        ],
        "instructions": (
            "SoilGrids 2.0 supports OGC WCS for bbox extraction.\n"
            "Coverage IDs use depth slices (0-5cm, 5-15cm, 15-30cm, ...);\n"
            "this script grabs the 5-15cm topsoil mean as the canonical layer.\n"
            "Two tiles per variable are saved: Asia bbox and US bbox at ~5km.\n\n"
            "If WCS fails, fall back to the soilgrids Python package:\n"
            "    pip install soilgrids\n"
            "    soilgrids --service WCS --map_service phh2o \\\n"
            "             --coverage_id phh2o_5-15cm_mean --bbox 25 -10 180 80 \\\n"
            "             --output data/raw/soilgrids/phh2o_asia.tif\n"
        ),
    },
    "worldclim": {
        "name": "WorldClim 2.1 bioclimatic variables (1km)",
        "url": "https://worldclim.org/data/worldclim21.html",
        "files": ["wc2.1_30s_bio.zip"],
        "instructions": (
            "1) Visit https://worldclim.org/data/worldclim21.html\n"
            "2) Download 'Bioclimatic variables' at 30 arc-seconds (~1 km).\n"
            "3) Unzip into data/raw/worldclim/  (yields wc2.1_30s_bio_1.tif ... bio_19.tif)\n"
            "Citation: Fick SE, Hijmans RJ. 2017. International Journal of Climatology 37:4302-4315.\n"
        ),
    },
    "modis_npp": {
        "name": "MODIS MOD17A3HGF annual NPP",
        "url": "https://lpdaac.usgs.gov/products/mod17a3hgfv061/",
        "files": [],
        "instructions": (
            "Recommended path: Google Earth Engine — fastest mosaicking.\n\n"
            "GEE example (paste in code.earthengine.google.com):\n"
            "    var asia = ee.Geometry.Rectangle([25, -10, 180, 80]);\n"
            "    var npp = ee.ImageCollection('MODIS/061/MOD17A3HGF')\n"
            "                .filterDate('2020-01-01','2024-12-31')\n"
            "                .select('Npp').mean();\n"
            "    Export.image.toDrive({image: npp.clip(asia), region: asia,\n"
            "                          scale: 1000, fileFormat:'GeoTIFF',\n"
            "                          description:'modis_npp_asia_2020_2024'});\n\n"
            "Save the resulting GeoTIFF to data/raw/modis/npp_2020_2024_mean.tif\n"
        ),
    },
    "modis_lst": {
        "name": "MODIS MOD11A2 land surface temperature",
        "url": "https://lpdaac.usgs.gov/products/mod11a2v061/",
        "files": [],
        "instructions": (
            "Same GEE pattern as NPP, but using MODIS/061/MOD11A2 collection,\n"
            "extracting LST_Day_1km and LST_Night_1km bands separately.\n"
            "Output to data/raw/modis/lst_day_2020_2024_mean.tif and lst_night_*.tif\n"
        ),
    },
    "modis_landcover": {
        "name": "MODIS MCD12Q1 IGBP land cover",
        "url": "https://lpdaac.usgs.gov/products/mcd12q1v061/",
        "files": [],
        "instructions": (
            "GEE: ee.ImageCollection('MODIS/061/MCD12Q1').filterDate('2023-01-01','2023-12-31')\n"
            "     .first().select('LC_Type1')\n"
            "Export to data/raw/modis/landcover_igbp_2023.tif\n"
        ),
    },
    "borders": {
        "name": "Natural Earth — admin_0 country borders (50m resolution)",
        "url": "https://www.naturalearthdata.com/downloads/",
        "files": ["ne_50m_admin_0_countries.shp"],
        "instructions": (
            "1) Visit https://www.naturalearthdata.com/downloads/50m-cultural-vectors/\n"
            "2) Download '50m admin 0 countries' (zip).\n"
            "3) Unzip into data/raw/borders/\n"
            "Used by hero_map.py for country-border overlay.\n"
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Generic utilities
# ─────────────────────────────────────────────────────────────────────────────
def _download_file(url: str, dest: Path, chunk: int = 1024 * 256) -> bool:
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f, tqdm(
                total=total, unit="B", unit_scale=True, desc=dest.name
            ) as pbar:
                for buf in r.iter_content(chunk_size=chunk):
                    f.write(buf)
                    pbar.update(len(buf))
        return True
    except Exception as e:
        print(f"[download] FAILED {url}: {e}", file=sys.stderr)
        return False


def download_soilgrids_wcs(
    variable: str, bbox: List[float],
    out_path: Path, depth: str = "5-15cm", stat: str = "mean",
    pixel_size_deg: float = 0.05,
) -> bool:
    """
    Fetch a SoilGrids 2.0 layer over a bbox via the OGC WCS endpoint.

    SoilGrids 2.0 only exposes per-depth slices (0-5, 5-15, 15-30, ... cm).
    The default 5-15cm topsoil mean is the canonical layer for plant/microbial
    activity studies. We use SCALESIZE (pixel counts) rather than RESOLUTION,
    since mapserver interprets RESOLUTION ambiguously over EPSG:4326.
    """
    coverage_id = f"{variable}_{depth}_{stat}"
    base = "https://maps.isric.org/mapserv"
    width  = max(1, int(round((bbox[2] - bbox[0]) / pixel_size_deg)))
    height = max(1, int(round((bbox[3] - bbox[1]) / pixel_size_deg)))
    params = {
        "map": f"/map/{variable}.map",
        "SERVICE": "WCS", "VERSION": "2.0.1",
        "REQUEST": "GetCoverage", "COVERAGEID": coverage_id,
        "FORMAT": "image/tiff",
        "SUBSET": [f"long({bbox[0]},{bbox[2]})", f"lat({bbox[1]},{bbox[3]})"],
        "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
        "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
        "SCALESIZE": f"long({width}),lat({height})",
    }
    print(f"[soilgrids] requesting {coverage_id} bbox={bbox} ({width}x{height} px)")
    try:
        r = requests.get(base, params=params, stream=True, timeout=300)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "")
        if "xml" in ctype.lower():
            body = r.content.decode("utf-8", errors="replace")[:400]
            print(f"[soilgrids] server returned XML error: {body}", file=sys.stderr)
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for buf in r.iter_content(chunk_size=1024 * 256):
                f.write(buf)
        print(f"[soilgrids] saved {out_path}  ({out_path.stat().st_size/1e6:.1f} MB)")
        return True
    except Exception as e:
        print(f"[soilgrids] FAILED for {coverage_id}: {e}", file=sys.stderr)
        return False


def print_instructions(target: str) -> None:
    if target not in SOURCES:
        print(f"Unknown source: {target}", file=sys.stderr)
        return
    src = SOURCES[target]
    print(f"\n=== {src['name']} ===")
    print(f"URL: {src['url']}")
    print()
    print(src["instructions"])
    print(f"Place files in: {RAW / target}/")
    print()


def print_all_instructions() -> None:
    print("MSHI-Geo data acquisition checklist (v2: soil respiration target)")
    print("=" * 70)
    for key in SOURCES:
        print_instructions(key)


SOILGRIDS_VARS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
ASIA_BBOX = [25.0, -10.0, 180.0, 80.0]
US_BBOX   = [-125.0, 24.0, -66.0, 50.0]


def _fetch_soilgrids_region(region: str, bbox: List[float], variables: List[str],
                            pixel_size_deg: float, depth: str = "5-15cm") -> int:
    n_ok = 0
    for v in variables:
        out = RAW / "soilgrids" / f"{v}_{depth}_{region}_5km.tif"
        if out.exists() and out.stat().st_size > 1024:
            print(f"  · {v} ({region}): already present, skipping")
            n_ok += 1
            continue
        if download_soilgrids_wcs(v, bbox, out, depth=depth,
                                  pixel_size_deg=pixel_size_deg):
            n_ok += 1
    return n_ok


def main() -> int:
    p = argparse.ArgumentParser(description="MSHI-Geo data downloader")
    p.add_argument("--target", default="all",
                   choices=list(SOURCES.keys()) + ["all", "instructions"])
    p.add_argument("--bbox", nargs=4, type=float, default=ASIA_BBOX)
    p.add_argument("--pixel-size-deg", type=float, default=0.05,
                   help="Output pixel size in degrees (~0.05 ≈ 5 km)")
    p.add_argument("--vars", type=str, default="")
    args = p.parse_args()

    if args.target == "instructions":
        print_all_instructions()
        return 0

    if args.target == "all":
        print_all_instructions()
        print("\nAttempting automated SoilGrids download for Asia + US bboxes...")
        n1 = _fetch_soilgrids_region("asia", ASIA_BBOX, SOILGRIDS_VARS, args.pixel_size_deg)
        n2 = _fetch_soilgrids_region("us",   US_BBOX,   SOILGRIDS_VARS, args.pixel_size_deg)
        print(f"\nSoilGrids: {n1}/{len(SOILGRIDS_VARS)} Asia layers, "
              f"{n2}/{len(SOILGRIDS_VARS)} US layers fetched.")
        return 0

    if args.target == "soilgrids":
        variables = [v.strip() for v in args.vars.split(",")] if args.vars else SOILGRIDS_VARS
        _fetch_soilgrids_region("asia", ASIA_BBOX, variables, args.pixel_size_deg)
        _fetch_soilgrids_region("us",   US_BBOX,   variables, args.pixel_size_deg)
        return 0

    print_instructions(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
