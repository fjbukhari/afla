"""Telling "the portal is broken" apart from "you are signed out" and "the layout changed".

Seen on the office PC: www.epads.gov.pk answered with a page whose entire content was
"connection not found". The tool reported that as "no tender list was recognised", which sends
the operator looking for a layout change that has not happened, and `tw login` reported it as
"still looks signed out", which sends them to re-enter a password that was never the problem.

The trap in the other direction is real too: one of the tenders in the live database is a
"COMPREHENSIVE MAINTENANCE CONTRACT OF NEONATE VENTILATORS", so a page must not be called down
merely for containing a word like "maintenance".
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import browser as B

DOWN_PAGES = {
    "/epads": "connection not found",                       # the one actually seen
    "/503": "Service Unavailable",
    "/maint": "The portal is under maintenance. Please try again later.",
    "/dberr": "Database error: cannot connect",
    "/blank": "",
}

# long, ordinary pages that must NOT be called down
LIVE_PAGES = {
    "/tenders": (
        "<h1>Active tenders</h1><table>"
        + "".join(
            f"<tr><td>{i}</td><td>COMPREHENSIVE MAINTENANCE CONTRACT OF NEONATE "
            f"VENTILATORS (SLE-4000) INCLUDING SERVICE AND SPARE PARTS FOR THE "
            f"HOSPITAL, LOT {i}</td><td>14-10-2026</td></tr>" for i in range(1, 12))
        + "</table>"),
    "/short-ok": "<h1>No tenders are open at the moment.</h1>",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in DOWN_PAGES:
            body = f"<html><body>{DOWN_PAGES[self.path]}</body></html>"
        elif self.path in LIVE_PAGES:
            body = f"<html><body>{LIVE_PAGES[self.path]}</body></html>"
        else:
            body = "<html><body>not found</body></html>"
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


@pytest.mark.parametrize("path", list(DOWN_PAGES))
def test_broken_portal_is_recognised(page, site, path):
    B.goto(page, site + path, None)
    assert B.looks_down(page), f"{path} should be recognised as a portal failure"


@pytest.mark.parametrize("path", list(LIVE_PAGES))
def test_working_portal_is_not_called_down(page, site, path):
    B.goto(page, site + path, None)
    assert not B.looks_down(page), f"{path} must not be mistaken for a portal failure"


def test_a_real_tender_mentioning_maintenance_is_safe(page, site):
    """The live database really does contain a maintenance contract; it must survive."""
    B.goto(page, site + "/tenders", None)
    assert "MAINTENANCE CONTRACT" in B.body_text(page)
    assert not B.looks_down(page)


def test_the_reported_page_gives_a_usable_reason(page, site):
    B.goto(page, site + "/epads", None)
    assert "connection not found" in B.looks_down(page).lower()
