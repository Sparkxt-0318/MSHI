import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
V = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise"
SRDB = "/home/user/MSHI/data/raw/srdb/srdb-data.csv"

def cluster(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    return connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]

def load(tag="qc", srdb_only=False):
    r = pd.read_parquet(f"{V}/data/v3/records_v3.parquet")
    r = r[~r.f_offland & ~r.f_coord].copy()
    if tag == "qc":
        r = r[~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)]
    s = pd.read_csv(SRDB, low_memory=False)
    isr = r.src == "srdb"
    r["row"] = -1
    r.loc[isr, "row"] = r.loc[isr, "rec_id"].str.replace("srdb_", "").astype(int)
    sub = s[["Study_number", "Study_midyear", "Meas_method", "Ecosystem_type"]].add_prefix("S_")
    r = r.join(sub, on="row")  # row -1 (COSORE) -> NaN
    # COSORE dataset = its own study
    r["study_id"] = np.where(isr, "srdb_" + r.S_Study_number.astype(str), r.rec_id)
    if srdb_only:
        r = r[isr]
    r = r.reset_index(drop=True)
    r["site"] = cluster(r)
    return r
