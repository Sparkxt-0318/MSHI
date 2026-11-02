import hashlib, socket, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
from mshi.netutil import download, check_reachable, SourceUnavailableError, DownloadError, ChecksumMismatchError
import requests

W = Path(SCR) / "work" / "t1"; W.mkdir(parents=True, exist_ok=True)
for f in W.iterdir():
    f.unlink()
srv, base = serve()
R = Behaviour.routes
good = b"hello world\n" * 100
R["/ok"] = body(200, good)
R["/404"] = body(404)
R["/403"] = body(403)
R["/401"] = body(401)
R["/407"] = body(407)
R["/429"] = body(429)
R["/500"] = body(500)
R["/503"] = body(503)
R["/trunc"] = body(200, good[:100], length=len(good))   # Content-Length larger than body, then close
def loop(h):
    h.send_response(302); h.send_header("Location", "/loop"); h.send_header("Content-Length", "0"); h.end_headers()
R["/loop"] = loop
def reset(h):   # send headers then RST
    h.send_response(200); h.send_header("Content-Length", str(len(good))); h.end_headers()
    h.wfile.write(good[:10]); h.wfile.flush()
    import struct
    h.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    h.close_connection = True
    h.rfile.close()
    h.connection.close()
R["/reset"] = reset
R["/html200"] = body(200, b"<html>Access denied by policy</html>")

def attempt(name, url, dest, **kw):
    sleeps = []
    t = time.time()
    try:
        r = download(url, dest, session=direct_session(), sleep=sleeps.append, timeout=10, **kw)
        out = f"OK {r}"
    except Exception as e:  # noqa
        out = f"{type(e).__name__}(kind={getattr(e, 'kind', '-')}) {str(e)[:160]}"
    left = sorted(p.name for p in dest.parent.iterdir() if p.name.startswith(dest.name))
    print(f"[{name}] hits={Behaviour.hits.get(url.split(base)[-1].split('?')[0]) if base in url else 'n/a'} sleeps={sleeps} files={left}\n    -> {out}")

h = hashlib.sha256(good).hexdigest()
attempt("200 pinned", f"{base}/ok", W / "ok.txt", sha256=h)
attempt("200 pinned again (skip)", f"{base}/ok", W / "ok.txt", sha256=h)
port = free_port()
attempt("connection refused", f"http://127.0.0.1:{port}/x", W / "refused", retries=3)
attempt("checksum mismatch", f"{base}/ok", W / "bad.csv", sha256="0" * 64)
# pre-existing bad file at the pinned path, re-download also mismatching
(W / "pre.csv").write_bytes(b"Record_number,Latitude\n")
attempt("pre-existing bad + mismatch", f"{base}/html200", W / "pre.csv", sha256=h)
print("    pre.csv still at dest:", (W / "pre.csv").exists(), (W / "pre.csv").read_bytes()[:30])
# unpinned + reuse_existing: a 200 HTML page is accepted, then reused forever
attempt("unpinned html 200 (reuse_existing)", f"{base}/html200", W / "wc.zip", reuse_existing=True)
R["/html200"] = body(200, b"PK\x03\x04 real zip would be here")
attempt("unpinned again (server now fixed)", f"{base}/html200", W / "wc.zip", reuse_existing=True)
print("    wc.zip content:", (W / "wc.zip").read_bytes()[:40])

print("--- check_reachable")
for code in ("404", "403", "500"):
    for ro in (True, False):
        try:
            # check_reachable uses requests.get directly (env proxies); 127.0.0.1 is in NO_PROXY
            check_reachable(f"{base}/{code}", require_ok=ro, timeout=5)
            print(f"check_reachable {code} require_ok={ro}: passes")
        except Exception as e:  # noqa
            print(f"check_reachable {code} require_ok={ro}: {type(e).__name__}(kind={getattr(e,'kind','-')})")
try:
    check_reachable(f"http://127.0.0.1:{port}/", timeout=5)
except Exception as e:  # noqa
    print("check_reachable refused:", type(e).__name__, getattr(e, "kind", "-"))
srv.shutdown()
