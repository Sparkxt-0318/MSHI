"""Claims 2 and 5: does mshi.io.read_table refuse re-encoded copies of the v1 demo table in these cases?
Scratch copies only (S/work/rg/); the real config; nothing in the repo is written."""
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")

import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from mshi.config import load_config  # noqa: E402
from mshi.io import ForbiddenInputError, read_table  # noqa: E402

SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
W = SCR / "work" / "rg"
shutil.rmtree(W, ignore_errors=True)
W.mkdir(parents=True)
cfg = load_config()
DEMO = cfg.repo_path("legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet")
d = pd.read_parquet(DEMO)                       # direct read of the demo table, to build test copies only
print("demo:", d.shape, "source values:", sorted(set(d.source)), "has source column:", "source" in d.columns)


def attempt(label, path, **kw):
    try:
        df = read_table(cfg, path, **kw)
        src_in = ("source" in df.columns) or ("source" in [n for n in df.index.names if n])
        print(f"READ     {label}: shape {df.shape}, index names {list(df.index.names)}, 'source' present: {src_in}")
    except ForbiddenInputError as e:
        print(f"REFUSED  {label}: {str(e)[:110]}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR    {label}: {type(e).__name__}: {str(e)[:110]}")


print("\n-- (5a) parquet with 'source' stored as the pandas index")
p = W / "source_as_index.parquet"
d.set_index("source").to_parquet(p)
print("   schema names end:", pq.read_schema(p).names[-3:], "| pandas index_columns:",
      pq.read_schema(p).pandas_metadata["index_columns"])
attempt("source_as_index.parquet, no kwargs", p)
attempt("source_as_index.parquet, columns=['longitude']", p, columns=["longitude"])
p2 = W / "multiindex.parquet"
d.set_index(["source", "longitude"]).to_parquet(p2)
attempt("multiindex.parquet (source, longitude), no kwargs", p2)
p0 = W / "resaved.parquet"
d.to_parquet(p0, index=False, compression="gzip")
attempt("control resaved.parquet (source column), no kwargs", p0)
attempt("control resaved.parquet, columns=['longitude','latitude']", p0, columns=["longitude", "latitude"])

print("\n-- (5a') CSV read with index_col='source' (no projection kwarg)")
c0 = W / "export.csv"
d.to_csv(c0, index=False)
attempt("export.csv, index_col='source'", c0, index_col="source")
attempt("control export.csv, no kwargs", c0)
attempt("fixed part: export.csv usecols list", c0, usecols=["longitude", "latitude"])
attempt("fixed part: export.csv usecols callable", c0, usecols=lambda c: c != "source")
attempt("fixed part: export.csv usecols positions", c0, usecols=[0, 1])
c_semi = W / "semi.csv"
d.to_csv(c_semi, index=False, sep=";")
attempt("fixed part: semi.csv sep=';' usecols", c_semi, sep=";", usecols=["longitude"])

print("\n-- (2)/(5b) CSV projections combined with header-changing kwargs")
c1 = W / "preamble.csv"
c1.write_text("# exported 2026-11-02 from a notebook\n" + c0.read_text())
attempt("preamble.csv skiprows=1 (control, no projection)", c1, skiprows=1)
attempt("preamble.csv skiprows=1 + usecols", c1, skiprows=1, usecols=["longitude", "latitude"])
attempt("preamble.csv comment='#' (control)", c1, comment="#")
attempt("preamble.csv comment='#' + usecols", c1, comment="#", usecols=["longitude"])
c2 = W / "headerless.csv"
d.to_csv(c2, index=False, header=False)
names = list(d.columns)
attempt("headerless.csv header=None names=... (control)", c2, header=None, names=names)
attempt("headerless.csv header=None names=... + usecols", c2, header=None, names=names, usecols=["longitude", "latitude"])
attempt("export.csv header=0 names=renamed + usecols (rename 'source'->'origin')", c0, header=0,
        names=[("origin" if n == "source" else n) for n in names], usecols=["longitude"])

print("\n-- pipeline projected reads (grep of read_table calls with kwargs):")
for f in sorted(Path("/home/user/MSHI/mshi").rglob("*.py")):
    for i, line in enumerate(f.read_text().splitlines(), 1):
        if "read_table(" in line and "def read_table" not in line and "," in line.split("read_table(", 1)[1].split(")")[0].split(",", 2)[-1] and line.count(",") >= 2:
            print("  ", f.relative_to("/home/user/MSHI"), i, line.strip())
