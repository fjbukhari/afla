"""Send tenders read on this PC to the website tender portal (jb-scientific.com staff area).

The website reads the public portals itself (PPRA, EPADS, Punjab, KPPRA). This PC sends what only
it can read: portals that need your login, JavaScript portals (EPADS 2.0), UN/donor portals, and the
item lists from tender documents. Sign-ins and passwords never leave this PC; only tender rows are sent.

Needs in settings.yaml:
  website:
    api_url: https://www.jb-scientific.com/catalogue/staff/tenders/api.php
and two saved logins (Windows Credential Manager):
  tw set-login website       staff-area username + password (the /catalogue/staff/ password)
  tw set-login website-key   any text as username + the tender tool's secret_key as password
"""
import base64
import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from datetime import date

from . import db, secrets
from .items import items_for
from .settings import load_settings, load_sources

# Read by the website itself; sending them again would only duplicate work.
WEBSITE_READS = {"ppra-fed", "epads-fed", "ppra-punjab", "kppra"}
CHUNK = 300


# Shared hosting commonly runs a firewall (ModSecurity, Imunify360) that rejects requests whose
# User-Agent says "Python-urllib/3.13", often by closing the connection without answering - which
# arrives here as RemoteDisconnected, exactly what the office PC reported. This says what the
# program is, in the shape of a normal browser's User-Agent, to our own website with our own
# credentials.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TenderWatch/2 (+https://www.jb-scientific.com)"


def _headers(req, user, password, key):
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json, */*")
    if key:
        req.add_header("X-Key", key)
    if user is not None:
        req.add_header("Authorization",
                       "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
    return req


def _post(url, payload, user, password, key):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    _headers(req, user, password, key)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _why(e):
    """Say what actually went wrong, in words that point at a fix.

    The office PC reported five portals as "could not reach the website (URLError)", which names
    the Python class and nothing else - not the host, not the reason, not what to do.
    """
    reason = getattr(e, "reason", None)
    inner = reason if isinstance(reason, BaseException) else e
    text = str(reason or e) or type(e).__name__
    if isinstance(inner, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY" in text.upper():
        return ("the website's security certificate could not be checked (" + text + "). "
                "If the site opens in your browser, this is usually the office network "
                "inspecting traffic, or a missing certificate update on this PC.")
    if isinstance(inner, ssl.SSLError):
        return "the secure connection failed (" + text + ")"
    if isinstance(inner, ConnectionRefusedError) or "refused it" in text or "refused" in text.lower():
        return ("nothing is listening at that address (" + text + "). This is not the website "
                "turning us away - the connection never got that far. The address in "
                "config/settings.yaml is almost always the cause: it must be the website's own "
                "address,\n      https://www.jb-scientific.com/catalogue/staff/tenders/api.php\n"
                "    not localhost, not 127.0.0.1, and with no port number such as :8766 (that is "
                "this PC's own dashboard, not the website).")
    if isinstance(inner, socket.gaierror):
        return ("the website's name could not be looked up (" + text + "). Check the address in "
                "config/settings.yaml - and that it is reachable from this PC.")
    if isinstance(e, http_client_errors()):
        return ("the website closed the connection without answering (" + type(e).__name__ + "). "
                "On shared hosting this is usually its firewall rejecting the request.")
    if isinstance(inner, (TimeoutError, socket.timeout)):
        return "the website did not answer in time (" + text + ")"
    return text + " (" + type(e).__name__ + ")"


def http_client_errors():
    import http.client
    return (http.client.RemoteDisconnected, http.client.BadStatusLine, ConnectionResetError)


def check(log=print):
    """Say whether this PC can reach the website at all, and how.

    Run when a push fails: it tries the address plainly from Python, then through the browser the
    program already drives. If the browser can and Python cannot, the website (or the network) is
    refusing the program rather than the credentials being wrong.
    """
    st = load_settings()
    api = (st.get("website") or {}).get("api_url")
    if not api:
        log("No website address is set. Add this to config/settings.yaml:\n"
            "    website:\n"
            "      api_url: https://www.jb-scientific.com/catalogue/staff/tenders/api.php")
        return 1
    from urllib.parse import urlsplit
    u = urlsplit(api)
    log(f"Website address: {api}")
    log(f"  it will contact: host {u.hostname or '(none)'}, port {u.port or (443 if u.scheme == 'https' else 80)}, "
        f"over {u.scheme or '(no scheme)'}")
    if u.hostname in ("localhost", "127.0.0.1", "::1"):
        log("  THIS IS THIS PC, not the website. The address must be the website's own address.")
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        if os.environ.get(var):
            log(f"  note: {var} is set to {os.environ[var]} - the office network uses a proxy.")
    # On Windows this reads the proxy Internet Options holds, which browsers obey and this
    # program may not. An office network that only lets traffic out through a proxy refuses
    # everything else, which looks exactly like the site being down.
    try:
        sysproxy = urllib.request.getproxies()
    except Exception:
        sysproxy = {}
    log("  Windows proxy : " + (", ".join(f"{k}={v}" for k, v in sysproxy.items()) if sysproxy
                                else "none configured"))
    user, password = secrets.get_login("website")
    _, key = secrets.get_login("website-key")
    log("  saved sign-in : " + ("yes" if user and password else "NO - run: tw set-login website"))
    log("  saved key     : " + ("yes" if key else "NO - run: tw set-login website-key"))

    python_ok = False
    try:
        req = urllib.request.Request(api, method="GET")
        _headers(req, user, password, key)
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read(400).decode("utf-8", "replace")
        log(f"  from this program: reached it (HTTP {r.status}). First reply: {body[:160]!r}")
        python_ok = True
    except urllib.error.HTTPError as e:
        log(f"  from this program: the website answered HTTP {e.code} ({e.reason}).")
        python_ok = e.code in (401, 403)      # it answered, so the connection itself works
    except Exception as e:
        log(f"  from this program: FAILED - {_why(e)}")

    browser_ok = None
    try:
        from .browser import Browser
        br = Browser(st)
        try:
            r = br.ctx.request.get(api, timeout=60000)
            log(f"  from the browser : reached it (HTTP {r.status}).")
            browser_ok = True
        finally:
            br.close()
    except Exception as e:
        log(f"  from the browser : could not try it ({type(e).__name__}: {e})"[:300])

    log("")
    if python_ok:
        log("This PC can reach the website. If a push still fails, it is the sign-in or the key:\n"
            "  tw set-login website       (the staff-area username and password)\n"
            "  tw set-login website-key   (any name, then the secret_key from the website's\n"
            "                              catalogue/staff/tenders/config.php)")
    elif browser_ok:
        log("The browser reaches the website but this program cannot. The connection is fine, so\n"
            "something is refusing the program itself - usually the website's own firewall on\n"
            "shared hosting. Ask the hosting support to allow requests from this office's address\n"
            "to /catalogue/staff/tenders/api.php, and send them the exact message printed above.")
    else:
        log("This PC cannot reach the website at all, by either route. Check that\n"
            "https://www.jb-scientific.com opens in your browser on this PC, and that the address\n"
            "in config/settings.yaml is spelled exactly the same way (including www).")
    return 0 if python_ok else 1


def push(log=print, opener=_post):
    st = load_settings()
    web = st.get("website") or {}
    api = web.get("api_url")
    if not api:
        log("Website not set up (settings.yaml: website: api_url). Nothing sent.")
        return 0
    user, password = secrets.get_login("website")
    _, key = secrets.get_login("website-key")
    if not (user and password and key):
        log("Save the website logins first:  tw set-login website   and   tw set-login website-key")
        return 0
    skip = set(web.get("skip_sources", WEBSITE_READS))
    today = date.today().isoformat()
    con = db.connect()
    items = items_for(con)
    names = {s["id"]: s for s in load_sources(include_disabled=True)}
    sent = 0
    by_src = {}
    for r in con.execute("SELECT * FROM tenders WHERE (closing IS NULL OR closing >= ?) AND has_sm = 1", (today,)):
        if r["source"] in skip:
            continue
        by_src.setdefault(r["source"], []).append({
            "ref": r["ref"] or "", "title": r["title"], "org": r["org"] or "", "location": r["location"] or "",
            "type": r["type"] or "", "published": r["published"] or "", "closing": r["closing"] or "",
            "url": r["url"] or "", "doc_url": r["doc_url"] or "", "items": items.get(r["id"], [])[:300],
        })
    failed = []
    for sid, rows in by_src.items():
        s = names.get(sid, {"id": sid, "name": sid, "region": "", "url": ""})
        meta = {"id": sid, "name": s.get("name", sid), "region": s.get("region", ""), "url": s.get("url", "")}
        done, problem = 0, ""
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            try:
                res = opener(api + ("&" if "?" in api else "?") + "action=import",
                             {"source": meta, "items": chunk, "pages": 0}, user, password, key)
            except urllib.error.HTTPError as e:
                problem = (f"the website refused it (HTTP {e.code}). "
                           + ("Check the website sign-in and key." if e.code in (401, 403)
                              else "That is the website's own error, not this PC's."))
                break
            except Exception as e:
                problem = _why(e)
                break
            if not res.get("ok"):
                problem = f"the website reported: {res.get('error', res)}"
                break
            done += len(chunk)
        sent += done
        # This line used to be printed whatever happened, and counted the rows it MEANT to send,
        # so a failed push said "sent 12 tenders" on one line and "Sent 0 tenders" on the next.
        if problem:
            failed.append(sid)
            log(f"  {sid}: {done} of {len(rows)} sent - {problem}")
        else:
            log(f"  {sid}: sent {done} tenders")
    con.close()
    if failed and not sent:
        log(f"\nNothing was sent: the website could not be reached for any of the "
            f"{len(by_src)} portals.\nRun  tw push --check  to find out why.")
    elif failed:
        log(f"\nSent {sent} tenders, but {len(failed)} portal(s) failed: {', '.join(failed)}.\n"
            f"Run  tw push --check  to find out why.")
    else:
        log(f"Sent {sent} tenders from {len(by_src)} portals to the website.")
    return sent
