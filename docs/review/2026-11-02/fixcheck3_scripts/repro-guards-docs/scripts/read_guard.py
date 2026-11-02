"""mshi.io.read_table guard: directories, symlinks, projections (parquet/CSV, usecols callables, sep/encoding),
and other ways the 'source' column can leave df.columns. Every file is a scratch copy; the repo is only read."""
import os, shutil, sys, warnings
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
warnings.filterwarnings("ignore")
import pandas as pd
from mshi.config import load_config
from mshi.io import read_table, ForbiddenInputError

cfg = load_config(); W = Path(sys.argv[1]); shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
DEMO = cfg.repo_path("legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet")
V1 = cfg.repo_path("legacy/data/processed/training_features.parquet")
V2 = cfg.repo_path("legacy/data/processed/training_features_v2.parquet")
d = pd.read_parquet(DEMO)                      # direct read, scratch test only
print("demo:", d.shape, "source values", sorted(set(d.source)), "columns", list(d.columns)[:6], "...")

def t(label, path, **kw):
    try:
        df = read_table(cfg, path, **kw)
        out = f"READ {df.shape}" + (f" index={df.index.name}" if df.index.name else "")
    except ForbiddenInputError as e:
        out = f"refused ({str(e).split(':')[0][:40]}...: {'directory' if 'directory' in str(e) else 'legacy' if 'legacy' in str(e) else 'forbidden hash' if 'forbidden' in str(e) else 'synthetic' if 'synthetic' in str(e) else str(e)[:40]})"
    except Exception as e:
        out = f"{type(e).__name__}: {str(e)[:70]}"
    print(f"  {label:68s} {out}")

print("== directories and symlinks")
ds = W / "ds.parquet"; ds.mkdir(); shutil.copy(DEMO, ds / "part-0.parquet"); t("directory dataset", ds)
ln = W / "dirlink.parquet"; ln.symlink_to(ds, target_is_directory=True); t("symlink to a directory", ln)
s1 = W / "v1link.parquet"; s1.symlink_to(V1); t("symlink to legacy v1 table (not allow-listed)", s1)
s2 = W / "demolink.parquet"; s2.symlink_to(DEMO); t("symlink to the demo table", s2)
s3 = W / "v2link.parquet"; s3.symlink_to(V2); t("symlink to the allow-listed v2 table", s3)
cp = W / "demo_copy.parquet"; shutil.copy(DEMO, cp); t("byte copy of the demo table", cp)

print("== re-encoded demo table, projections")
rz = W / "resaved.parquet"; d.to_parquet(rz, index=False, compression="gzip")
t("re-saved parquet, no projection", rz)
t("re-saved parquet, columns=[longitude, latitude]", rz, columns=["longitude", "latitude"])
t("re-saved parquet, columns=[]", rz, columns=[])
c = W / "export.csv"; d.to_csv(c, index=False)
t("CSV, usecols list", c, usecols=["longitude", "latitude"])
t("CSV, usecols callable", c, usecols=lambda x: x != "source")
t("CSV, usecols by position", c, usecols=[0, 1])
c2 = W / "semi.csv"; d.to_csv(c2, index=False, sep=";"); t("CSV sep=';', usecols", c2, sep=";", usecols=["longitude"])
c3 = W / "u16.csv"; d.to_csv(c3, index=False, encoding="utf-16"); t("CSV utf-16, usecols", c3, encoding="utf-16", usecols=["longitude"])
c4 = W / "tab.txt"; d.to_csv(c4, index=False, sep="\t"); t("TXT tab, delimiter kw, usecols", c4, delimiter="\t", usecols=["longitude"])

print("== 'source' column not in df.columns without a projection kwarg")
ix = W / "source_as_index.parquet"; d.set_index("source").to_parquet(ix)
import pyarrow.parquet as pq
print("  schema of source_as_index.parquet:", pq.read_schema(ix).names[-3:])
t("parquet whose 'source' column is the stored pandas index (no kwargs)", ix)
t("same, columns=[longitude]", ix, columns=["longitude"])
t("CSV with index_col='source'", c, index_col="source")
t("CSV with index_col='source', usecols", c, index_col="source", usecols=["source", "longitude"])
mi = W / "multiindex.parquet"; d.set_index(["source", "longitude"]).to_parquet(mi); t("parquet, MultiIndex (source, longitude)", mi)

print("== header-changing CSV kwargs with a projection")
pre = W / "preamble.csv"; pre.write_text("exported from the v1 demo\n" + c.read_text()); t("CSV with a preamble line, skiprows=1, usecols", pre, skiprows=1, usecols=["longitude", "latitude"])
t("same, skiprows=1, no usecols (control)", pre, skiprows=1)
cm = W / "comment.csv"; cm.write_text("# v1 demo\n" + c.read_text()); t("CSV with a comment line, comment='#', usecols", cm, comment="#", usecols=["longitude"])
nh = W / "noheader.csv"; d.to_csv(nh, index=False, header=False)
names = list(d.columns)
t("headerless CSV, header=None, names=..., usecols", nh, header=None, names=names, usecols=["longitude", "latitude"])
t("same, no usecols (control)", nh, header=None, names=names)
t("CSV header=0 names renaming source->src, usecols", c, header=0, names=[n if n != "source" else "src" for n in names], usecols=["longitude", "src"])
