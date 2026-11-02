import os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import pandas as pd
from mshi.io import read_table, check_readable, ForbiddenInputError

W = Path(SCR) / "work" / "t6"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
cfg = load_config()
DEMO = Path(REPO) / "legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet"
V1 = Path(REPO) / "legacy/data/processed/training_features.parquet"          # real v1 table, not allow-listed
V2 = Path(REPO) / "legacy/data/processed/training_features_v2.parquet"       # allow-listed, hash-pinned
d = pd.read_parquet(DEMO)                                                    # direct read: scratch analysis only
print("demo columns:", list(d.columns)[:8], "... n_cols", d.shape[1], "source values", d.source.unique())

def tryread(label, path, **kw):
    try:
        df = read_table(cfg, path, **kw)
        src = sorted(set(df["source"].astype(str))) if "source" in df.columns else "no source col"
        print(f"  READ    {label:55s} shape={df.shape} source={src}")
    except Exception as e:  # noqa
        print(f"  refused {label:55s} {type(e).__name__}: {str(e)[:90]}")

# variants of the demo table
d.to_parquet(W / "resaved.parquet", index=False)
d.drop(columns=["source"]).to_parquet(W / "no_source.parquet", index=False)
d.rename(columns={"source": "Source"}).to_parquet(W / "Source_renamed.parquet", index=False)
d.assign(source="srdb").to_parquet(W / "source_relabelled.parquet", index=False)
ds = W / "dataset.parquet"; ds.mkdir(); d.to_parquet(ds / "part-0.parquet", index=False)
ds2 = W / "hive.parquet"; d.to_parquet(ds2, partition_cols=["source"], index=False)
tryread("re-saved parquet", W / "resaved.parquet")
tryread("re-saved parquet read with columns= (no source)", W / "resaved.parquet", columns=["lat", "lon"] if "lat" in d else list(d.columns[:3]))
tryread("re-saved, source column dropped", W / "no_source.parquet")
tryread("re-saved, source column renamed 'Source'", W / "Source_renamed.parquet")
tryread("directory dataset of a re-saved copy", ds)
tryread("hive-partitioned on source", ds2)

# symlinks, relative paths, case
os.symlink(DEMO, W / "link_to_demo.parquet")
os.symlink(V1, W / "link_to_v1.parquet")
tryread("symlink -> demo", W / "link_to_demo.parquet")
tryread("symlink -> legacy v1 table", W / "link_to_v1.parquet")
dl = W / "dirlink.parquet"; dl.mkdir(); os.symlink(V1, dl / "part-0.parquet")
tryread("directory dataset containing symlink -> legacy v1", dl)
dl2 = W / "dirlink2.parquet"; dl2.mkdir(); os.symlink(Path(REPO) / "legacy/data/processed", dl2 / "sub")
tryread("dataset with a symlinked SUBDIR -> legacy/data/processed", dl2)
shutil.copy(V1, W / "copy_of_v1.parquet")
tryread("plain copy of the legacy v1 table outside legacy/", W / "copy_of_v1.parquet")
os.chdir(REPO)
tryread("relative 'legacy/...v2' (cwd=repo)", "legacy/data/processed/training_features_v2.parquet")
tryread("relative 'legacy/...v1' (cwd=repo)", "legacy/data/processed/training_features.parquet")
os.chdir(W)
tryread("relative 'legacy/...v2' (cwd=scratch)", "legacy/data/processed/training_features_v2.parquet")
tryread("non-existent path", W / "nope.parquet")
tryread("'..' traversal into legacy", W / ".." / ".." / ".." / ".." / ".." / ".." / ".." / ".." / ".." / "home/user/MSHI/legacy/data/processed/training_features.parquet")
tryread("upper-case LEGACY path (Linux: no such dir)", Path(REPO) / "LEGACY/data/processed/training_features_v2.parquet")
tryread("allow-listed v2 table", V2)
print("check_readable on a directory returns:", check_readable(cfg, ds))
