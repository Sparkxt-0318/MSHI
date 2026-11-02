import sys, requests
from pathlib import Path
out = Path(sys.argv[1])
for v in ["soc","nitrogen","phh2o","clay","sand","silt","bdod","cec"]:
    p = out / f"{v}_5-15cm_global_0p05.tif"
    if p.exists() and p.stat().st_size > 10000: continue
    params = {"map": f"/map/{v}.map", "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "GetCoverage",
              "COVERAGEID": f"{v}_5-15cm_mean", "FORMAT": "image/tiff",
              "SUBSET": ["long(-180,180)", "lat(-56,82.7)"],
              "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
              "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
              "SCALESIZE": "long(7200),lat(2774)"}
    r = requests.get("https://maps.isric.org/mapserv", params=params, timeout=600)
    print(v, r.status_code, r.headers.get("Content-Type"), len(r.content))
    if "tiff" in r.headers.get("Content-Type", ""): p.write_bytes(r.content)
