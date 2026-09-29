"""Snapshot exports: a single self-contained HTML page (to share or publish) and CSV (for Excel)."""
import csv
import json
from pathlib import Path

from . import DATA_DIR, db
from .runner import build_feed

WEB = Path(__file__).parent / "web" / "index.html"


def export_html(path=None, bare=False):
    """bare=True leaves out <html>/<head> (for publishing as a claude.ai artifact)."""
    con = db.connect()
    feed = build_feed(con)
    con.close()
    feed["live"] = False
    blob = json.dumps(feed, ensure_ascii=False).replace("</", "<\\/")
    html = WEB.read_text(encoding="utf-8").replace("window.TW_FEED = null;", "window.TW_FEED = " + blob + ";", 1)
    if not bare:
        from .server import page_html
        html = page_html(html)
    out = Path(path or DATA_DIR / "tender-watch-snapshot.html")
    out.write_text(html, encoding="utf-8")
    return out


def export_csv(path=None, relevant_only=True):
    con = db.connect()
    q = "SELECT t.*, n.status, n.note FROM tenders t LEFT JOIN notes n ON n.id=t.id"
    q += " WHERE t.relevant=1 AND t.dup_of IS NULL" if relevant_only else ""
    rows = [dict(r) for r in con.execute(q + " ORDER BY t.closing")]
    con.close()
    out = Path(path or DATA_DIR / "tenders.csv")
    cols = ["closing", "title", "org", "region", "source_name", "ref", "published", "score", "categories",
            "status", "note", "url", "doc_url", "first_seen"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel reads Urdu/Unicode
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["categories"] = ", ".join(json.loads(r["categories"] or "[]"))
            w.writerow(r)
    return out
