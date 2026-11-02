import os, socket, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import requests
from mshi.netutil import download, check_reachable, SourceUnavailableError

def free_port_matching(sub):
    for p in range(1024, 65535):
        if sub in str(p):
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", p)); s.close(); return p
            except OSError:
                s.close()
W = Path(SCR) / "work" / "t2"; W.mkdir(parents=True, exist_ok=True)
for url, sub in [("https://example.invalid/srdb-data.csv", "403"), ("https://example.invalid/srdb-data.csv", "407"),
                 ("https://example.invalid/MOD11A2.A2020407_LST.tif", None)]:
    port = free_port_matching(sub) if sub else free_port()
    s = requests.Session(); s.trust_env = False; s.proxies = {"https": f"http://127.0.0.1:{port}"}
    sleeps = []
    try:
        download(url, W / "z", session=s, sleep=sleeps.append, timeout=5)
    except SourceUnavailableError as e:
        print(f"dead proxy on port {port}, url {url}: kind={e.kind} sleeps={sleeps}")
        print("   ", str(e)[:330])
# check_reachable (uses the environment's proxies): point HTTPS_PROXY at a dead port containing 403
port = free_port_matching("403")
os.environ["HTTPS_PROXY"] = os.environ["https_proxy"] = f"http://127.0.0.1:{port}"
try:
    check_reachable("https://planetarycomputer.microsoft.com/api/stac/v1", timeout=5)
except SourceUnavailableError as e:
    print(f"check_reachable via dead proxy port {port}: kind={e.kind}")
