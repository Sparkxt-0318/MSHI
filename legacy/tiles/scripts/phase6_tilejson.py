"""
Generate a TileJSON 3.0 manifest describing the PMTiles archive.
Also writes a minimal MapLibre HTML viewer that loads the layer
from a local pmtiles server.

These are deliverables for Night 2 MSHI-WEB integration.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PMT = ROOT / "tiles" / "mshi_f_npp_anomaly.pmtiles"
OUT_TILEJSON = ROOT / "tiles" / "tilejson.json"
OUT_HTML = ROOT / "tiles" / "viewer.html"


def main() -> int:
    # Pull metadata from the PMTiles file
    p = subprocess.run(["pmtiles", "show", str(PMT)],
                        capture_output=True, text=True)
    out = p.stdout

    # Parse the bounds and zoom from pmtiles show output
    bounds = None
    min_zoom = max_zoom = None
    for line in out.split("\n"):
        if "bounds:" in line.lower():
            import re
            nums = [float(x) for x in re.findall(r"-?\d+\.\d+", line)]
            if len(nums) >= 4:
                bounds = nums[:4]
        elif "min zoom:" in line.lower():
            min_zoom = int(line.split(":")[-1].strip())
        elif "max zoom:" in line.lower():
            max_zoom = int(line.split(":")[-1].strip())

    tilejson = {
        "tilejson": "3.0.0",
        "name": "MSHI-Geo F+NPP anomaly (Asia)",
        "description": (
            "Soil respiration anomaly ratio (predicted F+NPP model / "
            "predicted climate baseline) across Asia. "
            "RdBu_r colormap centered at 1.0, range 0.5-1.5. "
            "Red = positive anomaly (higher respiration than climate alone "
            "predicts), Blue = negative anomaly. "
            "WARNING: Night 1 deliverable is built on synthetic training "
            "data — replace before scientific publication."
        ),
        "version": "1.0.0",
        "attribution": "MSHI-Geo · synthetic data · land mask: Natural Earth 50m",
        "scheme": "xyz",
        "tiles": [
            # Local development server path. Replace with production CDN
            # URL for deployment. PMTiles range-request semantics work
            # over HTTP/HTTPS directly without a tile server.
            "http://localhost:8765/mshi_f_npp_anomaly/{z}/{x}/{y}.png"
        ],
        "format": "png",
        "type": "overlay",
        "minzoom": min_zoom if min_zoom is not None else 0,
        "maxzoom": max_zoom if max_zoom is not None else 6,
        "bounds": bounds if bounds else [25.0, -10.0, 180.0, 80.0],
        "center": [102.5, 35.0, 2],
        # Metadata for client-side colormap legends
        "vector_layers": [],
        "raster_layer": {
            "colormap": "RdBu_r",
            "vmin": 0.5,
            "vcenter": 1.0,
            "vmax": 1.5,
            "units": "ratio (F+NPP / climate baseline)",
            "interpretation": {
                "0.5-0.85": "strongly negative anomaly (low respiration vs climate-expected)",
                "0.85-1.15": "near climate expectation",
                "1.15-1.5": "strongly positive anomaly (high respiration vs climate-expected)",
            },
        },
    }
    OUT_TILEJSON.write_text(json.dumps(tilejson, indent=2))
    print(f"wrote {OUT_TILEJSON}")

    # Minimal MapLibre viewer HTML
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>MSHI-Geo F+NPP anomaly — local viewer</title>
  <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
  <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
  <style>
    body { margin: 0; padding: 0; font-family: system-ui, sans-serif; }
    #map { position: absolute; top: 0; bottom: 0; left: 0; right: 0; }
    #legend {
      position: absolute; bottom: 24px; left: 16px;
      background: rgba(255,255,255,0.92); padding: 12px 16px;
      border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      font-size: 13px; max-width: 280px;
    }
    #legend .gradient {
      height: 16px; margin: 6px 0;
      background: linear-gradient(to right,
        rgb(33,102,172), rgb(67,147,195), rgb(146,197,222),
        rgb(209,229,240), rgb(247,247,247),
        rgb(253,219,199), rgb(244,165,130), rgb(214,96,77), rgb(178,24,43));
      border-radius: 2px;
    }
    #legend .ticks {
      display: flex; justify-content: space-between;
      font-size: 11px; color: #444;
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="legend">
    <strong>F+NPP anomaly ratio</strong><br>
    <small>predicted F+NPP / climate baseline</small>
    <div class="gradient"></div>
    <div class="ticks">
      <span>0.5</span><span>0.75</span><span>1.0</span>
      <span>1.25</span><span>1.5</span>
    </div>
    <small style="color: #888;">Night 1 demo · synthetic data</small>
  </div>

  <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
  <script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
  <script>
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);

    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        sources: {
          carto: {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
            ],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors, © CARTO"
          },
          mshi: {
            type: "raster",
            // For production, change to https://<your-cdn>/tiles/mshi_f_npp_anomaly.pmtiles
            url: "pmtiles://http://localhost:8765/mshi_f_npp_anomaly.pmtiles",
            tileSize: 256,
            attribution: "MSHI-Geo · synthetic data · Natural Earth 50m"
          }
        },
        layers: [
          { id: "carto", type: "raster", source: "carto" },
          { id: "mshi", type: "raster", source: "mshi", paint: { "raster-opacity": 0.75 } }
        ]
      },
      center: [102.5, 35.0],
      zoom: 2,
      maxBounds: [[-30, -30], [200, 90]]
    });

    map.on("error", (e) => console.error("map error", e));
  </script>
</body>
</html>
"""
    OUT_HTML.write_text(html)
    print(f"wrote {OUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
