"""20_fetch_worldclim30s.py — fetch only the eight WorldClim 2.1 30 arc-second
bioclim layers used by the study, using HTTP range requests (remotezip) so the
10.4 GB archive is never downloaded in full.

Layers: bio 1, 4, 5, 6, 12, 14, 15, 17.

Usage:
    python -I audit/20_fetch_worldclim30s.py data/raw/worldclim30s

zipfile verifies the CRC-32 of each member on extraction; a mismatch raises.
A manifest (name, bytes, CRC-32, sha256, UTC time) is written next to the files.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from remotezip import RemoteZip

URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_bio.zip"
LAYERS = [1, 4, 5, 6, 12, 14, 15, 17]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    with RemoteZip(URL) as z:
        info = {i.filename: i for i in z.infolist()}
        for b in LAYERS:
            name = f"wc2.1_30s_bio_{b}.tif"
            target = out_dir / name
            zi = info[name]
            if target.exists() and target.stat().st_size == zi.file_size and name in manifest:
                print(f"{name}: present, skipping", flush=True)
                continue
            t0 = time.time()
            print(f"{name}: fetching {zi.compress_size/1e6:.0f} MB ...", flush=True)
            # zipfile.extract checks CRC-32 while reading; corrupted bytes raise BadZipFile
            z.extract(name, path=out_dir)
            dt = time.time() - t0
            manifest[name] = {
                "url": URL,
                "member_bytes": zi.file_size,
                "crc32": zi.CRC,
                "sha256": sha256(target),
                "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "seconds": round(dt, 1),
            }
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"{name}: done in {dt:.0f} s ({zi.compress_size/1e6/max(dt,1e-6):.1f} MB/s)", flush=True)
    print("ALL_LAYERS_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
