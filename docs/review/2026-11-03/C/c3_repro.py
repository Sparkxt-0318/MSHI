"""Check 3: re-run the noise_ceiling stage on the real analysis tables in a sandbox (outputs under scratch), with
n_jobs from argv (the committed run used 4), and compare every number with the committed results/noise_ceiling.json.
Usage: c3_repro.py <outdir_name> <n_jobs> [n_boot]"""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import copy
import json
import shutil
import time
from pathlib import Path

from common import REPO, SCRATCH


def main():
    from mshi.config import Config, load_config
    from mshi.io import write_result
    from mshi.analysis import noise_ceiling as NC
    name, n_jobs = sys.argv[1], int(sys.argv[2])
    n_boot = int(sys.argv[3]) if len(sys.argv) > 3 else None
    cfg = load_config()
    data = copy.deepcopy(cfg.data)
    root = Path(SCRATCH) / name
    if root.exists():
        shutil.rmtree(root)
    data["paths"]["raw"] = str(root / "raw")
    data["phase2"]["noise_ceiling"]["n_jobs"] = n_jobs
    if n_boot is not None:
        data["phase2"]["noise_ceiling"]["n_boot"] = n_boot
    sand = Config(data, source=cfg.source, out_root=root / "out")
    paths = []
    for f in ["records_analysis.parquet", "sites_analysis_qc.parquet", "sites_analysis_repo.parquet"]:
        dst = sand.path("derived", f)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f"{REPO}/data/derived/{f}", dst)
        paths.append(dst)
    write_result(sand, {"synthetic": "copy of the committed analysis tables"}, "build_sites_analysis.json",
                 outputs=paths)
    t0 = time.time()
    summ = NC.noise_ceiling(sand)
    print(f"stage ran in {time.time() - t0:.1f} s")
    new = json.loads(sand.path("results", NC.RESULT).read_text())
    old = json.load(open(f"{REPO}/results/noise_ceiling.json"))
    diffs = []

    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                if k in ("_provenance", "_inputs"):
                    continue
                if k not in a or k not in b:
                    diffs.append((path + "/" + k, "missing in one"))
                    continue
                walk(a[k], b[k], path + "/" + k)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diffs.append((path, f"len {len(a)} vs {len(b)}"))
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        else:
            if a != b:
                diffs.append((path, f"{a!r} vs {b!r}"))
    walk(new, old, "")
    print(f"differences from the committed result (excluding _provenance, _inputs): {len(diffs)}")
    for d in diffs[:60]:
        print("  ", d)
    json.dump({"diffs": diffs}, open(root / "diffs.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
