"""Run the port's extract_points (plan_jobs, _read_job, aggregate) against the same fake catalog.
usage: run_port.py OUT.parquet [ties]"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/home/user/MSHI")
import pandas as pd
import fakepc
from mshi.config import load_config
from mshi.data import modis
m = load_config()["sources"]["modis"]
pts = pd.read_csv(os.path.join(HERE, "sites.csv"))          # same parser as the prototype
tiles = eval(open(os.path.join(HERE, "tiles.txt")).read())
ties = len(sys.argv) > 2 and sys.argv[2] == "ties"
cat = fakepc.FakeCatalog(tiles, ties)
t = time.time()
out, info = modis.extract_points(pts, m, catalog=cat, tokens=fakepc.FakeTokens())
print(f"port: {len(out)} points, n_jobs {info['n_jobs']}, n_tiles {info['n_tiles']}, failed {len(info['failed_reads'])}, "
      f"{time.time()-t:.1f}s; searches {len(cat.calls)}; first search {cat.calls[0]}")
out.to_parquet(sys.argv[1], index=False)
