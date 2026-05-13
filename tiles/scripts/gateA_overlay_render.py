"""
Gate A: verify that the rendered overlay tiles actually contain
visible colored content (not transparent, not grayscale).

Tests:
  1. Curl-equivalent fetch of /mshi_f_npp_anomaly/3/6/3.png from
     the local pmtiles server returns a valid PNG with non-trivial
     color content.
  2. The PNG has >100 unique RGB values (cmap actually applied).
  3. The PNG has at least 5% visible (alpha > 0) pixels (real data
     coverage at z=3 central Asia).
"""

from __future__ import annotations

import io
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PMT = ROOT / "tiles" / "mshi_f_npp_anomaly.pmtiles"
PORT = 8765
URL = f"http://localhost:{PORT}/mshi_f_npp_anomaly/3/6/3.png"


def main() -> int:
    results = []
    server = None

    # Spin up pmtiles serve
    server = subprocess.Popen(
        ["pmtiles", "serve", str(PMT.parent), f"--port={PORT}", "--cors=*"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for server
        ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(URL, timeout=2) as r:
                    if r.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.3)
        results.append(("server_ready", ready, f"server at {URL}"))

        if not ready:
            emit(results)
            return 1

        # Fetch the tile
        with urllib.request.urlopen(URL, timeout=10) as r:
            status = r.status
            data = r.read()
        results.append(("http_200", status == 200, f"status={status}, bytes={len(data)}"))

        # Decode PNG
        try:
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            arr = np.array(img)
            png_ok = img.size == (256, 256)
            decode_detail = f"dims={img.size}, mode=RGBA"
        except Exception as e:
            png_ok = False
            arr = None
            decode_detail = f"decode failed: {e}"
        results.append(("png_valid", png_ok, decode_detail))

        if arr is None:
            emit(results)
            return 1

        # Visible-pixel coverage
        alpha = arr[..., 3]
        visible = arr[alpha > 0]
        n_vis = len(visible)
        coverage = n_vis / (arr.shape[0] * arr.shape[1])
        results.append((
            "visible_pixels_>5pct",
            coverage > 0.05,
            f"{n_vis}/{arr.size//4} = {100*coverage:.1f}% visible",
        ))

        # Unique RGB count
        if n_vis > 0:
            unique_rgb = len(np.unique(visible[:, :3], axis=0))
        else:
            unique_rgb = 0
        results.append((
            "unique_rgb_>100",
            unique_rgb > 100,
            f"{unique_rgb} unique RGB values in visible pixels",
        ))

        # Not entirely transparent
        all_trans = (alpha.sum() == 0)
        results.append((
            "not_all_transparent",
            not all_trans,
            f"alpha sum = {int(alpha.sum())}",
        ))

    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()

    n_pass = emit(results)
    (ROOT / "tiles" / "intermediate" / "gateA_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE A RESULTS (overlay actually renders)")
    print("=" * 78)
    n_pass = 0
    for name, ok, detail in results:
        flag = "PASS" if ok else "FAIL"
        if ok:
            n_pass += 1
        print(f"  [{flag}] {name}: {detail}")
    print("=" * 78)
    print(f"Total: {n_pass}/{len(results)} passed")
    print("=" * 78)
    return n_pass


if __name__ == "__main__":
    raise SystemExit(main())
