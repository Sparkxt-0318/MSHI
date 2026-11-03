"""Smoke-like run of transfer_matrix + within_continent on 50 synthetic sites (as a --smoke run would have once the
gridded sources open): every pairwise training set is below min_test_sites; LOCO only; no continent eligible for the
within-continent benchmark. Checks the stages complete and what they record."""
import sys, json, copy
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd
from mshi.config import load_config, Config
from mshi.analysis import transfer as T
from mshi.io import write_result, write_table, require_current
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
base = load_config(); data = copy.deepcopy(base.data); data["paths"]["raw"] = str(OUT / "raw")
data["phase2"]["transfer"]["rf"].update(n_estimators=20, n_jobs=2); data["phase2"]["bootstrap"]["n"] = 100
cfg = Config(data, source=base.source, out_root=OUT / "out")
synth = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet")
s = synth.sample(50, random_state=20261102).reset_index(drop=True)
print(s.continent_geo.value_counts().to_dict())
paths = [write_table(s, cfg.path("interim", f"features_analysis_{t}.parquet")) for t in ("qc", "repo")]
write_result(cfg, {"synthetic": True}, "features_analysis.json", outputs=paths)
print("transfer_matrix:", T.transfer_matrix(cfg))
print("within_continent:", T.within_continent(cfg))
R = json.loads(cfg.path("results", "transfer_matrix.json").read_text())
print("main rows:", [(r["table"], r["test"], r["learner"], r["n_train"], r["n_test"], round(r["r2"], 3)) for r in R["main"]][:8])
print("skipped:", [(x["table"], x["train"], x.get("n_train"), x["reason"][:45]) for x in R["skipped"]])
W = json.loads(cfg.path("results", "within_continent.json").read_text())
print("within skipped:", W["skipped"], "outputs:", sorted(W["_outputs"]))
