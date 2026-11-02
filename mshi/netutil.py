"""Downloads with retries and checksum verification, and pinned shallow git checkouts."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import requests

from .io import sha256_file

log = logging.getLogger("mshi.net")


class SourceUnavailableError(RuntimeError):
    """A pinned source could not be reached (e.g. blocked by the network policy)."""


class ChecksumMismatchError(RuntimeError):
    pass


def download(url: str, dest: Path, sha256: str | None = None, retries: int = 4, timeout: int = 600,
             session: requests.Session | None = None, params: dict | None = None) -> dict:
    """Download ``url`` to ``dest`` (atomic), verify ``sha256`` if given.

    Skips the download if ``dest`` exists and matches ``sha256``. Retries with exponential
    backoff (2, 4, 8, 16 s) on network errors; a proxy/policy denial is reported as
    ``SourceUnavailableError`` immediately, without retrying.
    """
    dest = Path(dest)
    if dest.exists() and sha256 and sha256_file(dest) == sha256:
        return {"path": str(dest), "sha256": sha256, "downloaded": False}
    dest.parent.mkdir(parents=True, exist_ok=True)
    s = session or requests.Session()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with s.get(url, params=params, stream=True, timeout=timeout) as r:
                if r.status_code in (401, 403, 407):
                    raise SourceUnavailableError(f"{url}: HTTP {r.status_code}")
                r.raise_for_status()
                tmp = dest.with_name(dest.name + ".part")
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                os.replace(tmp, dest)
            break
        except SourceUnavailableError:
            raise
        except requests.exceptions.ProxyError as e:      # CONNECT refused by the egress policy
            raise SourceUnavailableError(f"{url}: blocked by proxy ({e})") from e
        except requests.exceptions.RequestException as e:
            last = e
            wait = 2 ** (attempt + 1)
            log.warning("download %s failed (%s); retry in %ss", url, e, wait)
            time.sleep(wait)
    else:
        raise SourceUnavailableError(f"{url}: failed after {retries} attempts ({last})")
    digest = sha256_file(dest)
    if sha256 and digest != sha256:
        raise ChecksumMismatchError(f"{dest}: SHA-256 {digest} != pinned {sha256}")
    return {"path": str(dest), "sha256": digest, "downloaded": True}


def check_reachable(url: str, timeout: int = 30) -> None:
    """Raise SourceUnavailableError if ``url`` cannot be reached (policy denial, DNS, refused)."""
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.close()
    except requests.exceptions.ProxyError as e:
        raise SourceUnavailableError(f"{url}: blocked by proxy ({e})") from e
    except requests.exceptions.ConnectionError as e:
        raise SourceUnavailableError(f"{url}: connection failed ({e})") from e
    if r.status_code in (403, 407):
        raise SourceUnavailableError(f"{url}: HTTP {r.status_code}")


def git_checkout_commit(repo_url: str, commit: str, dest: Path, retries: int = 4) -> dict:
    """Shallow-fetch exactly ``commit`` into ``dest`` (idempotent) and verify HEAD."""
    dest = Path(dest)

    def head() -> str | None:
        if not (dest / ".git").exists():
            return None
        out = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else None

    if head() == commit:
        return {"path": str(dest), "commit": commit, "downloaded": False}
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "remote", "add", "origin", repo_url], check=True)
    last = ""
    for attempt in range(retries):
        r = subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", "origin", commit],
                           capture_output=True, text=True)
        if r.returncode == 0:
            break
        last = r.stderr.strip()
        if "403" in last or "denied" in last.lower():
            raise SourceUnavailableError(f"{repo_url}@{commit}: {last}")
        time.sleep(2 ** (attempt + 1))
    else:
        raise SourceUnavailableError(f"{repo_url}@{commit}: fetch failed ({last})")
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True)
    got = head()
    if got != commit:
        raise ChecksumMismatchError(f"{dest}: HEAD {got} != pinned {commit}")
    return {"path": str(dest), "commit": commit, "downloaded": True}
