"""Run the portals, store results, and build the feed the dashboard reads."""
import json
from datetime import date, timedelta

from . import DATA_DIR, db
from .dedup import find_duplicates
from .places import city_of, institute_of
from .score import Scorer
from .settings import load_settings, load_sources


def run(only=None, headless=None, log=print):
    st = load_settings()
    sources = load_sources(only)
    scorer = Scorer()
    con = db.connect()
    from .browser import Browser, fetch_source
    br = Browser(st, headless=headless)
    summary = []
    try:
        for src in sources:
            started = db.now()
            log(f"{src['name']} ...")
            status, recs, err = fetch_source(br, src, log)
            new = rel = 0
            if recs:
                new, rel = db.upsert(con, src, recs, scorer)
            db.log_run(con, src["id"], started, status == "ok", status, len(recs), new, rel, err)
            line = f"  -> {status}: {len(recs)} rows, {rel} relevant, {new} new" + (f" | {err}" if err else "")
            log(line)
            summary.append((src["id"], status, len(recs), rel, new, err))
        mark_duplicates(con)
        if st.get("read_documents", True):
            from .items import fetch_items
            try:
                fetch_items(br, con, log)
            except Exception as e:
                log(f"Reading tender documents failed: {e}")
    finally:
        br.close()
    write_feed(con)
    if (st.get("website") or {}).get("api_url"):
        from .push import push
        push(log)
    return summary


def mark_duplicates(con):
    rows = [dict(r) for r in con.execute(
        "SELECT id, source, title, ref, org, closing, published, doc_url FROM tenders WHERE relevant=1")]
    dup = find_duplicates(rows)
    con.execute("UPDATE tenders SET dup_of=NULL")
    con.executemany("UPDATE tenders SET dup_of=? WHERE id=?", [(v, k) for k, v in dup.items()])
    con.commit()


def build_feed(con, include_irrelevant=False):
    st = load_settings()
    cutoff = (date.today() - timedelta(days=st["keep_closed_days"])).isoformat()
    # tenders without a closing date (e.g. PDF notices on institution pages) drop out once the page stops listing them
    q = "SELECT * FROM tenders WHERE ((closing IS NULL AND last_seen >= ?) OR closing >= ?)"
    if not include_irrelevant:
        q += " AND has_sm=1 AND score >= 1"
    tenders = []
    for r in con.execute(q + " ORDER BY closing", (cutoff, cutoff)):
        t = dict(r)
        for k in ("categories", "matched", "excluded"):
            t[k] = json.loads(t[k] or "[]")
        t.pop("raw", None)
        t["city"] = city_of(t.get("location"), t.get("org"), t.get("title"))
        t["institute"] = institute_of(t.get("org"))
        tenders.append(t)
    from .items import items_for
    items = items_for(con)
    for t in tenders:
        t["items"] = items.get(t["id"], [])
    notes = {r["id"]: dict(r) for r in con.execute("SELECT * FROM notes")}
    sources = []
    for s in load_sources(include_disabled=True):
        last = con.execute("SELECT * FROM runs WHERE source=? ORDER BY started DESC LIMIT 1", (s["id"],)).fetchone()
        last_ok = con.execute("SELECT finished FROM runs WHERE source=? AND ok=1 ORDER BY started DESC LIMIT 1",
                              (s["id"],)).fetchone()
        sources.append({
            "id": s["id"], "name": s["name"], "region": s.get("region", ""), "url": s["url"],
            "login": bool(s.get("login")), "enabled": s.get("enabled", True) is not False, "group": s.get("group", ""),
            "status": last["status"] if last else "never", "error": last["error"] if last else "",
            "rows": last["rows"] if last else 0, "relevant": last["relevant"] if last else 0,
            "last_run": last["finished"] if last else "", "last_ok": last_ok["finished"] if last_ok else "",
        })
    scorer = Scorer()
    return {
        "generated": db.now(), "threshold": scorer.threshold,
        "categories": {k: bool(v.get("core")) for k, v in scorer.R["categories"].items()},
        "team": st.get("team", []), "sources": sources, "tenders": tenders, "notes": notes,
        "catalogue_url": st.get("catalogue_url", ""),
    }


PUBLIC_FIELDS = ("id", "title", "institute", "city", "region", "source_name", "ref", "closing", "published",
                 "url", "doc_url", "categories", "core", "score", "items")


def build_public_feed(con):
    """Open relevant tenders for the catalogue's Match tab: no team notes or statuses."""
    feed = build_feed(con)
    today = date.today().isoformat()
    tenders = [{k: t.get(k) for k in PUBLIC_FIELDS} for t in feed["tenders"]
               if t["relevant"] and not t["dup_of"] and (not t["closing"] or t["closing"] >= today)]
    return {"generated": feed["generated"], "source": "JBS Tender Watch", "tenders": tenders}


def write_feed(con):
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "feed.json").write_text(json.dumps(build_feed(con), ensure_ascii=False), encoding="utf-8")
    pub = json.dumps(build_public_feed(con), ensure_ascii=False)
    (DATA_DIR / "tender-feed.json").write_text(pub, encoding="utf-8")
    # Optional copy next to the website's catalogue page (e.g. a synced website folder)
    dest = load_settings().get("catalogue_feed_path")
    if dest:
        from pathlib import Path
        try:
            Path(dest).write_text(pub, encoding="utf-8")
        except OSError as e:
            print(f"Could not write tender feed to {dest}: {e}")
