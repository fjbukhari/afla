"""Deciding whether a portal considers us signed in.

Every logged_in_check in sources.yaml was written without access to the real portal, because
they block cloud servers, so each one is a guess until it meets the live site. Reported from the
office PC: EPADS was signed in and showing its vendor dashboard, and `tw login epads-fed` still
said "Still looks signed out".

These cases cover the ways portals actually present a signed-in session - including the one that
broke it, where the sign-out control is an icon inside a collapsed account menu and never appears
in the page's visible text.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import browser as B

EPADS_CHECK = r"Log ?out|Sign ?out|My (Bids|Profile|Dashboard)"

PAGES = {
    # what the old check was written for
    "/plain-logout": ("<html><body><h1>Dashboard</h1><a href='/x'>Log out</a></body></html>", True),
    # the EPADS shape: sign-out is an icon in a menu that is collapsed, so no visible text
    "/collapsed-menu": (
        "<html><body><h1>Vendor dashboard</h1>"
        "<ul class='menu' style='display:none'><li><a href='/account/logout'>"
        "<i class='icon-power'></i></a></li></ul>"
        "<p>Active tenders: 14</p></body></html>", True),
    # sign-out written as one word, lower case
    "/one-word": ("<html><body><a href='/u'>logout</a>Welcome</body></html>", True),
    # no sign-out control, but the page clearly names the account
    "/welcome": ("<html><body><h1>Portal</h1><p>Signed in as F. Bukhari</p></body></html>", True),
    # a genuinely signed-out public landing page
    "/public": (
        "<html><body><h1>e-Procurement</h1><a href='/login'>Sign in</a>"
        "<p>Register as a vendor</p></body></html>", False),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body, _ = PAGES.get(self.path, ("<html><body>not found</body></html>", False))
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


@pytest.mark.parametrize("path,expected", [(p, v[1]) for p, v in PAGES.items()])
def test_signed_in_detection(page, site, path, expected):
    src = {"id": "test", "url": site, "logged_in_check": EPADS_CHECK}
    B.goto(page, site + path, None)
    assert B.is_logged_in(page, src) is expected, (
        path + " -> " + repr(B.signed_in_signals(page, src)))


def test_collapsed_menu_was_the_reported_failure(page, site):
    """The exact case that failed on the office PC: signed in, but nothing in the visible text."""
    src = {"id": "test", "url": site, "logged_in_check": EPADS_CHECK}
    B.goto(page, site + "/collapsed-menu", None)
    assert "Log out" not in B.body_text(page)          # the old check had nothing to find
    sig = B.signed_in_signals(page, src)
    assert sig["href_hit"], "the sign-out link should be found among the page's links"
    assert B.is_logged_in(page, src) is True


def test_signals_report_what_was_seen(page, site):
    """When it cannot decide, `tw login` shows these to the operator, so they must be filled in."""
    src = {"id": "test", "url": site, "logged_in_check": EPADS_CHECK}
    B.goto(page, site + "/public", None)
    sig = B.signed_in_signals(page, src)
    assert sig["url"].endswith("/public")
    assert not sig["text_hit"] and not sig["href_hit"] and not sig["configured_hit"]


def test_capture_returns_its_path(page, site, tmp_path):
    B.goto(page, site + "/public", None)
    path = B.capture(page, "test-login")
    assert path is not None and path.exists()
