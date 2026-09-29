"""End-to-end: drive a real headless browser against fake portals served locally."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
FX = Path(__file__).parent / "fixtures"


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _html(self, body, code=200, headers=()):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path
        if p.startswith("/portal"):
            return self._html((FX / ("portal_p2.html" if "page=2" in p else "portal_p1.html")).read_text())
        if p == "/spa":
            return self._html((FX / "spa.html").read_text())
        if p == "/api/menu":
            return self._json([{"title": "Home"}, {"title": "Active tenders"}])
        if p.startswith("/api/tenders"):
            page = 2 if "page=2" in p else 1
            items = ([{"tenderNo": "S-1", "tenderTitle": "Life Saving Medical Supplies", "procuringAgencyName": "Civil Hospital Karachi", "closingDate": "2026-10-13T00:00:00"},
                      {"tenderNo": "S-2", "tenderTitle": "Road repair works", "procuringAgencyName": "Works Dept", "closingDate": "2026-10-14T00:00:00"}]
                     if page == 1 else
                     [{"tenderNo": "S-3", "tenderTitle": "Hematology analyzer reagents", "procuringAgencyName": "CB Lab Karachi", "closingDate": "2026-10-20T00:00:00"}])
            return self._json({"data": {"items": items, "hasNext": page == 1}})
        if p == "/login":
            return self._html('<form method="post" action="/login"><input name="username"><input type="password" name="password"><button>Sign in</button></form>')
        if p == "/members":
            if "sid=ok" in (self.headers.get("Cookie") or ""):
                return self._html('<a href="/logout">Log out</a>' + (FX / "portal_p2.html").read_text())
            return self._html("<p>Please sign in</p>")
        self._html("nope", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode()
        if self.path == "/login" and "username=me" in body and "password=secret" in body:
            return self._html("ok", 302, [("Location", "/members"), ("Set-Cookie", "sid=ok; Path=/")])
        self._html("bad", 403)


@pytest.fixture(scope="module")
def site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def browser(tmp_path, monkeypatch):
    import tw.browser as B
    monkeypatch.setattr(B, "STATE_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(B, "CAPTURE_DIR", tmp_path / "captures")
    st = {"browser_channel": "", "headless": True, "page_delay_seconds": 0, "page_timeout_seconds": 20,
          "max_pages": 10, "profile_dir": str(tmp_path / "profile"),
          "browser_executable": os.environ.get("TW_BROWSER_EXECUTABLE", "")}
    b = B.Browser(st)
    yield b
    b.close()


def test_table_portal_with_pagination(site, browser):
    from tw.browser import fetch_source
    status, recs, err = fetch_source(browser, {"id": "t", "url": site + "/portal"}, print)
    assert status == "ok", err
    assert [r["ref"] for r in recs] == ["TS-100", "TS-101", "TS-102", "TS-103"]
    assert recs[3]["closing"] == "2026-11-01"


def test_javascript_portal_json(site, browser):
    from tw.browser import fetch_source
    status, recs, err = fetch_source(browser, {"id": "spa", "url": site + "/spa"}, print)
    assert status == "ok", err
    assert [r["ref"] for r in recs] == ["S-1", "S-2", "S-3"]
    assert recs[0]["org"] == "Civil Hospital Karachi"


def test_login_portal(site, browser, monkeypatch):
    import tw.browser as B
    from tw.browser import fetch_source
    src = {"id": "lp", "url": site + "/members", "login": True, "login_url": site + "/login",
           "logged_in_check": "Log ?out"}
    monkeypatch.setattr(B.secrets, "get_login", lambda sid: (None, None))
    status, recs, err = fetch_source(browser, src, print)
    assert status == "needs_login"
    monkeypatch.setattr(B.secrets, "get_login", lambda sid: ("me", "secret"))
    status, recs, err = fetch_source(browser, src, print)
    assert status == "ok", err
    assert recs[0]["title"] == "Next Generation Sequencing Consumables"
