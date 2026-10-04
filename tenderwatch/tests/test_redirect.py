"""goto() must survive a portal that redirects while its first page is still loading.

Reported from the office PC: a signed-in EPADS account sent www.epads.gov.pk straight on to
vendors.epads.gov.pk/dashboard, and `tw login epads-fed` stopped with a traceback instead of
showing the dashboard. Government portals redirect constantly, so this covers the ways they do
it - and still fails loudly when a site is genuinely unreachable.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import browser as B


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        def send(code, body, headers=()):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        if self.path == "/js-redirect":
            # the shape EPADS used: the page starts loading, then sends the browser elsewhere
            send(200, "<html><body>one moment"
                      "<script>location.href='/dashboard';</script></body></html>")
        elif self.path == "/meta-redirect":
            send(200, "<html><head><meta http-equiv='refresh' content='0;url=/dashboard'>"
                      "</head><body>redirecting</body></html>")
        elif self.path == "/server-redirect":
            send(302, "", [("Location", "/dashboard")])
        elif self.path == "/dashboard":
            send(200, "<html><body><h1>Vendor dashboard</h1>"
                      "<a href='/logout'>Log out</a></body></html>")
        elif self.path == "/plain":
            send(200, "<html><body><h1>Tender list</h1></body></html>")
        else:
            send(404, "<html><body>not found</body></html>")


@pytest.fixture(scope="module")
def site():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def page(site, tmp_path, monkeypatch):
    monkeypatch.setattr(B, "STATE_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(B, "CAPTURE_DIR", tmp_path / "captures")
    st = {"browser_channel": "", "headless": True, "page_delay_seconds": 0,
          "page_timeout_seconds": 20, "max_pages": 10,
          "profile_dir": str(tmp_path / "profile"),
          "browser_executable": os.environ.get("TW_BROWSER_EXECUTABLE", "")}
    br = B.Browser(st)
    pg = br.ctx.new_page()
    yield pg
    br.close()


@pytest.mark.parametrize("path", ["/js-redirect", "/meta-redirect", "/server-redirect"])
def test_redirect_during_load_is_not_an_error(page, site, path):
    """Whichever way the portal redirects, we end up on the dashboard without an exception."""
    B.goto(page, site + path, None)
    assert "/dashboard" in page.url
    assert "Vendor dashboard" in B.body_text(page)


def test_ordinary_page_still_loads(page, site):
    B.goto(page, site + "/plain", None)
    assert "Tender list" in B.body_text(page)


def test_unreachable_site_still_raises(page):
    """A portal that is really down must still be reported, not silently treated as fine."""
    with pytest.raises(Exception):
        B.goto(page, "http://127.0.0.1:9/never-listening", None)
