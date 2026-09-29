"""Daily email of new relevant tenders (optional; needs the email section in settings.yaml)."""
import html
import smtplib
from email.message import EmailMessage

from . import DATA_DIR, db, secrets
from .settings import load_settings


def build(con, since):
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM tenders WHERE relevant=1 AND dup_of IS NULL AND first_seen > ? "
        "AND (closing IS NULL OR closing >= date('now')) ORDER BY core DESC, closing", (since,))]
    if not rows:
        return rows, ""
    items = "".join(
        f"<tr><td style='white-space:nowrap'>{html.escape(r['closing'] or '?')}</td>"
        f"<td>{'<b>CORE</b> ' if r['core'] else ''}<a href='{html.escape(r['url'] or '')}'>{html.escape(r['title'])}</a>"
        f"<br><small>{html.escape(r['org'] or '')} · {html.escape(r['source_name'])}</small></td></tr>"
        for r in rows)
    body = (f"<p>{len(rows)} new relevant tender(s) since {html.escape(since)}.</p>"
            f"<table cellpadding='6' style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
            f"<tr><th align='left'>Closing</th><th align='left'>Tender</th></tr>{items}</table>"
            "<p style='color:#777;font-size:12px'>Confirm dates and documents on the official portal before bidding.</p>")
    return rows, body


def send(dry_run=False):
    st = load_settings()
    con = db.connect()
    since = db.meta_get(con, "last_digest", "1970-01-01 00:00:00")
    rows, body = build(con, since)
    if not rows:
        print("No new relevant tenders since", since)
        return
    out = DATA_DIR / "digest.html"
    out.write_text(body, encoding="utf-8")
    em = st.get("email") or {}
    if dry_run or not em.get("smtp_host"):
        print(f"{len(rows)} new tenders. Digest written to {out}" + ("" if dry_run else " (email not configured)"))
        return
    user, pw = secrets.get_login("email")
    msg = EmailMessage()
    msg["Subject"] = f"Tender Watch: {len(rows)} new relevant tender(s)"
    msg["From"] = em.get("from") or user
    msg["To"] = ", ".join(em.get("to") or [])
    msg.set_content("Open this email in an HTML-capable mail program.")
    msg.add_alternative(body, subtype="html")
    with smtplib.SMTP(em["smtp_host"], int(em.get("smtp_port", 587)), timeout=60) as s:
        s.starttls()
        if user and pw:
            s.login(user, pw)
        s.send_message(msg)
    db.meta_set(con, "last_digest", db.now())
    print(f"Emailed {len(rows)} tenders to {msg['To']}")
