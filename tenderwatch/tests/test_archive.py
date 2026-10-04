"""Reading an archive page without treating six years of old notices as open tenders.

The KP health department publishes its tenders as a list of links, newest first, going back to
2019 - 416 of them in the page captured on the office PC - and none of them carries a closing
date. Tenders without a closing date are kept for as long as the page keeps listing them, which
this page always will, so every one of them would have counted as open and the first digest
would have emailed a few hundred. A portal can now say how far down to read.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import browser as B

TOTAL = 50


def _page():
    items = "".join(
        f"<li><a href='/news/view/{1300 - i}'>Invitation for bids for the procurement of "
        f"laboratory reagents, batch {1300 - i}</a></li>" for i in range(TOTAL))
    return f"<html><body><h1>Tenders</h1><ul>{items}</ul></body></html>"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = _page()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


@pytest.fixture(scope="module")
def site():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/news/tenders"
    srv.shutdown()


@pytest.fixture
def br(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "STATE_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(B, "CAPTURE_DIR", tmp_path / "captures")
    b = B.Browser({"browser_channel": "", "headless": True, "page_delay_seconds": 0,
                   "page_timeout_seconds": 20, "max_pages": 1,
                   "profile_dir": str(tmp_path / "profile"),
                   "browser_executable": os.environ.get("TW_BROWSER_EXECUTABLE", "")})
    yield b
    b.close()


def test_the_whole_archive_is_read_when_nothing_is_capped(br, site):
    src = {"id": "arch", "name": "Archive portal", "url": site, "strategy": "links"}
    status, recs, err = B.fetch_source(br, src, lambda *a: None)
    assert status == "ok", f"{status}: {err}"
    assert len(recs) == TOTAL


def test_only_the_newest_are_kept_when_a_cap_is_set(br, site):
    src = {"id": "arch", "name": "Archive portal", "url": site, "strategy": "links",
           "max_items": 10}
    status, recs, err = B.fetch_source(br, src, lambda *a: None)
    assert status == "ok", f"{status}: {err}"
    assert len(recs) == 10
    # newest first: the page's own order is kept, so the cap takes the most recent notices
    assert "1300" in recs[0]["title"] and "1291" in recs[-1]["title"]


def test_the_health_department_is_configured_with_a_cap():
    """The portal that needed it must actually have it."""
    from tw.settings import load_sources
    src = load_sources(["health-kp"])[0]
    assert src.get("strategy") == "links"
    assert int(src.get("max_items", 0)) > 0
