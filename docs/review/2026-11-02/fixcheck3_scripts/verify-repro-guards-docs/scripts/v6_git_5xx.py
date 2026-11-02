"""Claim 6: how does git_checkout_commit classify an HTTP 5xx from the git server, and a proxy that answers
CONNECT with 502, compared with download() through the same proxy? Local servers only (127.0.0.1, which is in
no_proxy for the direct case; the fake proxy never connects anywhere). Writes only under S/work/git5xx/."""
import http.server
import shutil
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")

import requests  # noqa: E402

import mshi.netutil as N  # noqa: E402

SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
W = SCR / "work" / "git5xx"
shutil.rmtree(W, ignore_errors=True)
W.mkdir(parents=True)
COMMIT = "02f32e8e7f9a0f1c26c9dad61c574aef863f1df1"
REQS = []


def make_handler(code):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            REQS.append(("GET", self.path))
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            REQS.append(("POST", self.path))
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_CONNECT(self):
            REQS.append(("CONNECT", self.path))
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass
    return H


def serve(code):
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), make_handler(code))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def git_case(label, url, code, proxy=None):
    REQS.clear()
    srv = serve(code)
    port = srv.server_address[1]
    env_backup = dict(N.GIT_ENV)
    if proxy:
        for k in ("HTTPS_PROXY", "https_proxy"):
            N.GIT_ENV[k] = f"http://127.0.0.1:{port}"
    sleeps = []
    dest = W / label.replace(" ", "_")
    try:
        N.git_checkout_commit(url.format(port=port), COMMIT, dest, sleep=sleeps.append)
        out = "returned (unexpected)"
    except Exception as e:  # noqa: BLE001
        kind = getattr(e, "kind", "")
        out = f"{type(e).__name__}{'(kind=' + kind + ')' if kind else ''}: {str(e)[-120:]}"
    finally:
        N.GIT_ENV.clear()
        N.GIT_ENV.update(env_backup)
        srv.shutdown()
    print(f"git  {label}: {out}\n     sleeps {sleeps}, server saw {len(REQS)} request(s) {REQS[:3]}")


git_case("server 502", "http://127.0.0.1:{port}/bpbond/cosore", 502)
git_case("server 503", "http://127.0.0.1:{port}/bpbond/cosore", 503)
git_case("server 404 (control)", "http://127.0.0.1:{port}/bpbond/cosore", 404)
git_case("proxy CONNECT 502", "https://git.example.invalid/bpbond/cosore", 502, proxy=True)
git_case("proxy CONNECT 403 (control)", "https://git.example.invalid/bpbond/cosore", 403, proxy=True)

# requests through the same kind of proxy
for code in (502, 403):
    REQS.clear()
    srv = serve(code)
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"https": f"http://127.0.0.1:{srv.server_address[1]}"}
    sleeps = []
    try:
        N.download("https://git.example.invalid/srdb-data.csv", W / f"dl_{code}.csv", session=s, sleep=sleeps.append)
        out = "returned (unexpected)"
    except Exception as e:  # noqa: BLE001
        kind = getattr(e, "kind", "")
        out = f"{type(e).__name__}{'(kind=' + kind + ')' if kind else ''}: {str(e)[-100:]}"
    srv.shutdown()
    print(f"requests proxy CONNECT {code}: {out}\n     sleeps {sleeps}, proxy saw {len(REQS)} request(s)")

# run-log status mapping (run.py:164-171): SourceUnavailableError -> blocked/unavailable (exit 2); others -> error (exit 1)
