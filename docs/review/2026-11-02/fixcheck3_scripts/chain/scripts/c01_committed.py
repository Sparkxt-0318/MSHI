"""Are the committed results (de236d0) current for HEAD? result_staleness for each results/*.json, outputs check."""
import sys, json, subprocess
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config
from mshi.runlog import code_sha256, provenance
from mshi.io import result_staleness, sha256_file
cfg = load_config()
print("HEAD", subprocess.run(["git", "-C", "/home/user/MSHI", "--no-optional-locks", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
print("config_sha256", cfg.sha256())
print("code_sha256", code_sha256())
for p in sorted(cfg.path("results").glob("*.json")):
    obj = json.loads(p.read_text())
    if p.name == "environment.json":
        print(p.name, obj.get("git_commit"), obj.get("config_sha256") == cfg.sha256(), obj.get("code_sha256") == code_sha256())
        continue
    print(f"{p.name:28s} staleness={result_staleness(cfg, obj)!r} outputs={obj.get('_outputs')}")
    for k, d in (obj.get("_outputs") or {}).items():
        f = cfg.from_root_key(k)
        print("    ", k, f, f.exists(), sha256_file(f) == d)
