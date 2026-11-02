"""netutil failure classes through local fake CONNECT proxies and dead local proxy ports (127.0.0.1 only).
Targets are *.invalid hosts reached only through the local fake proxy; no outside host is contacted."""
import os, socket, socketserver, sys, threading, tempfile, json
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
import requests
from mshi import netutil as N

W = Path(sys.argv[1]); W.mkdir(parents=True, exist_ok=True)

class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
def make_proxy(code, reason, port=0):
    class H(socketserver.StreamRequestHandler):
        def handle(self):
            self.server.seen.append(self.rfile.readline().decode(errors="replace").strip())
            while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                pass
            self.wfile.write(f"HTTP/1.1 {code} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
    srv = Proxy(("127.0.0.1", port), H); srv.seen = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

def free(port):
    s = socket.socket(); s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) != 0
    finally:
        s.close()

def dl(proxy_url, url):
    sleeps = []
    s = requests.Session(); s.trust_env = False; s.proxies = {"https": proxy_url, "http": proxy_url}
    try:
        N.download(url, W / "dl.bin", session=s, sleep=sleeps.append, timeout=5)
        return "ok", sleeps, ""
    except N.SourceUnavailableError as e:
        return f"SourceUnavailable kind={e.kind}", sleeps, str(e)
    except Exception as e:
        return type(e).__name__, sleeps, str(e)

def reach(proxy_url, url):
    old = {k: os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy")}
    os.environ.update(HTTPS_PROXY=proxy_url, https_proxy=proxy_url, NO_PROXY="", no_proxy="")
    try:
        N.check_reachable(url, timeout=5); return "ok", ""
    except N.SourceUnavailableError as e:
        return f"SourceUnavailable kind={e.kind}", str(e)
    except Exception as e:
        return type(e).__name__, str(e)
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

print("== requests (download / check_reachable)")
p403 = make_proxy(403, "Forbidden"); p407 = make_proxy(407, "Proxy Authentication Required"); p502 = make_proxy(502, "Bad Gateway")
for label, srv in [("CONNECT 403", p403), ("CONNECT 407", p407), ("CONNECT 502", p502)]:
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    for target in ["https://modis.invalid/x.tif", "https://modis.invalid/MOD11A2.A2020403_407.tif"]:
        k, sl, msg = dl(url, target)
        print(f"  download via {label} ({target}): {k}, sleeps {sl}")
    print(f"    message: {msg[-170:]}")
    k, msg = reach(url, "https://stac.invalid/api")
    print(f"  check_reachable via {label}: {k}")
for port in [1403, 1407, 4030, 4070, 14031, 40307]:
    if not free(port):
        print(f"  port {port} busy, skipped"); continue
    url = f"http://127.0.0.1:{port}"
    k, sl, msg = dl(url, "https://modis.invalid/x.tif")
    k2, _ = reach(url, "https://stac.invalid/api")
    print(f"  dead proxy :{port}: download {k}, sleeps {sl}; check_reachable {k2}")
print(f"    message: {msg[-170:]}")
# a live proxy on a port that contains 403, answering 502 to CONNECT
for port in [14030, 24030, 34030]:
    if free(port):
        srv = make_proxy(502, "Bad Gateway", port)
        k, sl, msg = dl(f"http://127.0.0.1:{port}", "https://modis.invalid/x.tif")
        print(f"  proxy :{port} answering 502: {k}, sleeps {sl}"); break
# the exact message recorded in results/run_log.jsonl by this container's proxy (a6c00bc run)
rec = [json.loads(l) for l in open("/home/user/MSHI/results/run_log.jsonl")]
real = [r["status"] for r in rec if r.get("git_commit", "").startswith("a6c00bc") and r["status"].startswith("blocked")]
print("  regex on the container proxy messages in run_log:", [bool(N._TUNNEL_DENIED.search(s)) for s in real])

print("== git (git_checkout_commit) through the same fake proxies")
def git_case(proxy_url, repo_url):
    env = dict(N.GIT_ENV)
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        env[k] = proxy_url
    env.update(NO_PROXY="", no_proxy="", GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.proxy", GIT_CONFIG_VALUE_0=proxy_url)
    N.GIT_ENV.clear(); N.GIT_ENV.update(env)
    dest = Path(tempfile.mkdtemp(dir=W)) / "co"
    sleeps = []
    try:
        N.git_checkout_commit(repo_url, "0" * 40, dest, sleep=sleeps.append)
        return "ok", sleeps, ""
    except N.SourceUnavailableError as e:
        return f"SourceUnavailable kind={e.kind}", sleeps, str(e)
    except Exception as e:
        return type(e).__name__, sleeps, str(e)
orig_env = dict(N.GIT_ENV)
for label, srv in [("CONNECT 403", p403), ("CONNECT 407", p407), ("CONNECT 502", p502)]:
    for repo in ["https://git.invalid/bpbond/cosore", "https://git.invalid/repo403"]:
        k, sl, msg = git_case(f"http://127.0.0.1:{srv.server_address[1]}", repo)
        tail = msg.split("(", 1)[-1][-110:]
        print(f"  git via {label} {repo}: {k}, sleeps {sl}; stderr tail: {tail!r}")
for port in [1403, 1407]:
    if free(port):
        k, sl, msg = git_case(f"http://127.0.0.1:{port}", "https://git.invalid/bpbond/cosore")
        print(f"  git via dead proxy :{port}: {k}, sleeps {sl}; tail {msg[-120:]!r}")
N.GIT_ENV.clear(); N.GIT_ENV.update(orig_env)
print("proxy request lines seen:", sorted(set(p403.seen + p407.seen + p502.seen))[:6])
