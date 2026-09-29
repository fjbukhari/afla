"""Drives a real browser (Edge on Windows) so that JavaScript portals and logged-in portals
work the same way as public ones. Cookies from your sign-ins are kept in data/ on this PC only."""
import json
import re
import time
from datetime import datetime

from . import DATA_DIR
from . import secrets
from .extract import extract_json, extract_tables

STATE_FILE = DATA_DIR / "session-cookies.json"
CAPTURE_DIR = DATA_DIR / "captures"

USER_SELECTORS = ("input[type=email]", "input[autocomplete=username]", "input[name*=user i]", "input[id*=user i]",
                  "input[name*=email i]", "input[id*=email i]", "input[name*=login i]", "input[type=text]")
NEXT_SELECTORS = ("a[rel=next]", "li.next:not(.disabled) > a", ".pagination li:not(.disabled) a[aria-label*=Next i]",
                  "a.paginate_button.next:not(.disabled)", "button[aria-label*='next page' i]:not([disabled])",
                  "a[title*='next page' i]", "a:text-matches('^ *(next|next *[›»>]+|[›»>]) *$', 'i')",
                  "button:text-matches('^ *(next|next *[›»>]+|[›»>]) *$', 'i'):not([disabled])")


class Browser:
    def __init__(self, settings, headless=None):
        from playwright.sync_api import sync_playwright
        self.st = settings
        self.pw = sync_playwright().start()
        kw = dict(headless=settings["headless"] if headless is None else headless,
                  viewport={"width": 1366, "height": 900}, accept_downloads=False,
                  locale="en-GB", timezone_id="Asia/Karachi")
        if settings.get("browser_executable"):
            kw["executable_path"] = settings["browser_executable"]
        elif settings.get("browser_channel"):
            kw["channel"] = settings["browser_channel"]
        self.ctx = self.pw.chromium.launch_persistent_context(settings["profile_dir"], **kw)
        self.ctx.set_default_timeout(settings["page_timeout_seconds"] * 1000)
        if STATE_FILE.exists():
            try:
                self.ctx.add_cookies(json.loads(STATE_FILE.read_text())["cookies"])
            except Exception:
                pass

    def save_cookies(self):
        try:
            STATE_FILE.write_text(json.dumps({"cookies": self.ctx.cookies()}))
        except Exception:
            pass

    def close(self):
        self.save_cookies()
        try:
            self.ctx.close()
        finally:
            self.pw.stop()


def goto(page, url, st):
    page.goto(url, wait_until="domcontentloaded")
    settle(page)


def settle(page, ms=15000):
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass
    page.wait_for_timeout(800)


def body_text(page):
    try:
        return page.inner_text("body", timeout=5000)
    except Exception:
        return ""


def is_logged_in(page, src):
    chk = src.get("logged_in_check")
    if not chk:
        return None  # cannot tell
    return bool(re.search(chk, body_text(page), re.I))


def auto_login(page, src, st, log):
    """Sign in with the username/password saved in Windows Credential Manager, if any."""
    user, pw = secrets.get_login(src["id"])
    if not (user and pw):
        return False
    goto(page, src.get("login_url") or src["url"], st)
    fill_login(page, src, user, pw)
    try:
        page.locator(src.get("password_selector", "input[type=password]")).first.press("Enter")
    except Exception:
        pass
    settle(page)
    log(f"  submitted saved login for {src['id']}")
    return True


def fill_login(page, src, user, pw):
    usel = [src["username_selector"]] if src.get("username_selector") else USER_SELECTORS
    for sel in usel:
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                loc.fill(user)
                break
        except Exception:
            continue
    try:
        page.locator(src.get("password_selector", "input[type=password]")).first.fill(pw)
    except Exception:
        pass


def ensure_login(page, src, st, log):
    state = is_logged_in(page, src)
    if state is None or state:
        return True
    if auto_login(page, src, st, log):
        goto(page, src["url"], st)
        if is_logged_in(page, src):
            return True
    return False


def run_actions(page, actions):
    """Optional per-portal steps from sources.yaml, e.g. choose '100 per page'."""
    for a in actions or []:
        try:
            if "click" in a:
                page.locator(a["click"]).first.click()
            elif "select" in a:
                page.locator(a["select"]).first.select_option(str(a["value"]))
            elif "fill" in a:
                page.locator(a["fill"]).first.fill(str(a["value"]))
            elif "press" in a:
                page.keyboard.press(a["press"])
            elif "wait" in a:
                page.wait_for_timeout(int(a["wait"] * 1000))
            settle(page)
        except Exception:
            pass


def click_next(page, src):
    sels = [src["next"]] if src.get("next") else NEXT_SELECTORS
    for sel in sels:
        try:
            loc = page.locator(sel)
            n = loc.count()
            for i in range(min(n, 4)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                cls = (el.get_attribute("class") or "") + " " + (el.evaluate("e => e.parentElement ? e.parentElement.className : ''") or "")
                if re.search(r"\bdisabled\b", cls) or el.get_attribute("aria-disabled") == "true":
                    continue
                el.click()
                settle(page)
                return True
        except Exception:
            continue
    return False


def _json_bodies(responses):
    out = []
    for r in responses:
        try:
            if r.status != 200:
                continue
            b = r.body()
            if len(b) > 8_000_000:
                continue
            out.append((r.url, json.loads(b)))
        except Exception:
            continue
    return out


def collect(page, responses, src):
    """Records visible now: from the page's tables and from JSON the page downloaded."""
    fields = src.get("fields")
    strategy = src.get("strategy", "auto")
    table = extract_tables(page.content(), page.url, fields) if strategy in ("auto", "table") else []
    js = []
    if strategy in ("auto", "json"):
        for url, obj in _json_bodies(responses):
            js.extend(extract_json(obj, page.url, fields, src.get("detail_url")))
    return table if len(table) >= len(js) else js


def _key(r):
    return (r["title"].lower(), r.get("ref", ""), r.get("closing"))


def fetch_generic(page, src, st, log):
    responses = []
    page.on("response", lambda r: responses.append(r)
            if "json" in (r.headers.get("content-type") or "") and r.request.resource_type in ("xhr", "fetch") else None)
    goto(page, src["url"], st)
    if src.get("login") and not ensure_login(page, src, st, log):
        return "needs_login", []
    run_actions(page, src.get("before"))
    out, seen = [], set()
    max_pages = int(src.get("max_pages", st["max_pages"]))
    for i in range(max_pages):
        recs = collect(page, responses, src)
        responses.clear()
        fresh = [r for r in recs if _key(r) not in seen]
        for r in fresh:
            seen.add(_key(r))
        out.extend(fresh)
        log(f"  page {i + 1}: {len(recs)} rows ({len(fresh)} new)")
        if not fresh or i + 1 >= max_pages:
            break
        time.sleep(st["page_delay_seconds"])
        if not click_next(page, src):
            break
    return "ok", out


# ---------------------------------------------------------------- UNGM

UNGM_PAYLOAD = {
    "PageIndex": 0, "PageSize": 50, "Title": "", "Description": "", "Reference": "",
    "PublishedFrom": "", "PublishedTo": "", "DeadlineFrom": "", "DeadlineTo": "",
    "Countries": [], "Agencies": [], "UNSPSCs": [], "NoticeTypes": [], "SortField": "DatePublished",
    "SortAscending": False, "isPicker": False, "IsSustainable": False, "NoticeDisplayType": None,
    "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": [],
}


def fetch_ungm(page, src, st, log):
    """UNGM notice search. The search runs inside your signed-in browser session."""
    goto(page, src["url"], st)
    if src.get("login") and not ensure_login(page, src, st, log):
        return "needs_login", []
    token = page.evaluate("() => (document.querySelector('input[name=__RequestVerificationToken]') || {}).value || ''")
    out, seen = [], set()
    today = datetime.now().strftime("%d-%b-%Y")
    for kw in src.get("keywords", [""]):
        payload = dict(UNGM_PAYLOAD, **(src.get("payload") or {}))
        payload["Title"] = kw
        payload["DeadlineFrom"] = payload["DeadlineFrom"] or today
        for pg in range(int(src.get("max_pages", 3))):
            payload["PageIndex"] = pg
            res = page.evaluate("""async ([url, body, token]) => {
                const r = await fetch(url, {method: 'POST', credentials: 'include',
                  headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
                            ...(token ? {'__RequestVerificationToken': token, 'RequestVerificationToken': token} : {})},
                  body: JSON.stringify(body)});
                return {status: r.status, text: await r.text()};
            }""", [src.get("search_url", "/Public/Notice/Search"), payload, token])
            if res["status"] != 200:
                log(f"  search '{kw}' failed: HTTP {res['status']}")
                break
            recs = extract_tables("<div>" + res["text"] + "</div>", "https://www.ungm.org/Public/Notice", src.get("fields"))
            fresh = [r for r in recs if _key(r) not in seen]
            for r in fresh:
                seen.add(_key(r))
            out.extend(fresh)
            log(f"  '{kw or '(all)'}' page {pg + 1}: {len(recs)} rows")
            if len(recs) < payload["PageSize"]:
                break
            time.sleep(st["page_delay_seconds"])
        time.sleep(st["page_delay_seconds"])
    if not out:  # search API changed: fall back to reading the page as shown
        log("  search returned nothing; reading the notice page directly")
        return fetch_generic(page, dict(src, login=False), st, log)
    return "ok", out


# ---------------------------------------------------------------- JSON APIs (e.g. World Bank)

def fetch_json_api(page, src, st, log):
    out = []
    size = int(src.get("page_size", 100))
    for i in range(int(src.get("max_pages", 5))):
        url = src["api_url"].format(offset=i * size, page=i + 1, size=size)
        r = page.request.get(url, timeout=st["page_timeout_seconds"] * 1000)
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status} from {url}")
        recs = extract_json(r.json(), src.get("url", url), src.get("fields"), src.get("detail_url"))
        out.extend(recs)
        log(f"  page {i + 1}: {len(recs)} rows")
        if len(recs) < size:
            break
        time.sleep(st["page_delay_seconds"])
    return "ok", out


ADAPTERS = {"generic": fetch_generic, "ungm": fetch_ungm, "json_api": fetch_json_api}


def fetch_source(browser, src, log):
    """Returns (status, records, error). status: ok | empty | needs_login | error."""
    page = browser.ctx.new_page()
    try:
        status, recs = ADAPTERS[src.get("adapter", "generic")](page, src, browser.st, log)
        if status == "ok" and not recs:
            capture(page, src["id"])
            return "empty", [], "Page opened but no tender list was recognised (page saved in data/captures)."
        if status == "needs_login":
            capture(page, src["id"])
            return status, [], "Not signed in. Run: tw login " + src["id"]
        for r in recs:
            if src.get("url_is_home") and r.get("url") in ("", src["url"]):
                r["url"] = src["url"]
        return status, recs, ""
    except Exception as e:  # one broken portal must not stop the others
        capture(page, src["id"])
        return "error", [], f"{type(e).__name__}: {e}"[:800]
    finally:
        browser.save_cookies()
        page.close()


def capture(page, sid):
    try:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        (CAPTURE_DIR / f"{sid}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
