import os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import pandas as pd
from mshi.io import read_table, ForbiddenInputError
W = Path(SCR) / "work" / "t6b"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
cfg = load_config()
DEMO = Path(REPO) / "legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet"
def tryread(label, path, **kw):
    try:
        df = read_table(cfg, path, **kw)
        print(f"  READ    {label:62s} shape={df.shape}")
    except Exception as e:  # noqa
        print(f"  refused {label:62s} {type(e).__name__}")
pd.read_parquet(DEMO).to_parquet(W / "resaved.parquet", index=False)
tryread("re-saved demo, columns=['longitude','latitude','soc']", W / "resaved.parquet", columns=["longitude", "latitude", "soc"])
tryread("byte-identical demo copy, columns=['longitude','latitude']", (shutil.copy(DEMO, W / "copy.parquet") and W / "copy.parquet"), columns=["longitude", "latitude"])
# byte-identical demo copy inside a real dir that a dataset reaches through a symlinked sub-directory
real = W / "real_dir"; real.mkdir(); shutil.copy(DEMO, real / "part-0.parquet")
ds = W / "ds.parquet"; ds.mkdir(); os.symlink(real, ds / "sub")
print("  rglob under ds sees:", [str(p.relative_to(ds)) for p in ds.rglob("*")])
tryread("dataset -> symlinked subdir -> byte-identical demo copy", ds)
tryread("same, with columns=['longitude','latitude']", ds, columns=["longitude", "latitude"])
