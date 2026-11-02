import os, socket, sys, threading, collections, re
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import requests
from mshi.netutil import download, check_reachable, _is_proxy_denial, SourceUnavailableError, DownloadError

def fake_proxy(status_line):
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(50)
    def loop():
        while True:
            c, _ = srv.accept()
            try:
                c.recv(4096)
                c.sendall(f"HTTP/1.1 {status_line}\r\nContent-Length: 0\r\n\r\n".encode())
            finally:
                c.close()
    threading.Thread(target=loop, daemon=True).start()
    return srv.getsockname()[1]

W = Path(SCR) / "work" / "t2"; W.mkdir(parents=True, exist_ok=True)
for st in ("403 Forbidden", "407 Proxy Authentication Required", "502 Bad Gateway", "503 Service Unavailable"):
    port = fake_proxy(st)
    s = requests.Session(); s.trust_env = False; s.proxies = {"https": f"http://127.0.0.1:{port}"}
    sleeps = []
    try:
        download("https://example.invalid/data.csv", W / "x", session=s, sleep=sleeps.append, timeout=5)
    except Exception as e:  # noqa
        print(f"proxy answers CONNECT with {st!r}: {type(e).__name__} kind={getattr(e,'kind','-')} sleeps={sleeps}")
        print("    msg:", str(e)[:230])

# dead proxy port: how often is a plain connection failure classified as a policy block?
dead = free_port()
s = requests.Session(); s.trust_env = False; s.proxies = {"https": f"http://127.0.0.1:{dead}"}
kinds = collections.Counter(); example = {}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
for i in range(N):
    try:
        download("https://example.invalid/srdb-data.csv", W / "y", session=s, retries=1, sleep=lambda x: None, timeout=5)
    except SourceUnavailableError as e:
        kinds[e.kind] += 1
        example.setdefault(e.kind, str(e))
print(f"dead proxy, {N} attempts (retries=1):", dict(kinds))
for k, v in example.items():
    print(f"  example {k}: {v[:400]}")
