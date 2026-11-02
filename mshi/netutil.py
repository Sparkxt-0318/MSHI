"""Downloads with retries and checksum verification, and pinned shallow git checkouts.

Failures are classified so that the run log says what actually happened:

- ``SourceUnavailableError(kind="proxy_denied")``: the egress proxy refused the connection (CONNECT
  answered 403/407: ``Tunnel connection failed: 403`` from requests, ``CONNECT tunnel failed, response
  403`` from git). This is a network-policy block; the run log records the stage as ``blocked``. Only the
  tunnel status is matched, so a dead proxy is ``unreachable`` even if its port or the URL contains 403.
- ``SourceUnavailableError(kind="unreachable")``: DNS or connection failures, or timeouts, still failing
  after the retries. The run log records ``unavailable``.
- ``DownloadError``: the server answered with an error (HTTP 4xx other than 407/408/429 at once;
  408/429/5xx after the retries), a transfer was truncated on every attempt, or the body is not what
  was expected. This is an ordinary error, not a policy block.
- ``ChecksumMismatchError``: the bytes do not match the pinned SHA-256. The file is not left at the
  destination.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path

import requests

from .io import sha256_file

log = logging.getLogger("mshi.net")

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}


class SourceUnavailableError(RuntimeError):
    """A pinned source could not be reached: ``kind`` is ``proxy_denied`` or ``unreachable``."""

    def __init__(self, msg: str, kind: str = "unreachable"):
        super().__init__(msg)
        self.kind = kind


class DownloadError(RuntimeError):
    """The source answered, but not with the expected content (HTTP error, truncated or wrong body)."""


class ChecksumMismatchError(RuntimeError):
    pass


_TUNNEL_DENIED = re.compile(r"Tunnel connection failed: 40[37]\b")              # http.client, via requests
_GIT_TUNNEL_DENIED = re.compile(r"CONNECT tunnel failed, response 40[37]\b")      # curl, via git


def _is_proxy_denial(e: Exception) -> bool:
    return isinstance(e, requests.exceptions.ProxyError) and bool(_TUNNEL_DENIED.search(str(e)))


def _git_proxy_denial(stderr: str) -> bool:
    return bool(_GIT_TUNNEL_DENIED.search(stderr))


def verify_sha256(path: Path, expected: str) -> None:
    """Raise ChecksumMismatchError unless ``path`` exists and has SHA-256 ``expected``."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run the fetch stage first")
    got = sha256_file(path)
    if got != expected:
        raise ChecksumMismatchError(f"{path}: SHA-256 {got} != pinned {expected}; delete it and re-fetch")


def download(url: str, dest: Path, sha256: str | None = None, retries: int = 4, timeout: int = 600,
             session: requests.Session | None = None, params: dict | None = None,
             reuse_existing: bool = False, sleep=time.sleep) -> dict:
    """Download ``url`` to ``dest`` atomically and verify ``sha256`` (if given) before moving it in place.

    Skips the request if ``dest`` exists and matches ``sha256`` (or, for unpinned files, if
    ``reuse_existing``). Retries connection failures, timeouts, truncated transfers and HTTP
    408/429/5xx with backoff 2, 4, 8 s (no sleep after the last attempt).
    """
    dest = Path(dest)
    if dest.exists() and ((sha256 and sha256_file(dest) == sha256) or (reuse_existing and not sha256)):
        return {"path": str(dest), "sha256": sha256 or sha256_file(dest), "downloaded": False}
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    s = session or requests.Session()
    last: str = ""
    for attempt in range(retries):
        retry = False
        try:
            with s.get(url, params=params, stream=True, timeout=timeout) as r:
                if r.status_code == 407:
                    raise SourceUnavailableError(f"{url}: HTTP 407 from proxy", kind="proxy_denied")
                if r.status_code in RETRY_STATUS:
                    last, retry = f"HTTP {r.status_code}", True
                elif r.status_code >= 400:
                    raise DownloadError(f"{url}: HTTP {r.status_code} {r.reason}")
                else:
                    with open(tmp, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
        except (SourceUnavailableError, DownloadError):
            tmp.unlink(missing_ok=True)
            raise
        except requests.exceptions.ProxyError as e:
            tmp.unlink(missing_ok=True)
            if _is_proxy_denial(e):
                raise SourceUnavailableError(f"{url}: blocked by proxy ({e})", kind="proxy_denied") from e
            last, retry = f"proxy connection failed ({e})", True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            tmp.unlink(missing_ok=True)
            last, retry = f"{type(e).__name__}: {e}", True
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ContentDecodingError) as e:
            tmp.unlink(missing_ok=True)
            last, retry = f"truncated transfer ({type(e).__name__})", True
        if not retry:
            break
        if attempt < retries - 1:
            wait = 2 ** (attempt + 1)
            log.warning("download %s failed (%s); retry %d/%d in %ss", url, last, attempt + 1, retries - 1, wait)
            sleep(wait)
    else:
        if last.startswith(("HTTP", "truncated")):
            raise DownloadError(f"{url}: failed after {retries} attempts ({last})")
        raise SourceUnavailableError(f"{url}: unreachable after {retries} attempts ({last})", kind="unreachable")
    digest = sha256_file(tmp)
    if sha256 and digest != sha256:
        tmp.unlink(missing_ok=True)
        raise ChecksumMismatchError(f"{url}: SHA-256 {digest} != pinned {sha256}; nothing written to {dest}")
    os.replace(tmp, dest)
    return {"path": str(dest), "sha256": digest, "downloaded": True}


def check_reachable(url: str, timeout: int = 30, require_ok: bool = True) -> None:
    """Raise SourceUnavailableError if ``url`` cannot be reached; DownloadError if it answers with an
    error status and ``require_ok`` (use ``require_ok=False`` to test only that a host is reachable)."""
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.close()
    except requests.exceptions.ProxyError as e:
        kind = "proxy_denied" if _is_proxy_denial(e) else "unreachable"
        raise SourceUnavailableError(f"{url}: {'blocked by proxy' if kind == 'proxy_denied' else 'proxy connection failed'} ({e})",
                                     kind=kind) from e
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise SourceUnavailableError(f"{url}: connection failed ({e})", kind="unreachable") from e
    if r.status_code == 407:
        raise SourceUnavailableError(f"{url}: HTTP 407 from proxy", kind="proxy_denied")
    if require_ok and r.status_code >= 400:
        raise DownloadError(f"{url}: HTTP {r.status_code} {r.reason}")


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = ["git"] + (["-C", str(cwd)] if cwd else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, env=GIT_ENV)


def verify_git_checkout(dest: Path, commit: str) -> dict:
    """Raise unless ``dest`` is a checkout of ``commit`` with no modified, deleted, untracked or ignored
    files (an ignored file, e.g. a dataset directory matching the repository's .gitignore, would be read)."""
    dest = Path(dest)
    head = _git("rev-parse", "HEAD", cwd=dest) if (dest / ".git").exists() else None
    if head is None or head.returncode != 0:
        raise FileNotFoundError(f"{dest} is not a git checkout; run the fetch stage first")
    got = head.stdout.strip()
    if got != commit:
        raise ChecksumMismatchError(f"{dest}: HEAD {got} != pinned {commit}")
    st = _git("--no-optional-locks", "status", "--porcelain", "--untracked-files=all", "--ignored=matching",
              cwd=dest)
    if st.returncode != 0 or st.stdout.strip():
        changed = st.stdout.strip().splitlines()[:10]
        raise ChecksumMismatchError(f"{dest}: checkout of the pinned commit has local changes {changed}; "
                                    f"delete {dest} and re-fetch")
    tree = _git("rev-parse", "HEAD^{tree}", cwd=dest).stdout.strip()
    return {"commit": got, "tree": tree}


def git_checkout_commit(repo_url: str, commit: str, dest: Path, retries: int = 4, sleep=time.sleep) -> dict:
    """Shallow-fetch exactly ``commit`` into ``dest`` (idempotent); verify HEAD and a clean worktree."""
    dest = Path(dest)
    if (dest / ".git").exists():
        h = _git("rev-parse", "HEAD", cwd=dest)
        if h.returncode == 0 and h.stdout.strip() == commit:
            return {"path": str(dest), **verify_git_checkout(dest, commit), "downloaded": False}
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q", str(dest)], check=True, env=GIT_ENV)
        subprocess.run(["git", "-C", str(dest), "remote", "add", "origin", repo_url], check=True, env=GIT_ENV)
    last = ""
    for attempt in range(retries):
        r = _git("fetch", "-q", "--depth", "1", "origin", commit, cwd=dest)
        if r.returncode == 0:
            break
        last = r.stderr.strip()
        low = last.lower()
        if _git_proxy_denial(last):
            raise SourceUnavailableError(f"{repo_url}@{commit}: blocked by proxy ({last})", kind="proxy_denied")
        if not any(k in low for k in ("could not resolve", "failed to connect", "timed out", "connection",
                                      "early eof", "rpc failed", "unexpected disconnect")):
            raise DownloadError(f"{repo_url}@{commit}: git fetch failed ({last})")
        if attempt < retries - 1:
            sleep(2 ** (attempt + 1))
    else:
        raise SourceUnavailableError(f"{repo_url}@{commit}: unreachable after {retries} attempts ({last})",
                                     kind="unreachable")
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True, env=GIT_ENV)
    return {"path": str(dest), **verify_git_checkout(dest, commit), "downloaded": True}
