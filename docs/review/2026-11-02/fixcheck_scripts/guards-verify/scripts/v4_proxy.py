"""Claim 4: _is_proxy_denial matches '403'/'407' anywhere in str(ProxyError) (and the git branch anywhere in stderr).

Only loopback is contacted: a dead proxy port (connection refused) or a local fake proxy that answers CONNECT itself.
Target hosts are *.invalid and never resolved. Sleeps are recorded, not slept.
"""
import os
import socket
import socketserver
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import WORK  # noqa: E402

import requests  # noqa: E402

import mshi.netutil as N  # noqa: E402

W = WORK / "v4"; W.mkdir(parents=True, exist_ok=True)


def dead_port(candidates):
    for p in candidates:
        s = socket.socket()
        try:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
        finally:
            s.close()
    raise SystemExit("no dead port found")


class FakeProxy(socketserver.BaseRequestHandler):
    code = 502

    def handle(self):
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            buf += chunk
        reason = {403: "Forbidden", 502: "Bad Gateway", 503: "Service Unavailable"}[self.code]
        self.request.sendall(f"HTTP/1.1 {self.code} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())


def fake_proxy(code):
    cls = type(f"P{code}", (FakeProxy,), {"code": code})
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), cls)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def dl(label, proxy_port, url):
    s = requests.Session(); s.trust_env = False
    s.proxies = {"https": f"http://127.0.0.1:{proxy_port}", "http": f"http://127.0.0.1:{proxy_port}"}
    sleeps = []
    try:
        N.download(url, W / "f.bin", session=s, sleep=sleeps.append, retries=4, timeout=5)
        print(f"  {label:66s} -> downloaded?!")
    except N.SourceUnavailableError as e:
        print(f"  {label:66s} -> SourceUnavailableError kind={e.kind:12s} sleeps={sleeps} | {str(e)[-120:]}")
    except N.DownloadError as e:
        print(f"  {label:66s} -> DownloadError sleeps={sleeps} | {str(e)[-100:]}")


p403 = dead_port([1403, 14030, 14031, 24030])
p407 = dead_port([1407, 14070, 24070])
pctl = dead_port([1408, 1409, 24081])
print("dead proxy ports:", p403, p407, pctl)
print("download():")
dl(f"dead proxy :{p403}, plain URL", p403, "https://mshi-verify.invalid/data.zip")
dl(f"dead proxy :{p407}, plain URL", p407, "https://mshi-verify.invalid/data.zip")
dl(f"control: dead proxy :{pctl}, plain URL", pctl, "https://mshi-verify.invalid/data.zip")
dl(f"dead proxy :{pctl}, URL path with 'A2020403'", pctl, "https://mshi-verify.invalid/MOD11A2.A2020403.tif")
f502, f403 = fake_proxy(502), fake_proxy(403)
dl("proxy answers CONNECT 502, plain URL", f502, "https://mshi-verify.invalid/data.zip")
dl("proxy answers CONNECT 502, URL path with '407'", f502, "https://mshi-verify.invalid/v407/data.zip")
dl("control: proxy answers CONNECT 403 (a real policy denial)", f403, "https://mshi-verify.invalid/data.zip")

print("check_reachable() with HTTPS_PROXY in the environment:")
for port, label in [(p403, f"dead proxy :{p403}"), (pctl, f"control: dead proxy :{pctl}")]:
    os.environ["HTTPS_PROXY"] = os.environ["https_proxy"] = f"http://127.0.0.1:{port}"
    try:
        N.check_reachable("https://mshi-verify.invalid/", timeout=5, require_ok=False)
    except N.SourceUnavailableError as e:
        print(f"  {label:66s} -> kind={e.kind}")

print("git_checkout_commit() through a proxy answering CONNECT 502:")
for url in ("https://mshi-verify.invalid/bpbond/cosore", "https://mshi-verify.invalid/repo403/cosore"):
    N.GIT_ENV.update({"HTTPS_PROXY": f"http://127.0.0.1:{f502}", "https_proxy": f"http://127.0.0.1:{f502}",
                      "GIT_TERMINAL_PROMPT": "0"})
    dest = W / ("git_" + url.rsplit("/", 2)[-2])
    sleeps = []
    try:
        N.git_checkout_commit(url, "02f32e8e7f9a0f1c26c9dad61c574aef863f1df1", dest, retries=2, sleep=sleeps.append)
    except (N.SourceUnavailableError, N.DownloadError) as e:
        kind = getattr(e, "kind", type(e).__name__)
        print(f"  {url:66s} -> {type(e).__name__} kind={kind} sleeps={sleeps} | {str(e)[-90:]}")
