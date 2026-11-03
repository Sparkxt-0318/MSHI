"""Polished fits vs the reviewer's independent REML maxima, every bootstrap replicate of the groups given."""
import sys, json
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd
from threadpoolctl import threadpool_limits
from mshi.config import load_config
from mshi.analysis import noise_ceiling as NC
cfg = load_config(); s = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(cfg.path("derived", "records_analysis.parquet"))
sites = pd.read_parquet(cfg.path("derived", f"sites_analysis_{s.variant}.parquet"))
r, st, _ = NC.prepare(rec, sites, s); groups = NC.build_groups(r, st, s.continents)
draws = NC.draws(groups, s)
for path in sys.argv[2:]:
    data = json.load(open(path))
    for name, reps in data.items():
        own = {x["b"]: x for x in reps}
        g = groups[name]; gaps = []; bad = []; failed = 0; polished = 0
        with threadpool_limits(limits=1):
            for b, d in enumerate(draws):
                o = own.get(b)
                if o is None or o.get("own_llf") is None:
                    continue
                f = NC.replicate_stats(g, d[name], s.min_records, s.optimizer)["fit"]
                if f["status"] != "ok":
                    failed += 1; bad.append((b, f["status"])); continue
                polished += bool(f["polish"]["applied"])
                gap = o["own_llf"] - f["polish"]["llf"]
                gaps.append(gap)
                if gap > 1e-6:
                    bad.append((b, round(gap, 6)))
        gaps = np.array(gaps)
        print(f"{name}: replicates {len(gaps)}, max(own - kept) {gaps.max():.2e}, min {gaps.min():.2e}, "
              f"failed {failed}, polished {polished}, gap > 1e-6: {bad}", flush=True)
