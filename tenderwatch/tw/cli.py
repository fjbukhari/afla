"""Command line: python -m tw <command>. Run `python -m tw -h` for the list."""
import argparse
import getpass
import sys

from . import db


def cmd_run(a):
    from .runner import run
    summary = run(a.sources or None, headless=False if a.show else None)
    bad = [s for s in summary if s[1] != "ok"]
    print(f"\nDone: {len(summary) - len(bad)} of {len(summary)} portals read.")
    for sid, status, *_rest, err in bad:
        print(f"  {sid}: {status} {('- ' + err) if err else ''}")


def cmd_test(a):
    """Read one portal and print what was found, without saving anything."""
    from .browser import Browser, fetch_source
    from .score import Scorer
    from .settings import load_settings, load_sources
    src = load_sources([a.source])[0]
    br = Browser(load_settings(), headless=not a.show)
    try:
        status, recs, err = fetch_source(br, src, print)
    finally:
        br.close()
    sc = Scorer()
    print(f"\nStatus: {status}  rows: {len(recs)}  {err}")
    for r in recs[: a.n]:
        s = sc.score(r["title"], r.get("org", ""), r.get("type", ""))
        print(f"- [{'REL' if s['relevant'] else '   '} {s['score']:>2}] {r['title'][:90]}")
        print(f"      org={r.get('org', '')[:50]!r} ref={r.get('ref', '')!r} closing={r.get('closing')} "
              f"published={r.get('published')}\n      url={r.get('url', '')[:100]}")


def cmd_login(a):
    """Open a visible browser at the portal so you can sign in yourself (handles CAPTCHA / OTP)."""
    from . import secrets
    from .browser import Browser, fill_login, goto, is_logged_in
    from .settings import load_settings, load_sources
    src = load_sources([a.source])[0]
    br = Browser(load_settings(), headless=False)
    try:
        page = br.ctx.new_page()
        goto(page, src.get("login_url") or src["url"], br.st)
        user, pw = secrets.get_login(src["id"])
        if user and pw:
            fill_login(page, src, user, pw)
            print("Your saved username/password were filled in.")
        input(f"\nSign in to {src['name']} in the browser window.\n"
              "When you can see your account (or the tender list), come back here and press Enter... ")
        goto(page, src["url"], br.st)
        ok = is_logged_in(page, src)
        print({True: "Signed in: OK.", False: "Still looks signed out. Check the browser, then try again.",
               None: "Saved. (This portal has no sign-in check configured.)"}[ok])
    finally:
        br.close()


def cmd_set_login(a):
    from . import secrets
    user = input(f"Username for {a.source}: ").strip()
    pw = getpass.getpass("Password (not shown): ")
    secrets.set_login(a.source, user, pw)
    print("Saved in Windows Credential Manager (service 'tenderwatch'). It is never written to any file.")


def cmd_forget_login(a):
    from . import secrets
    secrets.delete_login(a.source)
    print("Removed.")


def cmd_serve(a):
    from .server import serve
    from .settings import load_settings
    st = load_settings()
    serve(a.port or st["dashboard_port"], a.lan, st.get("team_key", "") if a.lan else "")


def cmd_export(a):
    from .export import export_csv, export_html
    print("Written:", export_csv(a.path) if a.csv else export_html(a.path, a.bare))


def cmd_digest(a):
    from .digest import send
    send(a.dry_run)


def cmd_rescore(a):
    from .runner import mark_duplicates, write_feed
    from .score import Scorer
    con = db.connect()
    db.rescore(con, Scorer())
    mark_duplicates(con)
    write_feed(con)
    print("Rescored with the current config/rules.yaml.")


def cmd_import_old(a):
    """Bring tenders (and team notes) over from the first Tender Watch's data/tenders.json."""
    import json
    from .runner import mark_duplicates, write_feed
    from .score import Scorer
    old = json.load(open(a.path, encoding="utf-8"))
    con = db.connect()
    names = {s["id"]: s for s in old.get("sources", [])}
    by_src = {}
    for t in old.get("tenders", []):
        by_src.setdefault(t["source"], []).append(t)
    sc = Scorer()
    for sid, recs in by_src.items():
        s = names.get(sid, {})
        started = db.now()
        new, rel = db.upsert(con, {"id": sid, "name": s.get("name", recs[0].get("source_name", sid)),
                        "region": s.get("region", recs[0].get("region", "")), "url": s.get("url", "")}, recs, sc)
        db.log_run(con, sid, started, True, "ok", len(recs), new, rel, "Imported from the first Tender Watch")
        for t in recs:  # keep the original first-seen dates
            con.execute("UPDATE tenders SET first_seen=? WHERE id=?", (t.get("first_seen"), db.tender_id(sid, t)))
    for tid, n in (old.get("notes") or {}).items():
        db.set_note(con, tid, n.get("status"), n.get("note"), n.get("by", ""))
    con.commit()
    mark_duplicates(con)
    write_feed(con)
    print(f"Imported {sum(map(len, by_src.values()))} tenders from {len(by_src)} portals.")


def cmd_sources(a):
    from .runner import build_feed
    con = db.connect()
    for s in build_feed(con)["sources"]:
        flag = "login" if s["login"] else "public"
        on = "" if s["enabled"] else " (disabled)"
        print(f"{s['id']:<18} {flag:<6} {s['status']:<11} {s['relevant']:>4} relevant  last ok: {s['last_ok'] or '-'}"
              f"  {s['name']}{on}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="tw", description="Tender Watch: collect and review tenders.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run", help="read portals and update the database")
    s.add_argument("sources", nargs="*", help="source ids (default: all enabled)")
    s.add_argument("--show", action="store_true", help="show the browser window while it works")
    s.set_defaults(f=cmd_run)
    s = sub.add_parser("test", help="read one portal and print results without saving")
    s.add_argument("source")
    s.add_argument("--show", action="store_true")
    s.add_argument("-n", type=int, default=15)
    s.set_defaults(f=cmd_test)
    for name, fn, h in (("login", cmd_login, "sign in to a portal by hand in a visible browser"),
                        ("set-login", cmd_set_login, "save a portal username/password in Windows Credential Manager"),
                        ("forget-login", cmd_forget_login, "remove a saved username/password")):
        s = sub.add_parser(name, help=h)
        s.add_argument("source")
        s.set_defaults(f=fn)
    s = sub.add_parser("serve", help="open the dashboard at http://localhost:8765")
    s.add_argument("--port", type=int)
    s.add_argument("--lan", action="store_true", help="also allow colleagues on the office network")
    s.set_defaults(f=cmd_serve)
    s = sub.add_parser("export", help="write a shareable HTML snapshot (or --csv for Excel)")
    s.add_argument("path", nargs="?")
    s.add_argument("--csv", action="store_true")
    s.add_argument("--bare", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(f=cmd_export)
    s = sub.add_parser("digest", help="email new relevant tenders (see settings.yaml)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(f=cmd_digest)
    sub.add_parser("rescore", help="re-apply config/rules.yaml to stored tenders").set_defaults(f=cmd_rescore)
    s = sub.add_parser("import-old", help="import data/tenders.json from the first Tender Watch")
    s.add_argument("path")
    s.set_defaults(f=cmd_import_old)
    sub.add_parser("sources", help="list portals and their last result").set_defaults(f=cmd_sources)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    sys.exit(main())
