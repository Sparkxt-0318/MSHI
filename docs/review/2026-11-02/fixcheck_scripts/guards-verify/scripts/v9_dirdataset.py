"""Claim 9: members of a directory dataset get only the forbidden-hash check; symlinked sub-directories are not
walked; the 'source' content check sees only the projected columns. Real config, real mshi.io.read_table;
every constructed path lives in scratch (symlinks point INTO the repo, nothing in the repo is modified)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import REPO, WORK, Path, load_config  # noqa: E402

import pandas as pd  # noqa: E402

from mshi.io import ForbiddenInputError, read_table, sha256_file  # noqa: E402

cfg = load_config()
LEG = Path(REPO) / "legacy" / "data" / "processed"
v1 = LEG / "training_features.parquet"                 # real v1 table: under legacy/, NOT allow-listed
demo = LEG / "training_features_SYNTHETIC_DEMO.parquet"  # forbidden SHA-256
print("v1 allow-listed:", str(v1.relative_to(REPO)) in cfg["legacy_allowlist"],
      "| demo hash forbidden:", sha256_file(demo) in cfg["forbidden_sha256"])
W = WORK / "v9"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)


def attempt(label, path, **kw):
    try:
        df = read_table(cfg, path, **kw)
        print(f"  {label:70s} READ {df.shape}")
    except ForbiddenInputError as e:
        print(f"  {label:70s} refused ({str(e)[:70]}...)")


(W / "direct.parquet").symlink_to(v1)
attempt("symlink file -> legacy v1 table", W / "direct.parquet")
(W / "dirlink.parquet").mkdir()
(W / "dirlink.parquet" / "part-0.parquet").symlink_to(v1)
attempt("directory dataset whose member is a symlink -> legacy v1 table", W / "dirlink.parquet")

real = W / "subreal"; real.mkdir()
shutil.copy(demo, real / "part-0.parquet")                     # byte-identical demo copy (forbidden hash)
(W / "ds.parquet").mkdir()
(W / "ds.parquet" / "sub").symlink_to(real, target_is_directory=True)
print("  rglob members seen by check_readable:", [str(f.relative_to(W)) for f in (W / "ds.parquet").rglob("*")],
      "| files hashed:", [f.name for f in (W / "ds.parquet").rglob("*") if f.is_file()])
attempt("dir dataset, symlinked sub-dir with byte-identical demo, no projection", W / "ds.parquet")
attempt("same, columns=['longitude','latitude']", W / "ds.parquet", columns=["longitude", "latitude"])
(W / "ds2.parquet").mkdir()
shutil.copy(demo, W / "ds2.parquet" / "part-0.parquet")
attempt("control: dir dataset, demo copy as a plain member", W / "ds2.parquet", columns=["longitude", "latitude"])

resaved = W / "resaved.parquet"
pd.read_parquet(demo).to_parquet(resaved, index=False)          # different bytes, same rows
print("  re-saved demo hash differs from forbidden:", sha256_file(resaved) not in cfg["forbidden_sha256"])
attempt("re-saved demo, no projection", resaved)
attempt("re-saved demo, columns=['longitude','latitude','soc']", resaved, columns=["longitude", "latitude", "soc"])

# does any pipeline call read a directory dataset or project away 'source'?
print("  read_table calls with a projection in mshi/:")
for f in sorted((Path(REPO) / "mshi").rglob("*.py")):
    for i, line in enumerate(f.read_text().splitlines(), 1):
        if "read_table(" in line and ("columns=" in line or "usecols=" in line):
            print(f"     {f.relative_to(REPO)}:{i}: {line.strip()[:110]}")
