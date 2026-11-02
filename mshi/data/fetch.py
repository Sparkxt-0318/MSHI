"""Fetch stages for the pinned public sources: SRDB, COSORE, Natural Earth, licences.

Each stage writes ``results/<stage>.json`` with what was fetched and its checksum.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..io import sha256_file, write_result
from ..netutil import download, git_checkout_commit

log = logging.getLogger("mshi.fetch")


def srdb_csv_path(cfg: Config):
    s = cfg["sources"]["srdb"]
    return cfg.path("raw", "srdb", s["commit"][:8], s["file"])


def cosore_repo_path(cfg: Config):
    return cfg.path("raw", "cosore", cfg["sources"]["cosore"]["commit"][:8])


def cosore_read_paths(cfg: Config) -> list[str]:
    """Paths of the COSORE checkout that the pipeline reads (the dataset directories and the licence); the
    worktree check covers these (mshi.netutil.verify_git_checkout)."""
    c = cfg["sources"]["cosore"]
    return [c["datasets_dir"], c["licence_file"]]


def naturalearth_path(cfg: Config, file: str):
    ne = cfg["sources"]["naturalearth"]
    return cfg.path("raw", "naturalearth", ne["version"], file)


def fetch_srdb(cfg: Config) -> dict:
    s = cfg["sources"]["srdb"]
    url = s["url"].format(commit=s["commit"], file=s["file"])
    info = download(url, srdb_csv_path(cfg), sha256=s["sha256"])
    # the LICENSE is commit-pinned and hash-pinned too, so a re-run with both files on disk needs no network
    lic = download(s["licence_url"].format(commit=s["commit"]), srdb_csv_path(cfg).with_name("LICENSE"),
                   sha256=s["licence_sha256"])
    out = {"source": "srdb", "repo": s["repo"], "commit": s["commit"], "url": url,
           "sha256": info["sha256"], "sha256_pinned": s["sha256"], "licence_sha256": lic["sha256"]}
    write_result(cfg, out, "fetch_srdb.json")
    return out


def fetch_cosore(cfg: Config) -> dict:
    c = cfg["sources"]["cosore"]
    info = git_checkout_commit(c["repo_url"], c["commit"], cosore_repo_path(cfg),   # HEAD + clean worktree
                               pathspec=cosore_read_paths(cfg))
    ds_root = cosore_repo_path(cfg) / c["datasets_dir"]
    datasets = sorted(d.name for d in ds_root.iterdir() if d.is_dir())
    lic = cosore_repo_path(cfg) / c["licence_file"]
    out = {"source": "cosore", "version": c["version"], "commit": info["commit"], "tree": info["tree"],
           "repo_url": c["repo_url"], "n_dataset_dirs": len(datasets),
           "n_test_dirs": sum(d.startswith(cfg["cosore_annual"]["skip_prefix"]) for d in datasets),
           "licence_sha256": sha256_file(lic) if lic.exists() else None}
    write_result(cfg, out, "fetch_cosore.json")
    return out


def fetch_naturalearth(cfg: Config) -> dict:
    ne = cfg["sources"]["naturalearth"]
    files = {}
    for f, digest in ne["files"].items():
        info = download(ne["url"].format(commit=ne["commit"], file=f), naturalearth_path(cfg, f), sha256=digest)
        files[f] = info["sha256"]
    out = {"source": "naturalearth", "version": ne["version"], "commit": ne["commit"], "files_sha256": files}
    write_result(cfg, out, "fetch_naturalearth.json")
    return out
