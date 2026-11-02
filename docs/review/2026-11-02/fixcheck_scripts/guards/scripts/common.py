"""Shared helpers for the guards fix-check (scratch only)."""
import copy, http.server, os, socket, sys, threading, time
sys.dont_write_bytecode = True
os.environ["GIT_OPTIONAL_LOCKS"] = "0"
REPO = "/home/user/MSHI"
if REPO not in sys.path:
    sys.path.insert(0, REPO)
SCR = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/guards"
from pathlib import Path
from mshi.config import Config, load_config


def sandbox(work: Path, edit=None, out_root=True, absolute=False) -> Config:
    """Config whose raw/outputs live in ``work``. absolute=True: out_root None, every output root an
    absolute scratch path (so run() treats it as a full, non-smoke run)."""
    cfg = load_config()
    data = copy.deepcopy(cfg.data)
    work = Path(work)
    data["paths"]["raw"] = str(work / "raw")
    if absolute:
        for k in ("interim", "derived", "results", "figures"):
            data["paths"][k] = str(work / k)
    if edit:
        edit(data)
    return Config(data, source=cfg.source, out_root=(work / "out") if (out_root and not absolute) else None)


class Behaviour(http.server.BaseHTTPRequestHandler):
    """path -> callable(handler) registry; counts hits."""
    routes: dict = {}
    hits: dict = {}
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        key = self.path.split("?")[0]
        Behaviour.hits[key] = Behaviour.hits.get(key, 0) + 1
        fn = Behaviour.routes.get(key)
        if fn is None:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        fn(self)

    def log_message(self, *a):
        pass


def serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Behaviour)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def body(code, data=b"", headers=None, length=None):
    def f(h):
        h.send_response(code)
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(data) if length is None else length))
        h.end_headers()
        if data:
            h.wfile.write(data)
        h.wfile.flush()
        if length is not None and length != len(data):
            h.close_connection = True
            try:
                h.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    return f


def direct_session():
    import requests
    s = requests.Session()
    s.trust_env = False
    return s


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
