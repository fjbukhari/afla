"""Reading a portal whose HTTPS certificate does not check out.

Several Pakistani government sites serve an expired or self-signed certificate. On the office
PC's first real run, ppms.pprasindh.gov.pk answered ERR_CERT_AUTHORITY_INVALID and the browser
refused to open it at all, so the portal could never be read.

A source can opt in with `insecure: true`. The safety rule that comes with it is tested here:
a portal cannot be both insecure and signed-in to, because a certificate that cannot be verified
means the connection cannot be proven to be with the real portal, and no password of yours should
travel over it.
"""
import os
import ssl
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import browser as B


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = ("<html><body><table>"
                "<tr><th>Ref</th><th>Tender</th><th>Closing</th></tr>"
                "<tr><td>S-1</td><td>Supply of laboratory reagents</td><td>01-12-2026</td></tr>"
                "<tr><td>S-2</td><td>Supply of ELISA kits</td><td>05-12-2026</td></tr>"
                "</table></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture(scope="module")
def https_site():
    """A real HTTPS server with a self-signed certificate - the situation on the live portal."""
    d = tempfile.mkdtemp()
    cert, key = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
    rc = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key, "-out", cert,
         "-days", "2", "-nodes", "-subj", "/CN=localhost"],
        capture_output=True)
    if rc.returncode != 0:
        pytest.skip("openssl not available to make a self-signed certificate")
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"https://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


@pytest.fixture
def br(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "STATE_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(B, "CAPTURE_DIR", tmp_path / "captures")
    st = {"browser_channel": "", "headless": True, "page_delay_seconds": 0,
          "page_timeout_seconds": 20, "max_pages": 2,
          "profile_dir": str(tmp_path / "profile"),
          "browser_executable": os.environ.get("TW_BROWSER_EXECUTABLE", "")}
    b = B.Browser(st)
    yield b
    b.close()


def test_a_bad_certificate_blocks_the_portal_by_default(br, https_site):
    """Without the flag the browser refuses, which is what happened on the live portal."""
    src = {"id": "badcert", "name": "Bad certificate portal", "url": https_site}
    status, recs, err = B.fetch_source(br, src, lambda *a: None)
    assert status == "error"
    assert "CERT" in err.upper() or "certificate" in err.lower()


def test_the_flag_lets_it_be_read(br, https_site):
    src = {"id": "badcert", "name": "Bad certificate portal", "url": https_site, "insecure": True}
    status, recs, err = B.fetch_source(br, src, lambda *a: None)
    assert status == "ok", f"{status}: {err}"
    titles = " ".join(str(r.get("title", "")) for r in recs)
    assert "reagents" in titles.lower()


def test_insecure_and_sign_in_are_refused_together(br, https_site):
    """A password must never go over a connection whose certificate cannot be verified."""
    src = {"id": "badcert", "name": "Bad certificate portal", "url": https_site,
           "insecure": True, "login": True}
    status, recs, err = B.fetch_source(br, src, lambda *a: None)
    assert status == "error"
    assert "cannot be combined" in err


def test_the_throwaway_browser_carries_no_sign_ins(br, https_site):
    """It must not reuse the profile that holds your portal sessions."""
    src = {"id": "badcert", "name": "Bad certificate portal", "url": https_site, "insecure": True}
    extra_browser, extra_ctx, page = B._insecure_page(br, src, lambda *a: None)
    try:
        assert extra_ctx is not br.ctx
        assert extra_ctx.cookies() == []
    finally:
        extra_ctx.close()
        extra_browser.close()
