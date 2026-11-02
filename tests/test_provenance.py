"""Provenance chain and reproduction gate (third review, docs/DECISIONS.md R-P1-21).

A result is current only if its config and code hashes match, its recorded outputs still have their bytes
(an output under a gitignored root may be absent), and every upstream result it read still has the bytes
it read and is itself current. Offline: sandboxes, tiny tables, stand-in stages; nothing is scored.
"""
import json

import pandas as pd
import pytest

from mshi.io import StaleInputError, require_current, require_outputs, result_staleness, write_result, write_table
from test_robustness import _committed, full_sandbox, sandbox


def _res(sand, name):
    return json.loads(sand.path("results", name).read_text())


def _chain(sand):
    """up.json (output interim:a.parquet) -> down.json (output derived:b.parquet, input up.json) -> top.json."""
    a = write_table(pd.DataFrame({"x": [1.0, 2.0]}), sand.path("interim", "a.parquet"))
    write_result(sand, {"n": 1}, "up.json", outputs=[a])
    require_outputs(sand, "up.json", [a])
    b = write_table(pd.DataFrame({"y": [3.0]}), sand.path("derived", "b.parquet"))
    write_result(sand, {"m": 1}, "down.json", outputs=[b], inputs=["up.json"])
    require_current(sand, "down.json")
    write_result(sand, {"k": 1}, "top.json", inputs=["down.json"])
    return a, b


def test_a_result_is_bound_to_the_upstream_results_it_read(cfg, tmp_path):
    sand = full_sandbox(cfg, tmp_path)
    a, _ = _chain(sand)
    assert set(_res(sand, "down.json")["_inputs"]) == {"up.json"}
    assert all(result_staleness(sand, _res(sand, n)) is None for n in ("up.json", "down.json", "top.json"))
    # the upstream stage re-run under the same config and code, writing other bytes (e.g. a re-fetched source)
    write_table(pd.DataFrame({"x": [1.0, 2.5]}), a)
    write_result(sand, {"n": 1}, "up.json", outputs=[a])
    assert result_staleness(sand, _res(sand, "up.json")) is None
    assert result_staleness(sand, _res(sand, "down.json")) == "its input results/up.json changed after it was read"
    assert "its input results/down.json is not current (its input results/up.json changed" in \
        result_staleness(sand, _res(sand, "top.json"))
    with pytest.raises(StaleInputError, match="up.json changed after it was read"):
        require_current(sand, "down.json")
    # re-run with the original bytes: the upstream result is byte-identical, so the chain is current again
    write_table(pd.DataFrame({"x": [1.0, 2.0]}), a)
    write_result(sand, {"n": 1}, "up.json", outputs=[a])
    assert result_staleness(sand, _res(sand, "top.json")) is None


def test_an_upstream_output_changed_on_disk_makes_every_downstream_result_stale(cfg, tmp_path):
    sand = full_sandbox(cfg, tmp_path)
    a, _ = _chain(sand)
    write_table(pd.DataFrame({"x": [9.0]}), a)                       # replaced, upstream not re-run
    assert "its output" in result_staleness(sand, _res(sand, "up.json"))
    assert "its input results/up.json is not current (its output" in result_staleness(sand, _res(sand, "down.json"))
    assert "its input results/down.json is not current" in result_staleness(sand, _res(sand, "top.json"))
    sand.path("results", "up.json").unlink()
    assert result_staleness(sand, _res(sand, "down.json")) == "its input results/up.json is missing"
    write_result(sand, {"status": "incomplete: no values written"}, "up.json")
    assert "changed after it was read" in result_staleness(sand, _res(sand, "down.json"))


def test_gitignored_outputs_may_be_absent_but_are_never_handed_to_a_stage(cfg, tmp_path):
    """A fresh clone has the committed results but not data/raw or data/interim: the results stay current
    (their numbers were produced by this config and code), but a stage cannot read the absent files."""
    sand = full_sandbox(cfg, tmp_path)
    a, b = _chain(sand)
    a.unlink()                                                       # interim: local only
    assert all(result_staleness(sand, _res(sand, n)) is None for n in ("up.json", "down.json", "top.json"))
    with pytest.raises(StaleInputError, match="not on this machine"):
        require_outputs(sand, "up.json", [a])
    b.unlink()                                                       # derived: committed, so it must be there
    assert "missing its output" in result_staleness(sand, _res(sand, "down.json"))


def test_inputs_must_have_been_read_through_require_current(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path)
    with pytest.raises(ValueError, match="not read through require_current"):
        write_result(sand, {}, "x.json", inputs=["never_read.json"])


def test_root_key_keeps_symlinked_subdirectories(cfg, tmp_path):
    """data/raw/worldclim on another disk (a symlinked sub-directory of a root) used to break write_result."""
    sand = full_sandbox(cfg, tmp_path)
    big = tmp_path / "bigdisk" / "worldclim"
    big.mkdir(parents=True)
    sand.path("raw").mkdir(parents=True)
    sand.path("raw", "worldclim").symlink_to(big, target_is_directory=True)
    f = sand.path("raw", "worldclim", "wc.tif")
    f.write_bytes(b"x")
    assert sand.root_key(f) == "raw:worldclim/wc.tif"
    write_result(sand, {}, "fetch.json", outputs=[f])
    require_outputs(sand, "fetch.json", [f])
    via = tmp_path / "elsewhere"                                     # a path given through a link into a root
    via.symlink_to(sand.path("raw"), target_is_directory=True)
    (sand.path("raw") / "plain.txt").write_text("x")
    assert sand.root_key(via / "plain.txt") == "raw:plain.txt"
    with pytest.raises(ValueError, match="not under any configured path root"):
        sand.root_key(tmp_path / "outside.txt")


# ---------------------------------------------------------------- reproduction table and gate

@pytest.mark.data
def test_reproduction_table_records_its_inputs_and_goes_stale_with_them(cfg, tmp_path):
    from mshi.analysis.repro_checks import repro_checks
    from mshi.run import _gate_status
    sand = full_sandbox(cfg, tmp_path)
    write_result(sand, _committed(cfg, "cosore_annual.json"), "cosore_annual.json")
    require_current(sand, "cosore_annual.json")
    write_result(sand, _committed(cfg, "build_sites.json"), "build_sites.json", inputs=["cosore_annual.json"])
    s = repro_checks(sand)
    assert s["PASS"] == 17 and s["NOT RUN"] == 10
    assert set(_res(sand, "reproduction_check.json")["_inputs"]) == {"cosore_annual.json", "build_sites.json"}
    assert "'NOT RUN': 10" in _gate_status(sand, {}, [])            # not reproduced: the gate stays closed
    # cosore_annual re-run under the same config with other content: build and table are no longer current
    write_result(sand, {**_committed(cfg, "cosore_annual.json"), "n_sites": 65}, "cosore_annual.json")
    assert "build_sites.json is not current" in result_staleness(sand, _res(sand, "reproduction_check.json"))
    assert _gate_status(sand, {}, []).startswith("stale:")


@pytest.mark.data
def test_npp_row_not_run_when_the_modis_table_is_not_on_this_machine(cfg, tmp_path):
    """modis_points.json is current (committed after a networked run) but data/interim is not committed."""
    from mshi.analysis.repro_checks import repro_checks
    from mshi.data import modis
    sand = full_sandbox(cfg, tmp_path)
    for f in ["cosore_annual.json", "build_sites.json"]:
        write_result(sand, _committed(cfg, f), f)
    keys = ["1.0_1.0"]
    out = modis.write_modis_cache(sand, pd.DataFrame({"site_key": keys, "npp": [1.0], "npp_n": [1]}),
                                  modis.modis_cache_key(sand, keys), {"n_failed_reads": 0})
    write_result(sand, {"n_failed_reads": 0}, "modis_points.json", outputs=[out])
    out.unlink()
    assert result_staleness(sand, _res(sand, "modis_points.json")) is None
    s = repro_checks(sand)                                           # NOT RUN is not an error: no raise
    rows = {r["quantity"]: r for r in _res(sand, "reproduction_check.json")["rows"]}
    npp = next(r for q, r in rows.items() if q.startswith("NPP r"))
    assert npp["status"] == "NOT RUN" and "not on this machine" in npp["note"] and s["STALE"] == 0


def test_a_failed_producer_cannot_open_the_gate(cfg, tmp_path, monkeypatch):
    """Third review: a producer that fails in an invocation turns the current build's FAIL rows into NOT RUN;
    NOT RUN rows now close the gate, in this invocation and for later ones."""
    import mshi.run as R
    from mshi.run import Stage

    def build(c):
        raise StaleInputError("results/cosore_annual.json: produced with a different config")

    def repro(c):
        write_result(c, {"summary": {"PASS": 1, "FAIL": 0, "STALE": 0, "NOT RUN": 26}}, "reproduction_check.json")
        return {}
    ran = []
    monkeypatch.setattr(R, "_stages", lambda: [Stage("build_sites", build), Stage("repro_checks", repro),
                                               Stage("phase2", lambda c: ran.append(1) or {}, [])])
    sand = full_sandbox(cfg, tmp_path)
    assert R.run(["build_sites", "repro_checks", "phase2"], sand) == 2 and ran == []
    assert R.run(["phase2"], sand) == 2 and ran == []


def test_smoke_runs_do_not_apply_the_gate(cfg, tmp_path, monkeypatch):
    import mshi.run as R
    from mshi.run import Stage
    ran = []
    monkeypatch.setattr(R, "_stages", lambda: [Stage("build_sites", lambda c: {}), Stage("repro_checks", lambda c: {}),
                                               Stage("phase2", lambda c: ran.append(1) or {}, ["build_sites"])])
    assert R.run(["build_sites", "repro_checks", "phase2"], sandbox(cfg, tmp_path), full=True) == 0 and ran == [1]
    assert R.run(["phase2"], full_sandbox(cfg, tmp_path)) == 2 and ran == [1]    # not a smoke run: gate applies


def test_features_reports_a_refused_modis_table_as_stale(cfg, tmp_path, monkeypatch):
    """StaleModisError is a StaleInputError, so a refused MODIS table gives status 'stale' (exit 2), as in the
    reproduction table, not 'error'."""
    import mshi.run as R
    from mshi.data import modis
    from mshi.run import Stage
    assert issubclass(modis.StaleModisError, StaleInputError)

    def features(c):
        raise modis.StaleModisError("modis_points.parquet was produced with a different libraries")
    monkeypatch.setattr(R, "_stages", lambda: [Stage("features", features)])
    sand = sandbox(cfg, tmp_path)
    assert R.run(["features"], sand) == 2
    assert json.loads(sand.path("results", "run_log.jsonl").read_text().splitlines()[-1])["status"].startswith("stale:")
