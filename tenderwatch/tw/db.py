"""SQLite storage: tenders, team notes/status, and a log of each portal run."""
import hashlib
import json
import sqlite3
from datetime import datetime

from . import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenders (
  id TEXT PRIMARY KEY, source TEXT, source_name TEXT, region TEXT, ref TEXT, title TEXT,
  org TEXT, location TEXT, type TEXT, published TEXT, closing TEXT, closing_raw TEXT,
  url TEXT, doc_url TEXT, raw TEXT, first_seen TEXT, last_seen TEXT,
  score INTEGER, has_sm INTEGER, relevant INTEGER, core INTEGER, categories TEXT, matched TEXT,
  excluded TEXT, dup_of TEXT
);
CREATE INDEX IF NOT EXISTS ix_t_closing ON tenders(closing);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY, status TEXT, note TEXT, by TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  source TEXT, started TEXT, finished TEXT, ok INTEGER, status TEXT, rows INTEGER,
  new INTEGER, relevant INTEGER, error TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path=None):
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(str(path or DATA_DIR / "tenders.db"), timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def tender_id(source, rec):
    """Stable id: portal reference if there is one, otherwise title + buyer + closing date."""
    ref = (rec.get("ref") or "").strip().lower()
    key = ref if len(ref) >= 4 else "|".join(
        (rec.get("title") or "").lower().split() + ["|", (rec.get("org") or "").lower(), rec.get("closing") or ""])
    return f"{source}:{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def upsert(con, src, recs, scorer):
    """Insert/refresh tenders from one portal run. Returns (new_count, relevant_count)."""
    ts = now()
    new = rel = 0
    for r in recs:
        tid = tender_id(src["id"], r)
        s = scorer.score(r["title"], r.get("org", ""), r.get("type", ""))
        rel += s["relevant"]
        # A link to the portal's home page is useless; keep it only if nothing better exists
        url = r.get("url") or src.get("url", "")
        row = dict(
            id=tid, source=src["id"], source_name=src["name"], region=src.get("region", ""),
            ref=r.get("ref", ""), title=r["title"], org=r.get("org", "") or src.get("default_org", ""),
            location=r.get("location", ""), type=r.get("type", ""), published=r.get("published"),
            closing=r.get("closing"), closing_raw=r.get("closing_raw", ""), url=url,
            doc_url=r.get("doc_url", ""), raw=json.dumps(r.get("raw") or {}, ensure_ascii=False)[:4000],
            last_seen=ts, score=s["score"], has_sm=int(s["has_sm"]), relevant=int(s["relevant"]),
            core=int(s["core"]), categories=json.dumps(s["categories"]), matched=json.dumps(s["matched"]),
            excluded=json.dumps(s["excluded"]),
        )
        old = con.execute("SELECT first_seen FROM tenders WHERE id=?", (tid,)).fetchone()
        if old:
            sets = ", ".join(f"{k}=:{k}" for k in row if k != "id")
            con.execute(f"UPDATE tenders SET {sets} WHERE id=:id", row)
        else:
            new += 1
            row["first_seen"] = ts
            cols = ", ".join(row)
            con.execute(f"INSERT INTO tenders ({cols}) VALUES ({', '.join(':' + k for k in row)})", row)
    con.commit()
    return new, rel


def rescore(con, scorer):
    for t in con.execute("SELECT id, title, org, type FROM tenders").fetchall():
        s = scorer.score(t["title"], t["org"], t["type"])
        con.execute(
            "UPDATE tenders SET score=?, has_sm=?, relevant=?, core=?, categories=?, matched=?, excluded=? WHERE id=?",
            (s["score"], int(s["has_sm"]), int(s["relevant"]), int(s["core"]), json.dumps(s["categories"]),
             json.dumps(s["matched"]), json.dumps(s["excluded"]), t["id"]))
    con.commit()


def set_note(con, tid, status=None, note=None, by=""):
    cur = con.execute("SELECT status, note FROM notes WHERE id=?", (tid,)).fetchone()
    st = status if status is not None else (cur["status"] if cur else "")
    nt = note if note is not None else (cur["note"] if cur else "")
    con.execute("INSERT OR REPLACE INTO notes (id, status, note, by, updated) VALUES (?,?,?,?,?)",
                (tid, st, nt, by, now()))
    con.commit()


def log_run(con, source, started, ok, status, rows=0, new=0, relevant=0, error=""):
    con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
                (source, started, now(), int(ok), status, rows, new, relevant, error[:1000]))
    con.commit()


def meta_get(con, k, default=None):
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(con, k, v):
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))
    con.commit()
