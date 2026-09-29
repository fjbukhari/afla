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
import urllib.error
import urllib.request
from datetime import date

from . import db, secrets
from .items import items_for
from .settings import load_settings, load_sources

# Read by the website itself; sending them again would only duplicate work.
WEBSITE_READS = {"ppra-fed", "epads-fed", "ppra-punjab", "kppra"}
CHUNK = 300


def _post(url, payload, user, password, key):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Key", key)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


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
    for sid, rows in by_src.items():
        s = names.get(sid, {"id": sid, "name": sid, "region": "", "url": ""})
        meta = {"id": sid, "name": s.get("name", sid), "region": s.get("region", ""), "url": s.get("url", "")}
        for i in range(0, len(rows), CHUNK):
            try:
                res = opener(api + ("&" if "?" in api else "?") + "action=import",
                             {"source": meta, "items": rows[i:i + CHUNK], "pages": 0}, user, password, key)
            except urllib.error.HTTPError as e:
                log(f"  {sid}: website refused ({e.code}). Check the website logins.")
                break
            except Exception as e:
                log(f"  {sid}: could not reach the website ({type(e).__name__}).")
                break
            if not res.get("ok"):
                log(f"  {sid}: website error: {res.get('error', res)}")
                break
            sent += len(rows[i:i + CHUNK])
        log(f"  {sid}: sent {len(rows)} tenders")
    con.close()
    log(f"Sent {sent} tenders from {len(by_src)} portals to the website.")
    return sent
