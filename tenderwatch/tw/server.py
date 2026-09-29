"""Local dashboard server: http://localhost:8765 (only this PC unless started with --lan)."""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import DATA_DIR, ROOT, db
from .runner import build_feed

WEB = Path(__file__).parent / "web" / "index.html"
LOG = DATA_DIR / "last-run.log"
_run = {"proc": None}
_lock = threading.Lock()


def start_run(ids=None):
    with _lock:
        p = _run["proc"]
        if p and p.poll() is None:
            return False
        DATA_DIR.mkdir(exist_ok=True)
        f = open(LOG, "w", encoding="utf-8")
        _run["proc"] = subprocess.Popen([sys.executable, "-m", "tw", "run", *(ids or [])], cwd=str(ROOT),
                                        stdout=f, stderr=subprocess.STDOUT)
        return True


SKELETON = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>')


def page_html(inner=None):
    """index.html is written without <html>/<head> so the same file can be published as an artifact."""
    return SKELETON + (inner if inner is not None else WEB.read_text(encoding="utf-8")) + "</body></html>"


class Handler(BaseHTTPRequestHandler):
    team_key = ""

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, page_html().encode(), "text/html")
        if path == "/api/feed":
            con = db.connect()
            try:
                feed = build_feed(con)
            finally:
                con.close()
            feed["live"] = True
            feed["needs_key"] = bool(self.team_key)
            return self._send(200, feed)
        if path == "/api/run":
            p = _run["proc"]
            log = LOG.read_text(encoding="utf-8", errors="replace")[-6000:] if LOG.exists() else ""
            return self._send(200, {"running": bool(p and p.poll() is None), "log": log})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.team_key and self.headers.get("X-Team-Key") != self.team_key:
            return self._send(403, {"error": "Team key missing or wrong"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        path = self.path.split("?")[0]
        if path == "/api/note":
            con = db.connect()
            try:
                for tid in data.get("ids") or [data.get("id")]:
                    if tid:
                        db.set_note(con, tid, data.get("status"), data.get("note"), data.get("by", ""))
            finally:
                con.close()
            return self._send(200, {"ok": True})
        if path == "/api/run":
            return self._send(200, {"started": start_run(data.get("sources"))})
        self._send(404, {"error": "not found"})


def serve(port=8765, lan=False, team_key=""):
    Handler.team_key = team_key
    host = "0.0.0.0" if lan else "127.0.0.1"
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Tender Watch dashboard: http://localhost:{port}   (Ctrl+C to stop)")
    if lan:
        print("Shared on your office network. Colleagues use http://<this-PC-name>:%d" % port)
    httpd.serve_forever()
