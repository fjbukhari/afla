"""Being refused by a firewall, and not looking like a robot in the first place.

On the office PC's first real run, all five EPADS portals answered with the same page:

    Web Page Blocked!  The page cannot be displayed. ...
    URL: vendors.epads.gov.pk/dashboard   Client IP: 202.47.32.50   Attack ID: 20000051

while signing in to that very address by hand, from the same PC and the same IP address,
worked. The difference is in the request headers, so two things are tested here: that we send
the User-Agent of an ordinary browser window rather than announcing a headless one, and that a
firewall page is reported as a firewall page - not as "no tender list was recognised" (which
sends the operator looking for a layout change) and not as "signed out" (which sends them to
re-enter a password that was never the problem).
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import browser as B

# The real page, as captured from the portal.
BLOCK_PAGE = ("<html><body>The URL you requested has been blocked<br>block"
              "<h1>Web Page Blocked!</h1><p>The page cannot be displayed. Please contact the "
              "administrator for additional information.</p><p>URL: vendors.epads.gov.pk/dashboard "
              "Client IP: 202.47.32.50 Attack ID: 20000051 Message ID: 018798515278</p></body></html>")

CLOUDFLARE = ("<html><body><h1>Access denied</h1><p>You do not have access to this site. "
              "Cloudflare Ray ID: a4573cfbea1ac4c3</p></body></html>")

# A portal saying the sign-in expired - NOT a firewall, and it must not be called one.
EXPIRED = "<html><body><h1>Access Denied</h1><p>Your session has expired. Please log in.</p></body></html>"

# A real tender list that happens to use the words. It must survive.
TENDERS = ("<html><body><h1>Active tenders</h1><table>"
           "<tr><th>Ref</th><th>Tender</th><th>Closing</th></tr>"
           "<tr><td>B-1</td><td>Supply of blocked-drain clearing equipment for the hospital</td>"
           "<td>01-12-2026</td></tr>"
           "<tr><td>B-2</td><td>Access control and security policy audit for the blood bank</td>"
           "<td>05-12-2026</td></tr></table></body></html>")

SEEN_HEADERS = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN_HEADERS[self.path] = dict(self.headers)
        body = {"/blocked": BLOCK_PAGE, "/cloudflare": CLOUDFLARE,
                "/expired": EXPIRED, "/tenders": TENDERS}.get(self.path, "<html><body>ok</body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


@pytest.fixture(scope="module")
def site():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _settings(tmp_path):
    return {"browser_channel": "", "headless": True, "page_delay_seconds": 0,
            "page_timeout_seconds": 20, "max_pages": 2,
            "profile_dir": str(tmp_path / "profile"),
            "browser_executable": os.environ.get("TW_BROWSER_EXECUTABLE", "")}


@pytest.fixture
def br(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "STATE_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(B, "CAPTURE_DIR", tmp_path / "captures")
    b = B.Browser(_settings(tmp_path))
    yield b
    b.close()


@pytest.fixture
def page(br):
    return br.ctx.new_page()


def test_we_do_not_announce_a_headless_browser(br, site, page):
    """The header the portal's firewall actually sees."""
    B.goto(page, site + "/tenders", None)
    ua = SEEN_HEADERS["/tenders"].get("User-Agent", "")
    assert ua, "no User-Agent was sent at all"
    assert "Headless" not in ua, ua
    assert "Chrome" in ua, ua


def test_the_browser_still_identifies_itself_honestly(br, site, page):
    """Nothing is invented: it is the same browser and the same version, just not headless."""
    B.goto(page, site + "/tenders", None)
    ua = SEEN_HEADERS["/tenders"].get("User-Agent", "")
    real = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome").replace("Headless", "")
    assert ua == real


@pytest.mark.parametrize("path", ["/blocked", "/cloudflare"])
def test_a_firewall_page_is_recognised(page, site, path):
    B.goto(page, site + path, None)
    assert B.looks_blocked(page), f"{path} should be recognised as a firewall refusal"


def test_the_epads_page_gives_a_usable_reason(page, site):
    B.goto(page, site + "/blocked")
    reason = B.looks_blocked(page)
    assert "Attack ID: 20000051" in reason
    assert "vendors.epads.gov.pk" in reason


def test_an_expired_sign_in_is_not_called_a_firewall(page, site):
    """"Access denied" on its own is how portals say the session lapsed."""
    B.goto(page, site + "/expired", None)
    assert not B.looks_blocked(page)


def test_a_real_tender_list_is_never_called_blocked(page, site):
    B.goto(page, site + "/tenders", None)
    assert "blocked-drain" in B.body_text(page)
    assert not B.looks_blocked(page)
    assert not B.looks_down(page)


def test_a_blocked_portal_is_reported_as_blocked_not_empty(br, site):
    """The whole point: the operator is told it is a firewall, not a layout change."""
    src = {"id": "wafportal", "name": "Firewalled portal", "url": site + "/blocked"}
    status, recs, err = B.fetch_source(br, src, lambda *a: None)
    assert status == "error"
    assert "firewall" in err.lower()
    assert "Attack ID: 20000051" in err
    assert "no tender list was recognised" not in err
