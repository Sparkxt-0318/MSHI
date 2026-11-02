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
from mshi.io import StaleInputError, write_json, write_result, write_table
from mshi.netutil import (ChecksumMismatchError, DownloadError, SourceUnavailableError, _git_proxy_denial,
                          _is_proxy_denial, download, git_checkout_commit, verify_git_checkout)


def sandbox(cfg, tmp_path, edit=None) -> Config:
    data = copy.deepcopy(cfg.data)
    data["paths"]["raw"] = str(tmp_path / "raw")
    if edit:
        edit(data)
    return Config(data, source=cfg.source, out_root=tmp_path / "out")


def full_sandbox(cfg, tmp_path, edit=None) -> Config:
    """Like ``sandbox`` but not a smoke run (out_root None): every output root is an absolute temp path."""
    data = copy.deepcopy(cfg.data)
    for root in ("raw", "interim", "derived", "results", "figures"):
        data["paths"][root] = str(tmp_path / "full" / root)
    if edit:
        edit(data)
    return Config(data, source=cfg.source)


def fake_build(sand, lat=(45.0, 45.01), lon=(10.0, 10.02)):
    """Tiny site tables plus a current build_sites.json recording them as outputs (stands in for build_sites)."""
    st = pd.DataFrame({"site_id": [f"s{i}" for i in range(len(lat))], "lat": lat, "lon": lon,
                       "continent": "Europe", "log_rs": 6.0})
    outs = [write_table(st, sand.path("derived", f"sites_v3_{t}.parquet")) for t in ("qc", "repo")]
    outs.append(write_table(st.assign(rec_id=st.site_id), sand.path("derived", "records_v3.parquet")))
    write_result(sand, {"fake": True}, "build_sites.json", outputs=outs)
    return st


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


@pytest.mark.parametrize("msg,denied", [
    ("Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')", True),
    ("Unable to connect to proxy', OSError('Tunnel connection failed: 407 Proxy Authentication Required')", True),
    # a dead proxy on port 1403, or a URL containing 403/407, is not a policy block
    ('NewConnectionError("HTTPSConnection(host=127.0.0.1, port=1403): Failed to establish a new connection: '
     '[Errno 111] Connection refused")', False),
    ("Max retries exceeded with url: /MOD11A2.A2020407_LST.tif (Caused by ProxyError('Unable to connect to "
     "proxy', OSError('Tunnel connection failed: 502 Bad Gateway')))", False),
])
def test_proxy_denial_matches_the_tunnel_status_only(msg, denied, tmp_path):
    e = requests.exceptions.ProxyError(msg)
    assert _is_proxy_denial(e) is denied
    s = _RaisingSession(e)
    with pytest.raises(SourceUnavailableError) as err:
        download("https://example.invalid/f403", tmp_path / "f", session=s, sleep=lambda x: None, retries=2)
    assert err.value.kind == ("proxy_denied" if denied else "unreachable")
    assert s.calls == (1 if denied else 2)


def test_git_proxy_denial_matches_the_tunnel_status_only():
    assert _git_proxy_denial("fatal: unable to access 'https://maps.isric.org/x.git/': CONNECT tunnel failed, "
                             "response 403")
    assert not _git_proxy_denial("fatal: unable to access 'https://h/repo403/': CONNECT tunnel failed, response 502")
    assert not _git_proxy_denial("fatal: unable to access 'https://h:1407/x/': Failed to connect to proxy port 1407")


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


def test_git_checkout_detects_ignored_files(tmp_path):
    """COSORE's .gitignore has unanchored 'doc' and 'Meta': a dataset directory with such a name would be
    read by cosore_annual but is invisible to a plain `git status`."""
    src = tmp_path / "origin"
    src.mkdir()
    _git("init", "-q", cwd=src)
    _git("config", "user.email", "t@example.invalid", cwd=src)
    _git("config", "user.name", "t", cwd=src)
    _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=src)
    (src / ".gitignore").write_text("Meta\ndoc\n")
    (src / "datasets" / "dA").mkdir(parents=True)
    (src / "datasets" / "dA" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\n")
    _git("add", ".", cwd=src)
    _git("commit", "-qm", "c1", cwd=src)
    commit = _git("rev-parse", "HEAD", cwd=src)
    dest = tmp_path / "co"
    git_checkout_commit(f"file://{src}", commit, dest)
    (dest / "datasets" / "doc").mkdir()
    (dest / "datasets" / "doc" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 2\n")
    with pytest.raises(ChecksumMismatchError, match="local changes"):
        verify_git_checkout(dest, commit)


def test_git_checkout_ignores_os_metadata_and_paths_that_are_not_read(tmp_path):
    """Third review: --ignored=matching refused a Finder .DS_Store or RStudio project files that no stage
    reads. The check now covers the paths that are read (datasets, licence), minus OS metadata files."""
    src = tmp_path / "origin"
    src.mkdir()
    _git("init", "-q", cwd=src)
    _git("config", "user.email", "t@example.invalid", cwd=src)
    _git("config", "user.name", "t", cwd=src)
    _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=src)
    (src / ".gitignore").write_text(".DS_Store\n.Rproj.user/\n.Rhistory\ndoc\n")
    (src / "datasets" / "dA").mkdir(parents=True)
    (src / "datasets" / "dA" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\n")
    (src / "LICENSE").write_text("CC-BY-4.0\n")
    _git("add", ".", cwd=src)
    _git("commit", "-qm", "c1", cwd=src)
    commit = _git("rev-parse", "HEAD", cwd=src)
    dest = tmp_path / "co"
    read = ["datasets", "LICENSE"]
    git_checkout_commit(f"file://{src}", commit, dest, pathspec=read)
    for junk in ["datasets/.DS_Store", "datasets/dA/.DS_Store", "datasets/dA/._DESCRIPTION.txt", ".Rhistory",
                 ".Rproj.user/x", "notes.txt"]:
        (dest / junk).parent.mkdir(parents=True, exist_ok=True)
        (dest / junk).write_text("x")
    verify_git_checkout(dest, commit, pathspec=read)                    # none of these is read
    assert git_checkout_commit(f"file://{src}", commit, dest, pathspec=read)["downloaded"] is False
    (dest / "datasets" / "doc").mkdir()                                # an ignored dataset directory: read
    (dest / "datasets" / "doc" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 2\n")
    with pytest.raises(ChecksumMismatchError, match="datasets/doc"):
        verify_git_checkout(dest, commit, pathspec=read)
    (dest / "datasets" / "doc" / "DESCRIPTION.txt").unlink()
    (dest / "datasets" / "doc").rmdir()
    (dest / "LICENSE").write_text("MIT\n")                             # a file that is read, modified
    with pytest.raises(ChecksumMismatchError, match="LICENSE"):
        verify_git_checkout(dest, commit, pathspec=read)
    assert _git("config", "core.autocrlf", cwd=dest) == "false"         # no line-ending conversion


@pytest.mark.parametrize("stderr,kind", [
    ("fatal: unable to access 'https://github.com/bpbond/cosore/': CONNECT tunnel failed, response 403", "proxy_denied"),
    ("fatal: unable to access 'https://github.com/bpbond/cosore/': CONNECT tunnel failed, response 407", "proxy_denied"),
    ("fatal: unable to access 'https://github.com/bpbond/cosore/': CONNECT tunnel failed, response 502", "transient"),
    ("fatal: unable to access 'https://github.com/x/': The requested URL returned error: 503", "http"),
    ("error: RPC failed; HTTP 502 curl 22 The requested URL returned error: 502", "http"),
    ("fatal: unable to access 'https://github.com/x/': The requested URL returned error: 429", "http"),
    ("error: RPC failed; curl 56 GnuTLS recv error (-9): A TLS packet with unexpected length was received.", "transient"),
    ("fatal: unable to access 'https://github.com/x/': Could not resolve host: github.com", "transient"),
    ("fatal: unable to access 'https://github.com/x/': The requested URL returned error: 404", "fatal"),
    ("fatal: remote error: upload-pack: not our ref 02f32e8e7f9a0f1c26c9dad61c574aef863f1df1", "fatal"),
])
def test_git_fetch_failures_are_classified_like_downloads(stderr, kind):
    from mshi.netutil import _git_failure_kind
    assert _git_failure_kind(stderr) == kind


def test_git_fetch_retries_a_5xx_then_reports_a_download_error(server, tmp_path):
    """Third review: a GitHub 5xx failed at once; it is now retried (2, 4, 8 s), then DownloadError, as for
    HTTP in ``download``. 127.0.0.1 is in no_proxy, so git talks to the local server directly."""
    sleeps = []
    with pytest.raises(DownloadError, match="after 4 attempts.*502"):
        git_checkout_commit(f"{server}/502/repo.git", "0" * 40, tmp_path / "co", sleep=sleeps.append)
    assert sleeps == [2, 4, 8] and _Handler.hits["/502/repo.git/info/refs?service=git-upload-pack"] == 4


# ---------------------------------------------------------------- MODIS

M = {"window_deg": 0.05, "retries": 1, "threads": 4, "second_pass_threads": 2, "accepted_catalog_gaps": [],
     "datetime": "2020-01-01/2024-12-31", "max_items_per_tile": 500,
     "sinusoidal_proj": "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext", "tile_size_m": 1111950.5197,
     "x_origin_m": -20015109.354, "y_origin_m": 10007554.677,
     "npp": {"collection": "npp-col", "item_prefix": "MOD17A3HGF", "asset": "Npp_500m", "valid_range": [0, 32700],
             "scale": 0.1, "offset": 0.0},
     "lst": {"collection": "lst-col", "item_prefix": "MOD11A2", "assets": {"lst_day": "D", "lst_night": "N"},
             "valid_min_exclusive": 0, "scale": 0.02, "offset": -273.15, "composite": "first_of_month",
             "composite_days": 8}}


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
        for y in range(2020, 2025):
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
    assert len(day) == 60 and all(j[3].day == 1 and "MOD11" in j[1] for j in day)
    assert len([j for j in jobs if j[0] == "lst_night"]) == 60


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
    fake_build(sand)
    pts = _pts()[["lat", "lon", "site_key"]]
    monkeypatch.setattr(modis, "modis_point_set", lambda c: pts)
    monkeypatch.setattr(N, "check_reachable", lambda *a, **k: None)
    state = {"fail": True, "calls": 0}

    def fake_extract(p, m):
        state["calls"] += 1
        out = pd.DataFrame({"site_key": p.site_key, "npp": 500.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                            "lst_night": 5.0, "lst_night_n": 60})
        return out, {"n_jobs": 125, "n_reads": 125, "n_tiles": 1,
                     "failed_reads": ["mem://x: OSError"] if state["fail"] else [],
                     "catalog_gaps": [], "accepted_catalog_gaps": [], "lst_same_date_ties": [],
                     "npp_duplicate_years": [], "periods_outside_datetime": []}

    monkeypatch.setattr(modis, "extract_points", fake_extract)
    with pytest.raises(modis.ModisIncompleteError):
        modis.modis_points(sand)
    rec = json.loads(sand.path("results", "modis_points.json").read_text())
    assert rec["n_failed_reads"] == 1 and rec["status"].startswith("incomplete")
    assert not sand.path("interim", "modis_points.parquet").exists()
    with pytest.raises(modis.StaleModisError, match="missing"):        # a StaleInputError: readers are 'stale'
        modis.load_modis_points(sand)

    state["fail"] = False
    r1 = modis.modis_points(sand)
    assert r1["n_failed_reads"] == 0 and state["calls"] == 2
    j1 = sand.path("results", "modis_points.json").read_text()
    r2 = modis.modis_points(sand)                                       # cache hit: same record, no extraction
    assert r2["cached"] and state["calls"] == 2 and sand.path("results", "modis_points.json").read_text() == j1
    assert len(modis.load_modis_points(sand, pts.site_key)) == 2

    out_path = sand.path("interim", "modis_points.parquet")             # a table replaced after the run
    good = out_path.read_bytes()
    write_table(pd.read_parquet(out_path).assign(npp=lambda d: d.npp + 100), out_path)
    with pytest.raises(modis.StaleModisError, match="changed after the extraction"):
        modis.load_modis_points(sand)
    with pytest.raises(StaleInputError, match="changed after the run"):  # what features checks first
        from mshi.io import require_outputs
        require_outputs(sand, "modis_points.json", [out_path])
    modis.modis_points(sand)
    assert state["calls"] == 3 and out_path.read_bytes() == good       # not reused: re-extracted

    changed = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["modis"].__setitem__("window_deg", 0.25))
    with pytest.raises(modis.StaleModisError):
        modis.load_modis_points(changed)                                # features would refuse it
    with pytest.raises(StaleInputError, match="build_sites.json"):     # site tables from the other config
        modis.modis_points(changed)
    fake_build(changed)
    modis.modis_points(changed)
    assert state["calls"] == 4                                          # config change -> re-extracted


def test_modis_cache_key_covers_the_whole_module_and_libraries(cfg, tmp_path, monkeypatch):
    import hashlib
    from mshi.data import modis
    assert modis._extraction_code_sha256() == hashlib.sha256(Path(modis.__file__).read_bytes()).hexdigest()
    lib = modis._library_versions()
    assert set(lib) == {"numpy", "rasterio", "gdal", "pyproj", "proj"} and all(lib.values())
    sand = sandbox(cfg, tmp_path)
    df = pd.DataFrame({"site_key": ["a"], "npp": [1.0]})
    modis.write_modis_cache(sand, df, modis.modis_cache_key(sand, df.site_key), {"n_failed_reads": 0})
    assert len(modis.load_modis_points(sand)) == 1
    monkeypatch.setattr(modis, "_library_versions", lambda: {**lib, "gdal": "0.0"})     # another GDAL
    with pytest.raises(modis.StaleModisError, match="libraries"):
        modis.load_modis_points(sand)
    monkeypatch.setattr(modis, "_library_versions", lambda: lib)
    monkeypatch.setattr(modis, "_extraction_code_sha256", lambda: "0" * 64)            # edited module
    with pytest.raises(modis.StaleModisError, match="code_sha256"):
        modis.load_modis_points(sand)


class GappyCatalog(FakeCatalog):
    def __init__(self, drop_npp=(), drop_lst_month=None, tie=False):
        super().__init__()
        self.npp = [i for i in self.npp if not any(f"A{y}" in i.id for y in drop_npp)]
        if drop_lst_month:
            self.lst = [i for i in self.lst if not i.id.startswith(f"MOD11A2.{drop_lst_month}")]
        if tie:     # a second Terra item on the date of the first March-2021 composite, with a smaller id
            self.lst.append(_item("MOD11A2.20210300.B", (2021, 3, 1), ["D", "N"]))


def _reads(monkeypatch, seen):
    from mshi.data import modis

    def fake_read(href, sub, kind, m):
        seen.append(href.split("?")[0])
        return {k: 100.0 for k in sub.site_key}
    monkeypatch.setattr(modis, "read_windows", fake_read)
    monkeypatch.setattr("mshi.netutil.check_reachable", lambda *a, **k: None)


def test_catalog_gap_fails_before_any_raster_is_read(monkeypatch):
    from mshi.data import modis
    seen = []
    _reads(monkeypatch, seen)
    tile = "h{:02d}v{:02d}".format(*map(int, (_pts().h.iat[0], _pts().v.iat[0])))
    out, info = modis.extract_points(_pts(), M, catalog=GappyCatalog(drop_npp=[2023], drop_lst_month="202205"),
                                     tokens=_Tokens())
    assert info["catalog_gaps"] == [f"{tile} lst 2022-05", f"{tile} npp 2023"] and seen == [] and out.empty
    m = copy.deepcopy(M)
    m["accepted_catalog_gaps"] = [f"{tile} npp 2023", f"{tile} lst 2022-05"]          # reviewed, accepted
    out, info = modis.extract_points(_pts(), m, catalog=GappyCatalog(drop_npp=[2023], drop_lst_month="202205"),
                                     tokens=_Tokens())
    assert info["catalog_gaps"] == [] and len(info["accepted_catalog_gaps"]) == 2
    assert (out.npp_n == 4).all() and (out.lst_day_n == 59).all()
    m = copy.deepcopy(M)
    m["max_items_per_tile"] = 5                                        # 6 NPP items: possibly truncated
    _, info = modis.extract_points(_pts(), m, kinds=("npp",), catalog=FakeCatalog(), tokens=_Tokens())
    assert info["catalog_gaps"] == [f"{tile} npp truncated"]


def test_missing_first_composite_of_a_month_is_a_catalog_gap(monkeypatch):
    """Third review: the check was month-granular, so a month whose first 8-day composite is missing (but a
    later one present) passed, and its mean silently used the later composite."""
    from mshi.data import modis
    seen = []
    _reads(monkeypatch, seen)
    tile = "h{:02d}v{:02d}".format(*map(int, (_pts().h.iat[0], _pts().v.iat[0])))
    cat = FakeCatalog()
    cat.lst = [i for i in cat.lst if i.id != "MOD11A2.20210101"]      # Jan 2021: day 9 and 17 remain
    out, info = modis.extract_points(_pts(), M, catalog=cat, tokens=_Tokens())
    assert info["catalog_gaps"] == [f"{tile} lst 2021-01 first composite"] and seen == [] and out.empty
    m = copy.deepcopy(M)
    m["accepted_catalog_gaps"] = [f"{tile} lst 2021-01 first composite"]
    out, info = modis.extract_points(_pts(), m, catalog=cat, tokens=_Tokens())
    assert (out.lst_day_n == 60).all() and info["accepted_catalog_gaps"] == m["accepted_catalog_gaps"]


def test_periods_outside_the_datetime_range_are_used_and_recorded(monkeypatch):
    """A composite dated before the range but returned by the search (e.g. late December 2019) is used, as
    in the prototype, and listed."""
    from mshi.data import modis
    seen = []
    _reads(monkeypatch, seen)
    tile = "h{:02d}v{:02d}".format(*map(int, (_pts().h.iat[0], _pts().v.iat[0])))
    cat = FakeCatalog()
    cat.lst.append(_item("MOD11A2.20191227", (2019, 12, 27), ["D", "N"]))
    out, info = modis.extract_points(_pts(), M, catalog=cat, tokens=_Tokens())
    assert info["catalog_gaps"] == [] and info["periods_outside_datetime"] == [f"{tile} lst 2019-12"]
    assert (out.lst_day_n == 61).all() and info["n_reads"] == info["n_jobs"] == len(seen)


def test_modis_points_writes_nothing_on_a_catalog_gap(cfg, tmp_path, monkeypatch):
    from mshi.data import modis
    sand = sandbox(cfg, tmp_path)
    fake_build(sand)
    monkeypatch.setattr(modis, "modis_point_set", lambda c: _pts()[["lat", "lon", "site_key"]])
    monkeypatch.setattr("mshi.netutil.check_reachable", lambda *a, **k: None)
    gaps = [f"h18v04 lst 2021-{i:02d}" for i in range(1, 13)] * 10 + ["h18v04 npp 2023"]      # 121 gaps

    def gap_extract(p, m):              # what extract_points returns when the catalog lacks items
        return pd.DataFrame(), {"n_jobs": 373, "n_reads": 0, "n_tiles": 1, "failed_reads": [], "catalog_gaps": gaps,
                                "accepted_catalog_gaps": [], "lst_same_date_ties": [], "npp_duplicate_years": [],
                                "periods_outside_datetime": []}
    monkeypatch.setattr(modis, "extract_points", gap_extract)
    with pytest.raises(modis.ModisIncompleteError, match="lacks 121 expected item"):
        modis.modis_points(sand)
    rec = json.loads(sand.path("results", "modis_points.json").read_text())
    assert rec["status"].startswith("incomplete") and rec["catalog_gaps"] == gaps    # complete list, to copy
    assert rec["n_raster_reads"] == 0 and rec["n_planned_reads"] == 373               # nothing was read
    assert not sand.path("interim", "modis_points.parquet").exists()


@pytest.mark.parametrize("reverse", [False, True])
def test_lst_same_date_tie_broken_by_id_and_recorded(monkeypatch, reverse):
    from mshi.data import modis
    cat = GappyCatalog(tie=True)
    if reverse:
        cat.lst = list(reversed(cat.lst))                              # API order must not matter
    stats = {}
    jobs = modis.plan_jobs(_pts(), M, cat, stats=stats)
    assert [t["month"] for t in stats["lst_same_date_ties"]] == ["2021-03"]
    assert stats["lst_same_date_ties"][0]["chosen"] == "MOD11A2.20210300.B"
    assert stats["lst_same_date_ties"][0]["others"] == ["MOD11A2.20210301"]
    march = [j for j in jobs if j[0] == "lst_day" and (j[3].year, j[3].month) == (2021, 3)]
    assert [j[1] for j in march] == ["mem://MOD11A2.20210300.B/D"]


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
    ({"a": 0, "b": StaleInputError("results/x.json: produced with a different config"), "c": 0, "d": 0}, 2),
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
    if isinstance(beh["b"], SourceUnavailableError):
        assert st["b"].startswith("blocked:") and st["c"].startswith("skipped: upstream b")
    if isinstance(beh["b"], StaleInputError):
        assert st["b"].startswith("stale: results/x.json") and st["c"].startswith("skipped: upstream b")
    if isinstance(beh["d"], Exception):
        assert st["d"].startswith("error: ValueError")


def _gate_stages(beh):
    from mshi.analysis.repro_checks import ReproductionFailure
    from mshi.run import Stage

    def mk(name):
        def f(cfg):
            b = beh.get(name, 0)
            if b == "fail":
                raise ReproductionFailure("1 reproduction target(s) outside tolerance")
            if b == "stale":
                raise StaleInputError("2 reproduction row(s) come from results that are not current")
            if name == "repro_checks":     # as the real stage: the table, then ok (NOT RUN rows are not errors)
                notrun = 10 if b == "notrun" else 0
                write_result(cfg, {"summary": {"PASS": 17, "FAIL": 0, "STALE": 0, "NOT RUN": notrun}},
                             "reproduction_check.json")
            return {"ok": name}
        return f
    return [Stage("build", mk("build")), Stage("repro_checks", mk("repro_checks")),
            Stage("phase2", mk("phase2"), ["build"])]


@pytest.mark.parametrize("repro,code,phase2", [("ok", 0, "ok"), ("fail", 1, "skipped: reproduction gate closed"),
                                               ("stale", 2, "skipped: reproduction gate closed"),
                                               ("notrun", 2, "skipped: reproduction gate closed")])
def test_stages_after_repro_checks_need_a_passing_table(cfg, tmp_path, monkeypatch, repro, code, phase2):
    import mshi.run as R
    monkeypatch.setattr(R, "_stages", lambda: _gate_stages({"repro_checks": repro}))
    sand = full_sandbox(cfg, tmp_path)
    assert R.run(["build", "repro_checks", "phase2"], sand) == code
    st = {r["stage"]: r["status"] for r in map(json.loads, sand.path("results", "run_log.jsonl").read_text().splitlines())}
    assert st["phase2"].startswith(phase2)


def test_gate_uses_the_stored_table_when_repro_checks_is_not_run(cfg, tmp_path, monkeypatch):
    import mshi.run as R
    monkeypatch.setattr(R, "_stages", lambda: _gate_stages({}))
    sand = full_sandbox(cfg, tmp_path)
    last = lambda: json.loads(sand.path("results", "run_log.jsonl").read_text().splitlines()[-1])["status"]  # noqa: E731
    assert R.run(["phase2"], sand) == 2 and "reproduction_check.json: missing" in last()
    write_result(sand, {"summary": {"FAIL": 1, "STALE": 0}}, "reproduction_check.json")
    assert R.run(["phase2"], sand) == 2 and "'FAIL': 1" in last()
    write_result(sand, {"summary": {"FAIL": 0, "STALE": 0, "PASS": 7, "NOT RUN": 10}}, "reproduction_check.json")
    assert R.run(["phase2"], sand) == 2 and "'NOT RUN': 10" in last()      # not reproduced is not passed
    write_result(sand, {"summary": {"FAIL": 0, "STALE": 0, "PASS": 17}}, "reproduction_check.json")
    assert R.run(["phase2"], sand) == 0 and last() == "ok"
    other = full_sandbox(cfg, tmp_path, edit=lambda d: d["smoke"].__setitem__("seed", 1))  # table: other config
    assert R.run(["phase2"], other) == 2 and "different config" in last()


def test_results_carry_the_code_hash_taken_when_the_run_started(cfg, tmp_path, monkeypatch):
    """A stage whose code is edited while it runs must not stamp its result with the edited code's hash."""
    import mshi.run as R
    import mshi.runlog as RL
    from mshi.io import result_staleness
    hashes = iter(["A"] + ["B"] * 50)
    monkeypatch.setattr(RL, "code_sha256", lambda pkg_dir=None: next(hashes))

    def stage(c):
        write_result(c, {"x": 1}, "x.json")
        return {}
    monkeypatch.setattr(R, "_stages", lambda: [R.Stage("x", stage, [])])
    sand = sandbox(cfg, tmp_path)
    assert R.run(["x"], sand) == 0
    obj = json.loads(sand.path("results", "x.json").read_text())
    assert obj["_provenance"]["code_sha256"] == "A"
    assert result_staleness(sand, obj) == "produced with a different code"
    assert "provenance" not in sand.invocation                         # later direct calls stamp their own


# ---------------------------------------------------------------- provenance chain

def test_outputs_are_bound_to_their_result(cfg, tmp_path):
    from mshi.io import require_outputs, result_staleness
    sand = sandbox(cfg, tmp_path)
    st = fake_build(sand)
    tables = [sand.path("derived", f) for f in ("sites_v3_qc.parquet", "sites_v3_repo.parquet")]
    obj = require_outputs(sand, "build_sites.json", tables)
    assert set(obj["_outputs"]) == {"derived:sites_v3_qc.parquet", "derived:sites_v3_repo.parquet",
                                    "derived:records_v3.parquet"}
    write_table(st.assign(log_rs=7.0), tables[0])                     # replaced after the run
    assert "changed after the run" in result_staleness(sand, obj)
    with pytest.raises(StaleInputError, match="sites_v3_qc.parquet changed after the run"):
        require_outputs(sand, "build_sites.json", tables)
    tables[0].unlink()
    assert "missing its output" in result_staleness(sand, obj)
    fake_build(sand)
    with pytest.raises(StaleInputError, match="not an output recorded"):
        require_outputs(sand, "build_sites.json", [sand.path("derived", "other.parquet")])
    write_result(sand, {"status": "incomplete: no values written"}, "modis_points.json")
    with pytest.raises(StaleInputError, match="incomplete"):
        require_outputs(sand, "modis_points.json", [])


def test_build_sites_refuses_a_cosore_table_from_another_config(cfg, tmp_path):
    from mshi.data.sites import load_cosore_records
    sand = sandbox(cfg, tmp_path)
    csv = write_table(pd.DataFrame({"site_id": ["cosore_a"], "source": ["cosore"], "longitude": [10.0],
                                    "latitude": [45.0], "rs_annual": [500.0], "igbp": ["DBF"]}),
                      sand.path("derived", "cosore_annual.csv"))
    write_result(sand, {"n_sites": 1}, "cosore_annual.json", outputs=[csv])
    assert len(load_cosore_records(sand)) == 1
    other = sandbox(cfg, tmp_path, edit=lambda d: d["cosore_annual"].__setitem__("molar_mass_c", 12.0))
    with pytest.raises(StaleInputError, match="cosore_annual.json: produced with a different config"):
        load_cosore_records(other)                     # build_sites under the new config, before cosore_annual


@pytest.mark.data
def test_site_diagnostics_refuses_stale_site_tables(cfg, tmp_path):
    from mshi.analysis.site_diagnostics import site_diagnostics
    sand = sandbox(cfg, tmp_path)
    fake_build(sand)
    other = sandbox(cfg, tmp_path, edit=lambda d: d["site_build"].__setitem__("merge_radius_km", 2.0))
    with pytest.raises(StaleInputError, match="build_sites.json"):
        site_diagnostics(other)


def test_features_verifies_every_input_it_reads(cfg, monkeypatch):
    from mshi.data import features as F
    calls = []

    def rec(c, name, paths):
        calls.append((name, [Path(p).name for p in paths]))
        return {}
    monkeypatch.setattr(F, "require_outputs", rec)
    F.verify_inputs(cfg)
    got = dict(calls)
    assert got["build_sites.json"] == ["sites_v3_qc.parquet", "sites_v3_repo.parquet"]
    assert got["modis_points.json"] == ["modis_points.parquet"]
    assert got["fetch_worldclim.json"] == [f"wc2.1_2.5m_bio_{i}.tif" for i in range(1, 20)]
    sg = cfg["sources"]["soilgrids"]
    assert got["fetch_soilgrids.json"] == [f"{v}_5-15cm_mean_global_0p05.tif" for v in sg["variables"]]


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
    with pytest.raises(StaleInputError, match="17 reproduction row"):
        repro_checks(stale)
    s = json.loads(stale.path("results", "reproduction_check.json").read_text())["summary"]
    assert s["STALE"] == 17 and s["PASS"] == 0

    # a site table changed after build_sites wrote it: its rows are STALE (outputs are bound to results)
    outs = []
    for f in ["sites_v3_qc.parquet", "sites_v3_repo.parquet", "records_v3.parquet"]:
        dst = sand.path("derived", f)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(cfg.path("derived", f).read_bytes())
        outs.append(dst)
    write_result(sand, _committed(cfg, "build_sites.json"), "build_sites.json", outputs=outs)
    assert repro_checks(sand)["PASS"] == 17
    outs[0].write_bytes(outs[0].read_bytes() + b"\0")
    with pytest.raises(StaleInputError):
        repro_checks(sand)
    rows = json.loads(sand.path("results", "reproduction_check.json").read_text())["rows"]
    assert sum(r["status"] == "STALE" for r in rows) == 16 and "changed after the run" in rows[1]["note"]
    write_result(sand, _committed(cfg, "build_sites.json"), "build_sites.json")

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
    outs = [write_table(d, sand.path("interim", f"features_v3_{tag}.parquet")) for tag in cfg["clean_test"]["variants"]]
    write_result(sand, {"synthetic": True}, "features.json", outputs=outs)

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
    write_table(d.assign(log_rs=d.log_rs + 1), outs[0])                       # features table replaced
    with pytest.raises(StaleInputError, match="features_v3_qc.parquet changed after the run"):
        CT.clean_test(sand)


def test_clean_test_refuses_stale_features(cfg, tmp_path):
    from mshi.analysis.clean_test import clean_test
    sand = sandbox(cfg, tmp_path)
    write_json({"_provenance": {"config_sha256": "x", "code_sha256": "y"}}, sand.path("results", "features.json"))
    with pytest.raises(StaleInputError, match="features.json: produced with a different config and code"):
        clean_test(sand)
    assert not sand.path("results", "clean_test_rerun_qc.json").exists()


# ---------------------------------------------------------------- WorldClim zip handling

class _BytesSession:
    """requests.Session stand-in for ``netutil.download``: serves fixed bytes, or a proxy denial when offline."""

    def __init__(self, data: bytes):
        self.data, self.offline, self.calls = data, False, 0

    def get(self, url, params=None, stream=True, timeout=None):
        if self.offline:
            raise requests.exceptions.ProxyError("Tunnel connection failed: 403 Forbidden")
        self.calls += 1
        data = self.data

        class _R:
            status_code, reason = 200, "OK"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_content(self, n):
                yield data
        return _R()


def test_fetch_worldclim_extracts_19_layers_and_reuses_zip(cfg, tmp_path, monkeypatch):
    import hashlib
    from mshi.data import rasters
    sand = sandbox(cfg, tmp_path)
    src = tmp_path / "wc.zip"
    with zipfile.ZipFile(src, "w") as z:
        for i in range(1, 20):
            z.writestr(cfg["sources"]["worldclim"]["file_pattern"].format(i=i), f"layer {i}")
    web = _BytesSession(src.read_bytes())
    monkeypatch.setattr(rasters, "download", lambda url, dest, sha256=None, **k:
                        download(url, dest, sha256=sha256, session=web, sleep=lambda s: None))   # the real one
    r = rasters.fetch_worldclim(sand)
    assert len(r["tif_sha256"]) == 19 and r["zip_sha256"] == hashlib.sha256(web.data).hexdigest() and web.calls == 1
    out = json.loads(sand.path("results", "fetch_worldclim.json").read_text())
    assert len(out["_outputs"]) == 19 and all(k.startswith("raw:worldclim/") for k in out["_outputs"])
    rasters.fetch_worldclim(sand)
    assert web.calls == 1                          # layers present and recorded: nothing downloaded
    rasters.worldclim_path(sand, 1).write_bytes(b"replaced")
    r2 = rasters.fetch_worldclim(sand)             # a replaced layer is re-extracted from the recorded zip
    assert web.calls == 1 and r2["tif_sha256"] == r["tif_sha256"]

    web.offline = True                             # e.g. geodata.ucdavis.edu blocked, as in this container
    good = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["worldclim"].__setitem__("sha256", r["zip_sha256"]))
    assert rasters.fetch_worldclim(good)["tif_sha256"] == r["tif_sha256"]      # pinning the recorded hash:
    assert web.calls == 1                                                      # no request, nothing deleted
    fewer = sandbox(cfg, tmp_path, edit=lambda d: d["features"].__setitem__("worldclim_vars", 12))
    assert len(rasters.fetch_worldclim(fewer)["tif_sha256"]) == 12 and web.calls == 1   # re-extracted, offline
    wrong = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["worldclim"].__setitem__("sha256", "0" * 64))
    zpath = rasters.worldclim_dir(sand).parent / cfg["sources"]["worldclim"]["url"].rsplit("/", 1)[-1]
    with pytest.raises(SourceUnavailableError):
        rasters.fetch_worldclim(wrong)             # another pin needs a download: blocked ...
    assert hashlib.sha256(zpath.read_bytes()).hexdigest() == r["zip_sha256"]       # ... and nothing was deleted
    assert all(rasters.worldclim_path(sand, i).exists() for i in range(1, 20))
    web.offline = False
    with pytest.raises(ChecksumMismatchError):
        rasters.fetch_worldclim(wrong)             # online: the bytes are not the pinned ones; zip kept
    assert hashlib.sha256(zpath.read_bytes()).hexdigest() == r["zip_sha256"] and web.calls == 2
    zpath.with_name(zpath.name + ".source.json").unlink()                     # a zip without its sidecar
    web.offline = True
    assert rasters.fetch_worldclim(good)["zip_sha256"] == r["zip_sha256"] and web.calls == 2   # pin: no request


def _tiff_download(calls, state=None):
    def fake(url, dest, params=None, session=None, **k):
        if state and state.get("offline"):
            raise SourceUnavailableError(f"{url}: blocked by proxy", kind="proxy_denied")
        calls.append(params["COVERAGEID"])
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"II*\x00" + params["COVERAGEID"].encode() + b"\0" * 20000)
        return {"path": str(dest), "sha256": None, "downloaded": True}
    return fake


def test_fetch_soilgrids_refetches_when_the_request_or_file_changes(cfg, tmp_path, monkeypatch):
    from mshi.data import rasters
    calls = []
    monkeypatch.setattr(rasters, "download", _tiff_download(calls))
    sand = sandbox(cfg, tmp_path)
    n = len(cfg["sources"]["soilgrids"]["variables"])
    r = rasters.fetch_soilgrids(sand)
    assert len(calls) == n and len(r["files_sha256"]) == n
    rasters.fetch_soilgrids(sand)
    assert len(calls) == n                                            # unchanged: nothing fetched
    q50 = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["soilgrids"].__setitem__("statistic", "Q0.5"))
    r = rasters.fetch_soilgrids(q50)
    assert len(calls) == 2 * n and all("Q0.5" in f for f in r["files_sha256"])     # new request, new files
    lat = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["soilgrids"].__setitem__("lat", [-60, 84]))
    rasters.fetch_soilgrids(lat)
    assert len(calls) == 3 * n                                        # same file names, other request
    p = rasters.soilgrids_path(lat, "soc")
    p.write_bytes(p.read_bytes() + b"x")
    rasters.fetch_soilgrids(lat)
    assert len(calls) == 3 * n + 1                                    # a changed file is fetched again
    orig = rasters.soilgrids_params
    monkeypatch.setattr(rasters, "soilgrids_params",                  # a code change to the WCS request
                        lambda sg, v: {**orig(sg, v), "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/3857"})
    rasters.fetch_soilgrids(lat)
    assert len(calls) == 4 * n + 1                                    # fetched again, not reused


def test_fetch_soilgrids_keeps_its_files_when_a_refetch_fails(cfg, tmp_path, monkeypatch):
    from mshi.data import rasters
    from mshi.io import sha256_file
    calls, state = [], {}
    monkeypatch.setattr(rasters, "download", _tiff_download(calls, state))
    sand = sandbox(cfg, tmp_path)
    rasters.fetch_soilgrids(sand)
    p = rasters.soilgrids_path(sand, "soc")
    before = sha256_file(p)
    state["offline"] = True
    lat = sandbox(cfg, tmp_path, edit=lambda d: d["sources"]["soilgrids"].__setitem__("lat", [-60, 84]))
    with pytest.raises(SourceUnavailableError):
        rasters.fetch_soilgrids(lat)                                  # new request, source blocked
    assert sha256_file(p) == before and not p.with_name(p.name + ".new").exists()



# ---------------------------------------------------------------- reproduction table: NPP and re-run rows

def _repro_sandbox(cfg, tmp_path, edit=None):
    sand = sandbox(cfg, tmp_path, edit)
    for f in ["build_sites.json", "cosore_annual.json"]:
        write_result(sand, _committed(cfg, f), f)
    return sand


def _rows(sand):
    return {r["quantity"]: r for r in json.loads(sand.path("results", "reproduction_check.json").read_text())["rows"]}


@pytest.mark.data
def test_repro_npp_rows_stale_and_fail(cfg, tmp_path):
    from mshi.analysis.repro_checks import ReproductionFailure, repro_checks
    from mshi.data import modis
    from mshi.io import read_table
    sand = _repro_sandbox(cfg, tmp_path)
    o = pd.concat([read_table(cfg, cfg.repo_path(r)) for r in cfg["legacy_allowlist"]])
    keys = modis.site_key(o.latitude, o.longitude).values
    df = pd.DataFrame({"site_key": keys, "npp": np.nan, "npp_n": 0})       # current, but no NPP at all
    out = modis.write_modis_cache(sand, df, modis.modis_cache_key(sand, keys), {"n_failed_reads": 0})
    write_result(sand, {"n_failed_reads": 0}, "modis_points.json", outputs=[out])
    with pytest.raises(ReproductionFailure, match="NPP r"):
        repro_checks(sand)
    row = next(r for q, r in _rows(sand).items() if q.startswith("NPP r"))
    assert row["status"] == "FAIL" and "r not computable: 0 original sites" in row["note"]

    other = _repro_sandbox(cfg, tmp_path, edit=lambda d: d["smoke"].__setitem__("seed", 1))   # json now stale
    write_result(other, _committed(cfg, "build_sites.json"), "build_sites.json")
    write_result(sand, {"n_failed_reads": 0}, "modis_points.json", outputs=[out])              # under sand's config
    with pytest.raises(StaleInputError):
        repro_checks(other)
    rows = _rows(other)
    npp = next(r for q, r in rows.items() if q.startswith("NPP r"))
    info = rows["Original sites with NPP missing in the committed tables but present in v3"]
    assert npp["status"] == "STALE" and info["status"] == "STALE" and "different config" in npp["note"]


@pytest.mark.data
def test_repro_rerun_rows_for_both_variants(cfg, tmp_path):
    from mshi.analysis.repro_checks import ReproductionFailure, repro_checks
    sand = _repro_sandbox(cfg, tmp_path)
    locked = {t: json.loads(cfg.repo_path(f["file"]).read_text()) for t, f in cfg["clean_test"]["locked_results"].items()}
    vs_same = {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0}
    write_result(sand, {**locked["qc"], "vs_locked": vs_same}, "clean_test_rerun_qc.json")
    write_result(sand, {**locked["repo"], "vs_locked": {"identical": False, "selected_same": False,
                                                        "max_abs_primary_diff": 0.4}}, "clean_test_rerun_repo.json")
    s = repro_checks(sand)
    rows = _rows(sand)
    repo = rows["Locked test (repo-filter sensitivity): re-run identical to the locked result"]
    assert s["DEVIATION"] == 1 and repo["status"] == "DEVIATION" and "another model selected" in repo["v3"]
    assert rows["Locked test: re-run identical to the locked result"]["status"] == "PASS"
    write_result(sand, {**locked["repo"], "vs_locked": {"identical": False, "selected_same": True,
                                                        "max_abs_primary_diff": None}}, "clean_test_rerun_repo.json")
    repro_checks(sand)                                                 # no TypeError on a missing diff
    assert "no primary metrics" in _rows(sand)[repo["quantity"]]["v3"]
    write_result(sand, dict(locked["repo"]), "clean_test_rerun_repo.json")      # no vs_locked block
    with pytest.raises(ReproductionFailure, match="repo-filter sensitivity"):
        repro_checks(sand)
    assert "no valid vs_locked" in _rows(sand)[repo["quantity"]]["note"]
