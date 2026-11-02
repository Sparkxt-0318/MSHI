"""Claim 1 follow-up: would tests/test_regression.py::test_fresh_rebuild_matches_committed_tables (pd.testing.
assert_frame_equal, check_dtype=False) notice the reverse-order sandbox of v1_transitive.py reverse?
Compares the full chain under config C with the reverse-order run under config C."""
import pandas as pd

W = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/guards-verify/work/v1_reverse"
for name in ["cosore_annual.csv", "sites_v3_qc.parquet", "sites_v3_repo.parquet", "records_v3.parquet"]:
    rd = pd.read_csv if name.endswith(".csv") else pd.read_parquet
    a, b = rd(f"{W}/fullC/derived/{name}"), rd(f"{W}/revC/derived/{name}")
    try:
        pd.testing.assert_frame_equal(a, b, check_dtype=False)
        print(name, "assert_frame_equal: equal")
    except AssertionError as e:
        print(name, "assert_frame_equal: DIFFERENT ->", str(e).splitlines()[0:3])
