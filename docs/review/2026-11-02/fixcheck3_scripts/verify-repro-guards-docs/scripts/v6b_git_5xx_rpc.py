"""Claim 6, second phase: a git smart-HTTP server whose ref advertisement (GET info/refs) works but whose
upload-pack RPC (POST) answers 502 (or always works, as a control). Served by `git http-backend` from a scratch
bare repo. Local only (127.0.0.1 is in no_proxy). Writes only under S/work/git5xx_rpc/."""
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, "/home/user/MSHI")

import mshi.netutil as N  # noqa: E402

SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
W = SCR / "work" / "git5xx_rpc"
shutil.rmtree(W, ignore_errors=True)
W.mkdir(parents=True)
ENV = {"PATH": "/usr/bin:/bin", "HOME": str(W), "GIT_OPTIONAL_LOCKS": "0"}
src = W / "src"
src.mkdir()
run = lambda *a, cwd: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", *a], cwd=cwd, env=ENV,  # noqa: E731
                                     capture_output=True, text=True, check=True).stdout
run("init", "-q", cwd=src)
(src / "f.txt").write_text("x\n")
run("add", "-A", cwd=src)
run("commit", "-q", "-m", "c", cwd=src)
commit = run("rev-parse", "HEAD", cwd=src).strip()
run("clone", "-q", "--bare", str(src), str(W / "repo.git"), cwd=W)
run("config", "uploadpack.allowAnySHA1InWant", "true", cwd=W / "repo.git")
run("config", "http.uploadpack", "true", cwd=W / "repo.git")
REQS = []
MODE = {"post": 502}


class H(http.server.BaseHTTPRequestHandler):
    def _backend(self, body=b""):
        u = urlsplit(self.path)
        env = {**ENV, "GIT_PROJECT_ROOT": str(W), "GIT_HTTP_EXPORT_ALL": "1", "PATH_INFO": u.path,
               "QUERY_STRING": u.query, "REQUEST_METHOD": self.command,
               "CONTENT_TYPE": self.headers.get("Content-Type", ""), "CONTENT_LENGTH": str(len(body))}
        if self.headers.get("Git-Protocol"):
            env["GIT_PROTOCOL"] = self.headers["Git-Protocol"]
        out = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True).stdout
        head, _, payload = out.partition(b"\r\n\r\n")
        status = 200
        hdrs = []
        for line in head.split(b"\r\n"):
            k, _, v = line.decode().partition(":")
            if k.lower() == "status":
                status = int(v.strip().split()[0])
            elif k:
                hdrs.append((k, v.strip()))
        self.send_response(status)
        for k, v in hdrs:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        REQS.append(("GET", self.path.split("?")[0]))
        self._backend()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        REQS.append(("POST", self.path))
        if MODE["post"]:
            self.send_response(MODE["post"])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._backend(body)

    def log_message(self, *a):
        pass


srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/repo.git"

for post in (0, 502):
    MODE["post"] = post
    REQS.clear()
    sleeps = []
    try:
        r = N.git_checkout_commit(url, commit, W / f"dest_{post}", sleep=sleeps.append)
        out = f"ok downloaded={r['downloaded']}"
    except Exception as e:  # noqa: BLE001
        out = f"{type(e).__name__}{'(kind=' + e.kind + ')' if hasattr(e, 'kind') else ''}: {str(e)[-150:]}"
    print(f"POST answers {post or 'normally'}: {out}\n   sleeps {sleeps}; requests {REQS}")
srv.shutdown()
