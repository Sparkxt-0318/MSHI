"""Load ``configs/v3.yaml`` and resolve repository paths.

The configuration is the single place for versions, paths, thresholds and seeds.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "v3.yaml"


class Config:
    """Thin wrapper around the YAML dict with path helpers.

    ``cfg["sources"]["srdb"]`` gives raw values; ``cfg.path("raw", "srdb")`` resolves
    a path under one of the ``paths`` roots. ``cfg.out_root`` lets a smoke run redirect
    every derived/interim/results path into a sandbox without touching real outputs.
    """

    def __init__(self, data: dict, source: Path | None = None, out_root: Path | None = None):
        self._d = data
        self.source = source
        self.repo_root = REPO_ROOT
        self.out_root = Path(out_root) if out_root else None

    def __getitem__(self, key: str) -> Any:
        return self._d[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._d.get(key, default)

    @property
    def data(self) -> dict:
        return copy.deepcopy(self._d)

    def path(self, root: str, *parts: str) -> Path:
        """Resolve ``paths.<root>`` (relative to the repo, or to ``out_root`` for outputs)."""
        rel = Path(self._d["paths"][root])
        if self.out_root is not None and root in ("interim", "derived", "results", "figures"):
            base = self.out_root / rel
        else:
            base = self.repo_root / rel
        return base.joinpath(*parts)

    def repo_path(self, rel: str | Path) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.repo_root / p

    def sha256(self) -> str:
        """Hash of the canonical JSON of the whole config (recorded with results)."""
        return canonical_sha256(self._d)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def load_config(path: str | Path | None = None, out_root: str | Path | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.is_absolute():
        p = REPO_ROOT / p
    with open(p, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data.get("version") != 3:
        raise ValueError(f"{p}: expected version 3 config, got {data.get('version')!r}")
    return Config(data, source=p, out_root=Path(out_root) if out_root else None)
