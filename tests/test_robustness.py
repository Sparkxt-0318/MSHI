"""Failure handling, caching, provenance and stage plumbing (package review, 2026-11-02).

Everything here is offline: a local HTTP server, local git repositories, fake STAC catalogs, synthetic
rasters and synthetic targets. No real Europe outcome is scored.
"""
import copy
import http.server
import json
import subprocess
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests

from mshi.config import Config
from mshi.io import write_json, write_result
from mshi.netutil import (ChecksumMismatchError, DownloadError, SourceUnavailableError, download,
                          git_checkout_commit, verify_git_checkout)


def sandbox(cfg, tmp_path, edit=None) -> Config:
    data = copy.deepcopy(cfg.data)
    data["paths"]["raw"] = str(tmp_path / "raw")
    if edit:
        edit(data)
    return Config(data, source=cfg.source, out_root=tmp_path / "out")


# ---------------------------------------------------------------- downloads

class _Handler(http.server.BaseHTTPRequestHandler):
    hits: dict = {}

    def do_GET(self):  # noqa: N802
        _Handler.hits[self.path] = _Handler.hits.get(self.path, 0) + 1
        if self.path.startswith("/ok"):
            body = b"hello world"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            code = int(self.path.strip("/").split("/")[0])
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def direct():
    s = requests.Session()
    s.trust_env = False            # local server: bypass the egress proxy
    return s


def test_download_ok_and_skip_when_pinned_file_present(server, direct, tmp_path):
    import hashlib
    h = hashlib.sha256(b"hello world").hexdigest()
    info = download(f"{server}/ok/a", tmp_path / "a.txt", sha256=h, session=direct)
    assert info["downloaded"] and (tmp_path / "a.txt").read_bytes() == b"hello world"
    n = _Handler.hits.get("/ok/a")
    assert download(f"{server}/ok/a", tmp_path / "a.txt", sha256=h, session=direct)["downloaded"] is False
    assert _Handler.hits.get("/ok/a") == n          # no request


def test_download_checksum_mismatch_leaves_nothing(server, direct, tmp_path):
    with pytest.raises(ChecksumMismatchError):
        download(f"{server}/ok/b", tmp_path / "b.txt", sha256="0" * 64, session=direct)
    assert not (tmp_path / "b.txt").exists() and not (tmp_path / "b.txt.part").exists()


def test_download_404_is_an_error_not_a_block_and_is_not_retried(server, direct, tmp_path):
    sleeps = []
    with pytest.raises(DownloadError, match="404"):
        download(f"{server}/404/x", tmp_path / "x", session=direct, sleep=sleeps.append)
    assert sleeps == [] and _Handler.hits["/404/x"] == 1


def test_download_5xx_retried_then_error(server, direct, tmp_path):
    sleeps = []
    with pytest.raises(DownloadError, match="503"):
        download(f"{server}/503/y", tmp_path / "y", session=direct, sleep=sleeps.append, retries=4)
    assert sleeps == [2, 4, 8] and _Handler.hits["/503/y"] == 4      # no sleep after the last attempt


class _RaisingSession:
    def __init__(self, exc):
        self.exc, self.calls = exc, 0

    def get(self, *a, **k):
        self.calls += 1
        raise self.exc


def test_proxy_denial_is_blocked_without_retry(tmp_path):
    s = _RaisingSession(requests.exceptions.ProxyError("Tunnel connection failed: 403 Forbidden"))
    with pytest.raises(SourceUnavailableError) as e:
        download("https://example.invalid/f", tmp_path / "f", session=s, sleep=lambda x: None)
    assert e.value.kind == "proxy_denied" and s.calls == 1


def test_connection_failure_is_unavailable_after_retries(tmp_path):
    s = _RaisingSession(requests.exceptions.ConnectionError("Name or service not known"))
    sleeps = []
    with pytest.raises(SourceUnavailableError) as e:
        download("https://example.invalid/f", tmp_path / "f", session=s, sleep=sleeps.append, retries=3)
    assert e.value.kind == "unreachable" and s.calls == 3 and sleeps == [2, 4]


# ---------------------------------------------------------------- pinned git checkout

def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def origin(tmp_path):
    src = tmp_path / "origin"
    src.mkdir()
    _git("init", "-q", cwd=src)
    _git("config", "user.email", "t@example.invalid", cwd=src)
    _git("config", "user.name", "t", cwd=src)
    _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=src)
    (src / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\n")
    _git("add", ".", cwd=src)
    _git("commit", "-qm", "c1", cwd=src)
    return src, _git("rev-parse", "HEAD", cwd=src)


def test_git_checkout_detects_modified_and_untracked_files(origin, tmp_path):
    src, commit = origin
    dest = tmp_path / "co"
    info = git_checkout_commit(f"file://{src}", commit, dest)
    assert info["downloaded"] and info["commit"] == commit and len(info["tree"]) == 40
    assert git_checkout_commit(f"file://{src}", commit, dest)["downloaded"] is False
    (dest / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 99\n")
    with pytest.raises(ChecksumMismatchError, match="local changes"):
        git_checkout_commit(f"file://{src}", commit, dest)
    _git("checkout", "--", "DESCRIPTION.txt", cwd=dest)
    verify_git_checkout(dest, commit)
    (dest / "extra_dataset").mkdir()
    (dest / "extra_dataset" / "x").write_text("x")
    with pytest.raises(ChecksumMismatchError):
        verify_git_checkout(dest, commit)


# ---------------------------------------------------------------- MODIS

M = {"window_deg": 0.05, "retries": 1, "threads": 4, "second_pass_threads": 2, "max_failed_reads": 0,
     "datetime": "2020-01-01/2024-12-31", "max_items_per_tile": 500,
     "sinusoidal_proj": "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext", "tile_size_m": 1111950.5197,
     "x_origin_m": -20015109.354, "y_origin_m": 10007554.677,
     "npp": {"collection": "npp-col", "item_prefix": "MOD17A3HGF", "asset": "Npp_500m", "valid_range": [0, 32700],
             "scale": 0.1, "offset": 0.0},
     "lst": {"collection": "lst-col", "item_prefix": "MOD11A2", "assets": {"lst_day": "D", "lst_night": "N"},
             "valid_min_exclusive": 0, "scale": 0.02, "offset": -273.15, "composite": "first_of_month"}}


def _item(iid, when, assets, dt_none=False):
    when = datetime(*when, tzinfo=timezone.utc)
    return SimpleNamespace(id=iid, datetime=None if dt_none else when,
                           properties={"start_datetime": when.isoformat()},
                           assets={a: SimpleNamespace(href=f"mem://{iid}/{a}") for a in assets})


class FakeCatalog:
    def __init__(self):
        self.npp = [_item(f"MOD17A3HGF.A{y}", (y, 1, 1), ["Npp_500m"]) for y in range(2020, 2025)]
        self.npp.append(_item("MYD17A3HGF.A2020", (2020, 1, 1), ["Npp_500m"]))          # Aqua: excluded
        self.lst = []
        for y in (2021,):
            for mth in range(1, 13):
                for k, day in enumerate((1, 9, 17)):
                    self.lst.append(_item(f"MOD11A2.{y}{mth:02d}{day:02d}", (y, mth, day), ["D", "N"],
                                          dt_none=(k == 0 and mth % 2 == 0)))
        self.lst.append(_item("MYD11A2.20210101", (2021, 1, 1), ["D", "N"]))

    def search(self, collections, **kw):
        its = self.npp if collections[0] == "npp-col" else list(reversed(self.lst))
        return SimpleNamespace(item_collection=lambda: its)


def _pts():
    from mshi.data.modis import site_key, sinusoidal_tiles
    p = pd.DataFrame({"lat": [45.0, 45.01], "lon": [10.0, 10.02]})
    p["site_key"] = site_key(p.lat, p.lon).values
    p["h"], p["v"] = sinusoidal_tiles(p.lon.values, p.lat.values, M)
    return p


def test_plan_jobs_first_composite_per_month_terra_only_and_datetime_none():
    from mshi.data.modis import plan_jobs
    jobs = plan_jobs(_pts(), M, FakeCatalog())
    npp = [j for j in jobs if j[0] == "npp"]
    day = [j for j in jobs if j[0] == "lst_day"]
    assert len(npp) == 5 and all("MOD17" in j[1] for j in npp)
    assert len(day) == 12 and all(j[3].day == 1 and "MOD11" in j[1] for j in day)
    assert len([j for j in jobs if j[0] == "lst_night"]) == 12


def test_plan_jobs_rejects_unimplemented_composite_rule():
    from mshi.data.modis import plan_jobs
    m = copy.deepcopy(M)
    m["lst"]["composite"] = "all_composites"
    with pytest.raises(ValueError, match="not implemented"):
        plan_jobs(_pts(), m, FakeCatalog())


def test_aggregate_independent_of_completion_order():
    from mshi.data.modis import aggregate
    rng = np.random.default_rng(1)
    res = [("lst_day", datetime(2021, m, 1, tzinfo=timezone.utc), f"h{m}", {"a": float(v), "b": float(v) / 3})
           for m, v in zip(range(1, 13), rng.normal(20, 7, 12))]
    outs = [aggregate([res[i] for i in rng.permutation(len(res))], ["a", "b"], ["lst_day"]) for _ in range(20)]
    for o in outs[1:]:
        pd.testing.assert_frame_equal(o, outs[0], check_exact=True)


class _Tokens:
    def get(self, force=False):
        return "tok"


def test_extract_points_second_pass_and_persistent_failures(monkeypatch):
    from mshi.data import modis
    calls = {}

    def fake_read(href, sub, kind, m):
        h = href.split("?")[0]
        calls[h] = calls.get(h, 0) + 1
        if "A2023" in h:
            raise OSError("CURL error: 503")                 # persistent failure
        if "A2022" in h and calls[h] == 1:
            raise OSError("CURL error: timeout")             # transient: recovered in the second pass
        return {k: 100.0 for k in sub.site_key}

    monkeypatch.setattr(modis, "read_windows", fake_read)
    out, info = modis.extract_points(_pts(), M, kinds=("npp",), catalog=FakeCatalog(), tokens=_Tokens())
    assert info["n_jobs"] == 5 and len(info["failed_reads"]) == 1 and "A2023" in info["failed_reads"][0]
    assert (out.npp_n == 4).all()


def test_modis_points_fails_on_failed_reads_and_caches_only_complete_runs(cfg, tmp_path, monkeypatch):
    from mshi.data import modis
    import mshi.netutil as N
    sand = sandbox(cfg, tmp_path)
    pts = _pts()[["lat", "lon", "site_key"]]
    monkeypatch.setattr(modis, "modis_point_set", lambda c: pts)
    monkeypatch.setattr(N, "check_reachable", lambda *a, **k: None)
    state = {"fail": True, "calls": 0}

    def fake_extract(p, m):
        state["calls"] += 1
        out = pd.DataFrame({"site_key": p.site_key, "npp": 500.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                            "lst_night": 5.0, "lst_night_n": 60})
        return out, {"n_jobs": 125, "n_tiles": 1, "failed_reads": ["mem://x: OSError"] if state["fail"] else []}

    monkeypatch.setattr(modis, "extract_points", fake_extract)
    with pytest.raises(modis.ModisIncompleteError):
        modis.modis_points(sand)
    rec = json.loads(sand.path("results", "modis_points.json").read_text())
    assert rec["n_failed_reads"] == 1 and rec["status"].startswith("incomplete")
    assert not sand.path("interim", "modis_points.parquet").exists()
    with pytest.raises(FileNotFoundError):
        modis.load_modis_points(sand)

    state["fail"] = False
    r1 = modis.modis_points(sand)
    assert r1["n_failed_reads"] == 0 and state["calls"] == 2
    j1 = sand.path("results", "modis_points.json").read_text()
    r2 = modis.modis_points(sand)                                       # cache hit: same record, no extraction
    assert r2["cached"] and state["calls"] == 2 and sand.path("results", "modis_points.json").read_text() == j1
    assert len(modis.load_modis_points(sand, pts.site_key)) == 2

    changed = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["modis"].__setitem__("window_deg", 0.25))
    with pytest.raises(modis.StaleModisError):
        modis.load_modis_points(changed)                                # features would refuse it
    modis.modis_points(changed)
    assert state["calls"] == 3                                          # config change -> re-extracted


# ---------------------------------------------------------------- runner: order, statuses, exit codes

def _fake_stages(behaviour):
    from mshi.run import Stage

    def mk(name):
        def f(cfg):
            b = behaviour[name]
            if isinstance(b, Exception):
                raise b
            return {"ok": name}
        return f
    deps = {"a": [], "b": [], "c": ["b"], "d": []}
    return [Stage(n, mk(n), deps[n]) for n in "abcd"]


@pytest.mark.parametrize("beh,code", [
    ({"a": 0, "b": 0, "c": 0, "d": 0}, 0),
    ({"a": 0, "b": SourceUnavailableError("x", kind="proxy_denied"), "c": 0, "d": 0}, 2),
    ({"a": 0, "b": SourceUnavailableError("x", kind="proxy_denied"), "c": 0, "d": ValueError("bug")}, 1),
])
def test_run_order_statuses_and_exit_codes(cfg, tmp_path, monkeypatch, beh, code):
    import mshi.run as R
    monkeypatch.setattr(R, "_stages", lambda: _fake_stages(beh))
    sand = sandbox(cfg, tmp_path)
    assert R.run(["d", "c", "b", "a"], sand) == code
    recs = [json.loads(x) for x in sand.path("results", "run_log.jsonl").read_text().splitlines()]
    assert [r["stage"] for r in recs] == ["a", "b", "c", "d"]                   # pipeline order
    assert all(r["config_sha256"] == sand.sha256() and r["code_sha256"] for r in recs)
    st = {r["stage"]: r["status"] for r in recs}
    if isinstance(beh["b"], Exception):
        assert st["b"].startswith("blocked:") and st["c"].startswith("skipped: upstream b")
    if isinstance(beh["d"], Exception):
        assert st["d"].startswith("error: ValueError")


# ---------------------------------------------------------------- reproduction table

def _committed(cfg, name):
    d = json.loads(cfg.path("results", name).read_text())
    d.pop("_provenance", None)
    return d


@pytest.mark.data
def test_repro_checks_stale_not_run_and_fail(cfg, tmp_path):
    from mshi.analysis.repro_checks import ReproductionFailure, repro_checks
    sand = sandbox(cfg, tmp_path)
    for f in ["build_sites.json", "cosore_annual.json"]:
        write_result(sand, _committed(cfg, f), f)
    s = repro_checks(sand)
    assert s["PASS"] == 17 and s["FAIL"] == 0 and s["STALE"] == 0

    stale = sandbox(cfg, tmp_path, edit=lambda d: d["smoke"].__setitem__("seed", 1))   # any config change
    s = repro_checks(stale)
    assert s["STALE"] == 17 and s["PASS"] == 0

    sand.invocation = {"stages": ["build_sites"], "status": {"build_sites": "error: FileNotFoundError: x"}}
    s = repro_checks(sand)                       # this run's build_sites failed: its old file is not used
    assert s["PASS"] == 1 and s["NOT RUN"] >= 17
    rows = json.loads(sand.path("results", "reproduction_check.json").read_text())["rows"]
    assert any("build_sites: error (FileNotFoundError)" in r["note"] for r in rows)

    bad = sandbox(cfg, tmp_path, edit=lambda d: d["reproduction_targets"]["srdb_repo_filter_records"].__setitem__("value", 4770))
    for f in ["build_sites.json", "cosore_annual.json"]:
        write_result(bad, _committed(cfg, f), f)
    with pytest.raises(ReproductionFailure, match="SRDB records after repo filters"):
        repro_checks(bad)
    assert "| FAIL |" in bad.path("results", "reproduction_check.md").read_text()


# ---------------------------------------------------------------- clean_test stage (synthetic data)

@pytest.mark.data
@pytest.mark.slow
def test_clean_test_stage_success_path_on_synthetic_data(cfg, tmp_path, monkeypatch):
    from mshi.analysis import clean_test as CT
    sand = sandbox(cfg, tmp_path)
    rng = np.random.default_rng(0)
    sites = pd.read_parquet(cfg.path("derived", "sites_v3_qc.parquet"))
    d = sites[["site_id", "lat", "lon", "continent"]].copy()
    cols = set().union(*map(set, cfg["clean_test"]["locked"]["sets"].values()))
    for c in sorted(cols):
        d[c] = rng.gamma(3.0, 10.0, len(d))
    d["log_rs"] = 5.5 + 0.02 * d.bio01 + 0.1 * np.log(d.bio12) + rng.normal(0, 0.3, len(d))   # synthetic target
    sand.path("interim").mkdir(parents=True)
    for tag in cfg["clean_test"]["variants"]:
        d.to_parquet(sand.path("interim", f"features_v3_{tag}.parquet"), index=False)
    write_result(sand, {"synthetic": True}, "features.json")

    class Light(CT.LockedTest):
        def __init__(self, c, **kw):
            super().__init__(c, **kw)            # verifies the real lock
            self.L = copy.deepcopy(self.L)
            self.L["rf"]["n_estimators"] = self.L["xgb"]["n_estimators"] = 15
            self.L["bootstrap_n"], self.L["seed_spread"] = 30, [0, 1]

    monkeypatch.setattr(CT, "LockedTest", Light)
    res = CT.clean_test(sand)
    assert set(res) == set(cfg["clean_test"]["variants"])
    R = json.loads(sand.path("results", "clean_test_rerun_qc.json").read_text())
    assert R["lock"]["locked_sha256"] == CT.LOCKED_SHA256 and R["_provenance"]["config_sha256"] == sand.sha256()
    assert R["vs_locked"]["identical"] is False and "max_abs_primary_diff" in R["vs_locked"]
    assert not any(Path(cfg.path("handoff", "results")).glob("*rerun*"))       # locked results untouched


def test_clean_test_refuses_stale_features(cfg, tmp_path):
    from mshi.analysis.clean_test import clean_test
    sand = sandbox(cfg, tmp_path)
    write_json({"_provenance": {"config_sha256": "x", "code_sha256": "y"}}, sand.path("results", "features.json"))
    with pytest.raises(RuntimeError, match="re-run stage features"):
        clean_test(sand)


# ---------------------------------------------------------------- WorldClim zip handling

def test_fetch_worldclim_extracts_19_layers_and_reuses_zip(cfg, tmp_path, monkeypatch):
    from mshi.data import rasters
    sand = sandbox(cfg, tmp_path)
    src = tmp_path / "wc.zip"
    with zipfile.ZipFile(src, "w") as z:
        for i in range(1, 20):
            z.writestr(cfg["sources"]["worldclim"]["file_pattern"].format(i=i), f"layer {i}")
    calls = []

    def fake_download(url, dest, sha256=None, reuse_existing=False, **k):
        calls.append(url)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(src.read_bytes())
        return {"path": str(dest), "sha256": None, "downloaded": True}

    monkeypatch.setattr(rasters, "download", fake_download)
    r = rasters.fetch_worldclim(sand)
    assert len(r["tif_sha256"]) == 19 and r["zip_sha256"] and len(calls) == 1
    rasters.fetch_worldclim(sand)
    assert len(calls) == 1                         # layers present: nothing downloaded
