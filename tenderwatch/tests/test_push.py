"""Sending this PC's tenders to the website, and saying clearly when that fails.

Reported from the office PC, with every portal:

    pu: could not reach the website (RemoteDisconnected).
    pu: sent 1 tenders
    ...
    Sent 0 tenders from 5 portals to the website.

Three faults in four lines: the success line was printed whatever happened and counted the rows
it MEANT to send, so it contradicted both the error above it and the total below it; and
"(URLError)" names a Python class rather than saying what went wrong or what to do about it.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tw import push as P

ROWS = {"ungm": 3, "undp": 2}


class Handler(BaseHTTPRequestHandler):
    mode = "ok"
    seen = []

    def log_message(self, *a):
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        Handler.seen.append(dict(self.headers))
        if Handler.mode == "drop":                 # the office PC's case: closed, no answer
            self.close_connection = True
            self.wfile.close()
            return
        if Handler.mode == "401":
            self.send_response(401); self.end_headers(); return
        if Handler.mode == "apierror":
            out = {"ok": False, "error": "bad key"}
        else:
            out = {"ok": True, "imported": len(self._body().get("items", []))}
        b = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    do_GET = do_POST


@pytest.fixture(scope="module")
def site():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api.php"
    srv.shutdown()


@pytest.fixture
def wired(site, tmp_path, monkeypatch):
    """A database with a few relevant tenders, and the website settings filled in."""
    from tw import db
    real_connect = db.connect                      # keep it: the patch below replaces db.connect
    con = real_connect(tmp_path / "t.db")
    for sid, n in ROWS.items():
        for i in range(n):
            con.execute(
                "INSERT INTO tenders (id, source, title, closing, has_sm, relevant) VALUES (?,?,?,?,1,1)",
                (f"{sid}-{i}", sid, f"Supply of laboratory reagents, lot {i}", "2099-01-01"))
    con.commit()
    con.close()
    monkeypatch.setattr(P.db, "connect", lambda *a, **k: real_connect(tmp_path / "t.db"))
    monkeypatch.setattr(P, "load_settings", lambda: {"website": {"api_url": site}})
    monkeypatch.setattr(P, "load_sources", lambda **k: [{"id": s, "name": s.upper()} for s in ROWS])
    monkeypatch.setattr(P.secrets, "get_login", lambda which: ("user", "pass"))
    monkeypatch.setattr(P, "items_for", lambda con: {})
    Handler.seen = []
    return site


def run(mode):
    Handler.mode = mode
    out = []
    sent = P.push(log=out.append)
    return sent, "\n".join(out)


def test_a_good_push_reports_what_it_sent(wired):
    sent, text = run("ok")
    assert sent == sum(ROWS.values())
    assert f"Sent {sent} tenders" in text
    assert "could not reach" not in text


def test_a_dropped_connection_is_not_reported_as_a_success(wired):
    """The reported fault: "could not reach" and "sent 1 tenders" on consecutive lines."""
    sent, text = run("drop")
    assert sent == 0
    assert "sent 3 tenders" not in text and "sent 2 tenders" not in text
    for sid in ROWS:
        assert f"{sid}: 0 of {ROWS[sid]} sent" in text, text


def test_the_reason_is_in_plain_words_not_a_class_name(wired):
    sent, text = run("drop")
    assert "closed the connection without answering" in text, text
    assert "firewall" in text, text
    assert "tw push --check" in text, text


def test_nothing_sent_is_said_once_and_clearly(wired):
    sent, text = run("drop")
    assert "Nothing was sent" in text
    assert "Sent 0 tenders from" not in text      # the old contradictory summary


def test_nothing_listening_points_at_the_address(wired, monkeypatch):
    """WinError 10061: the office PC dialled an address where nothing answered."""
    monkeypatch.setattr(P, "load_settings",
                        lambda: {"website": {"api_url": "http://127.0.0.1:9/api.php"}})
    out = []
    P.push(log=out.append)
    text = "\n".join(out)
    assert "nothing is listening at that address" in text, text
    assert "settings.yaml" in text and ":8766" in text, text


def test_a_refused_sign_in_says_so(wired):
    sent, text = run("401")
    assert sent == 0
    assert "HTTP 401" in text and "sign-in" in text


def test_an_error_from_the_website_is_passed_on(wired):
    sent, text = run("apierror")
    assert sent == 0
    assert "bad key" in text


def test_we_do_not_identify_ourselves_as_python_urllib(wired):
    """Shared hosting firewalls reject that outright, usually by dropping the connection."""
    run("ok")
    uas = [h.get("User-Agent", "") for h in Handler.seen]
    assert uas and all("Python-urllib" not in ua for ua in uas), uas
    assert all("TenderWatch" in ua for ua in uas), uas


class FakeBrowser:
    """check() also tries the real browser; these tests are about the Python side, and starting
    Playwright here would leave its event loop running for the browser tests that follow."""
    def __init__(self, st):
        self.ctx = self
        self.request = self

    def get(self, url, timeout=0):
        return type("R", (), {"status": 200})()

    def close(self):
        pass


def test_check_says_it_reached_the_website(wired, monkeypatch):
    import tw.browser
    monkeypatch.setattr(tw.browser, "Browser", FakeBrowser)
    Handler.mode = "ok"
    out = []
    rc = P.check(log=out.append)
    text = "\n".join(out)
    assert rc == 0
    assert "reached it (HTTP 200)" in text
    assert "saved sign-in : yes" in text


def test_check_blames_the_website_not_the_settings_when_both_routes_are_refused(wired, monkeypatch):
    """The office PC's case: the address was right, and the tool told them to check the address.

    Both routes refused instantly at a correct address means the website is refusing, and that
    is what has to be said - the settings file is never even reached.
    """
    import tw.browser

    class Refusing(FakeBrowser):
        def get(self, url, timeout=0):
            raise RuntimeError("connect ECONNREFUSED 74.50.90.186:443")

    monkeypatch.setattr(tw.browser, "Browser", Refusing)
    monkeypatch.setattr(P, "load_settings",
                        lambda: {"website": {"api_url": "http://127.0.0.1:9/api.php"}})
    out = []
    P.check(log=out.append)
    text = "\n".join(out)
    assert "That is the website refusing the connection" in text, text
    assert "on your phone with" in text, text
    assert "spelled exactly the same way" not in text, text


def test_check_explains_a_refusal(wired, monkeypatch):
    import tw.browser
    monkeypatch.setattr(tw.browser, "Browser", FakeBrowser)
    Handler.mode = "drop"
    out = []
    rc = P.check(log=out.append)
    text = "\n".join(out)
    assert rc == 1
    assert "FAILED" in text and "closed the connection" in text
    # the browser reached it while the program could not: that is the verdict to report
    assert "firewall" in text, text
