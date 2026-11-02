"""git_checkout_commit against a local HTTP server that answers 502/503 (transient server errors), no proxy."""
import http.server, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi import netutil as N
W = Path(sys.argv[1]); W.mkdir(parents=True, exist_ok=True)
for code in (502, 503):
    hits = []
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path); self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sleeps = []
    try:
        N.git_checkout_commit(f"http://127.0.0.1:{srv.server_address[1]}/bpbond/cosore", "0" * 40,
                              Path(tempfile.mkdtemp(dir=W)) / "co", sleep=sleeps.append)
        r = "ok"
    except N.SourceUnavailableError as e:
        r = f"SourceUnavailable kind={e.kind}: {str(e)[-90:]}"
    except Exception as e:
        r = f"{type(e).__name__}: {str(e)[-90:]}"
    print(f"HTTP {code}: {r}; sleeps {sleeps}; requests {len(hits)}")
    srv.shutdown()
