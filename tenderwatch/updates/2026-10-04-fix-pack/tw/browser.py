"""Drives a real browser (Edge on Windows) so that JavaScript portals and logged-in portals
work the same way as public ones. Cookies from your sign-ins are kept in data/ on this PC only."""
import json
import re
import time
from datetime import datetime

from . import DATA_DIR
from . import secrets
from .extract import extract_json, extract_links, extract_tables

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
                  locale="en-GB", timezone_id="Asia/Karachi",
                  # Chromium otherwise advertises that it is being driven by a program, which is
                  # what the EPADS firewall appears to act on (see _fix_headless_fingerprint).
                  args=["--disable-blink-features=AutomationControlled"],
                  # The Punjab eP portal will not let anyone sign in without the browser's
                  # location ("Location access is mandatory for security and audit purposes"),
                  # and a browser with nobody at it has nothing to grant. Offer Lahore, which is
                  # where the portal expects its suppliers to be; no portal is told anything it
                  # would not learn from an ordinary visit.
                  permissions=["geolocation"],
                  geolocation={"latitude": 31.5204, "longitude": 74.3587, "accuracy": 120})
        if settings.get("browser_executable"):
            kw["executable_path"] = settings["browser_executable"]
        elif settings.get("browser_channel"):
            kw["channel"] = settings["browser_channel"]
        try:
            self.ctx = self.pw.chromium.launch_persistent_context(settings["profile_dir"], **kw)
        except Exception as e:
            # Your sign-ins live in one browser profile folder, and Chromium allows only one
            # window at a time to use it. So leaving the `tw login` window open makes the next
            # run fail - with a message about a "ProcessSingleton", which says nothing useful to
            # the person reading it. Say what to do instead.
            if "ProcessSingleton" in str(e) or "already in use" in str(e):
                self.pw.stop()
                raise RuntimeError(
                    "Another Tender Watch browser window is still open.\n"
                    "Close it (the window that opened for `tw login`, and any left from an\n"
                    "earlier run), then try again. Only one can use your saved sign-ins at a time."
                ) from None
            self.pw.stop()
            raise
        self.ctx.set_default_timeout(settings["page_timeout_seconds"] * 1000)
        self._fix_headless_fingerprint()
        if STATE_FILE.exists():
            try:
                self.ctx.add_cookies(json.loads(STATE_FILE.read_text())["cookies"])
            except Exception:
                pass

    def _fix_headless_fingerprint(self):
        """Ask the portals with the same User-Agent as an ordinary browser window.

        When it runs without a visible window, Chromium puts "HeadlessChrome" in the
        User-Agent it sends with every request. On the office PC's first real run, all five
        EPADS portals answered with a firewall page - "Web Page Blocked! ... Attack ID:
        20000051" - while signing in to the very same address by hand, from the same PC and
        the same IP address, worked. The request headers are the difference, so send the
        headers the operator's own browser sends: the same browser, the same version, just
        without announcing that nobody is watching it.

        This only affects how we identify ourselves on portals the operator is registered
        with; it does not bypass any sign-in.
        """
        try:
            page = self.ctx.new_page()
            try:
                ua = page.evaluate("navigator.userAgent")
            finally:
                page.close()
        except Exception:
            return
        if not ua or "Headless" not in ua:
            self.user_agent = ua or ""
            return
        ua = ua.replace("HeadlessChrome", "Chrome").replace("Headless", "")
        self.user_agent = ua
        try:
            self.ctx.set_extra_http_headers({
                "User-Agent": ua,
                "Accept-Language": "en-GB,en;q=0.9",
            })
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


# A portal interrupting its own first page load is normal, not a failure. Government portals
# redirect constantly: http to https, www to the vendor subdomain, and a vendor who is already
# signed in being sent straight to their dashboard. Playwright reports the interrupted first
# navigation as an error even though the browser has landed somewhere perfectly good, so those
# two messages are treated as "we arrived, just not where we first asked".
# Found when a signed-in EPADS account sent www.epads.gov.pk straight to
# vendors.epads.gov.pk/dashboard and `tw login epads-fed` stopped with a traceback.
_BENIGN_NAV = ("interrupted by another navigation", "net::ERR_ABORTED")


def goto(page, url, st=None):
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        if not any(b in str(e) for b in _BENIGN_NAV):
            raise                       # a real failure: no such host, refused, timed out
        try:
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        # Only a redirect counts as arriving. A blank page means the load really did fail.
        if not page.url or page.url.startswith("about:"):
            raise
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


# Signs that a portal considers us signed in, beyond whatever the portal's own entry in
# sources.yaml asks for. These exist because every logged_in_check in sources.yaml was written
# without access to the real portal - they block cloud servers - so each one is a guess until it
# meets the live site. Reported from the office PC: EPADS was signed in and showing its vendor
# dashboard, and the check still said "Still looks signed out".
_SIGNED_IN_TEXT = r"log\s?out|sign\s?out|my (bids|profile|dashboard|account|tenders)|welcome,|signed in as"
_SIGNED_IN_HREF = r"logout|signout|sign-out|log-out"


def signed_in_signals(page, src):
    """Everything observable about whether this looks like a signed-in session.

    Returns a dict rather than a yes/no, so `tw login` can show the operator what it saw when it
    cannot decide. A sign-out control is the reliable marker, and it is looked for in the page's
    links as well as its text: on many portals it is an icon inside a collapsed account menu, so
    it never appears in the visible text the old check read.
    """
    out = {"url": "", "title": "", "text_hit": "", "href_hit": "", "configured_hit": ""}
    try:
        out["url"] = page.url or ""
        out["title"] = (page.title() or "")[:120]
    except Exception:
        pass
    text = body_text(page)
    # the whole document, including text inside collapsed menus that inner_text leaves out
    try:
        full = page.content()
    except Exception:
        full = text
    m = re.search(_SIGNED_IN_TEXT, text, re.I) or re.search(_SIGNED_IN_TEXT, full, re.I)
    if m:
        out["text_hit"] = m.group(0)
    try:
        hrefs = page.eval_on_selector_all("a[href]", "a => a.map(x => x.getAttribute('href'))")
    except Exception:
        hrefs = []
    for h in hrefs or []:
        if h and re.search(_SIGNED_IN_HREF, str(h), re.I):
            out["href_hit"] = str(h)[:120]
            break
    chk = src.get("logged_in_check")
    if chk:
        m2 = re.search(chk, text, re.I) or re.search(chk, full, re.I)
        if m2:
            out["configured_hit"] = m2.group(0)
    return out


# Phrases a portal shows when its own back end has fallen over. Seen on the office PC:
# www.epads.gov.pk answering with a page whose entire content was "connection not found".
# Without this the tool called that "no tender list was recognised", which sends you looking
# for a layout change that has not happened, or "still looks signed out", which sends you to
# sign in again. Neither is the problem; the portal is simply down, and the answer is to wait.
_DOWN_PHRASES = (
    "connection not found", "service unavailable", "temporarily unavailable",
    "under maintenance", "database error", "bad gateway", "gateway timeout",
    "cannot connect", "connection timed out", "internal server error",
    "server error", "site is down", "503 ", "502 ", "500 ",
)
# A real tender page is long, and may legitimately contain these words - one of the tenders in
# the live database is a "COMPREHENSIVE MAINTENANCE CONTRACT OF NEONATE VENTILATORS". So a page
# only counts as down when it is BOTH short and matching: a portal reporting its own failure has
# almost nothing else on it.
_DOWN_MAX_CHARS = 400


def looks_down(page):
    """A short reason if the portal is answering with its own failure page, otherwise ''."""
    text = " ".join(body_text(page).split())
    if len(text) > _DOWN_MAX_CHARS:
        return ""
    low = text.lower()
    for phrase in _DOWN_PHRASES:
        if phrase.strip() in low:
            return text[:160] or phrase.strip()
    if not text:
        return "the page came back empty"
    return ""


# Firewall / WAF block pages. Seen on all five EPADS portals from the office PC:
# "Web Page Blocked! ... URL: vendors.epads.gov.pk/dashboard  Client IP: ...  Attack ID: 20000051".
# Reporting that as "no tender list was recognised" sends the operator looking for a layout
# change, and reporting it as "signed out" sends them to re-enter a password. It is neither.
# An unmistakable firewall page: these phrases do not occur in tender lists.
_BLOCK_STRONG = (
    "web page blocked", "request blocked", "you have been blocked",
    "the url you requested has been blocked", "403 forbidden",
    "attention required! | cloudflare",
)
# These DO occur in tender lists - "Access control and security policy audit for the blood
# bank" is the sort of thing being tendered, and an expired sign-in also says "Access Denied".
# So they only count alongside a reference that only a firewall prints.
_BLOCK_WEAK = ("access denied", "blocked", "forbidden", "security policy", "not authorized")
_BLOCK_MARKER = re.compile(
    r"client ip|attack id|ray id|reference ?#|incident id|error code \d|support id", re.I)
# A firewall page is short; a long page is the portal's own content.
_BLOCK_MAX_CHARS = 1200


def looks_blocked(page):
    """A short reason if a firewall is refusing us rather than the portal failing, else ''.

    The reason keeps the firewall's own URL, client IP and attack/reference number, because
    those are exactly what the portal's administrator needs if it has to be reported.
    """
    text = " ".join(body_text(page).split())
    if not text or len(text) > _BLOCK_MAX_CHARS:
        return ""
    low = text.lower()
    if any(p in low for p in _BLOCK_STRONG):
        return text[:400]
    if any(p in low for p in _BLOCK_WEAK) and _BLOCK_MARKER.search(low):
        return text[:400]
    return ""


def is_logged_in(page, src):
    """True / False / None, where None honestly means "cannot tell from this page"."""
    sig = signed_in_signals(page, src)
    if sig["configured_hit"] or sig["text_hit"] or sig["href_hit"]:
        return True
    if not src.get("logged_in_check"):
        return None
    return False


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
            elif "wait_for" in a:
                # A portal that builds its list with JavaScript (BPPRA) is still showing
                # "loading" when the page is otherwise finished, so wait for the list itself.
                page.wait_for_selector(a["wait_for"], timeout=int(a.get("timeout", 15)) * 1000)
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
    if strategy == "links":
        return extract_links(page.content(), page.url, src.get("link_pattern"))
    html = page.content()
    table = extract_tables(html, page.url, fields) if strategy in ("auto", "table") else []
    js = []
    if strategy in ("auto", "json"):
        for url, obj in _json_bodies(responses):
            js.extend(extract_json(obj, page.url, fields, src.get("detail_url")))
    best = table if len(table) >= len(js) else js
    if best or strategy != "auto":
        return best
    # Many institution pages are not a table at all - they are a list of links to notices, which
    # is how the KP health department and UNDP publish theirs. "auto" never tried that, so both
    # were reported as "no tender list was recognised" while their tenders were in plain sight.
    return extract_links(html, page.url, src.get("link_pattern"))


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
    # Some pages are an archive rather than a list of what is open: the KP health department's
    # tenders page carries every notice back to 2019, none of them with a closing date, so all
    # of them would be treated as current for as long as the page keeps listing them - and the
    # first run would email a few hundred of them. Those pages are newest-first, so a portal can
    # say how far down to read. Without max_items nothing is dropped.
    limit = src.get("max_items")
    if limit and len(out) > int(limit):
        log(f"  keeping the {int(limit)} newest of {len(out)} (max_items)")
        out = out[: int(limit)]
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


def _insecure_page(browser, src, log):
    """A page for a portal whose HTTPS certificate does not check out.

    Several Pakistani government sites serve an expired or self-signed certificate -
    ppms.pprasindh.gov.pk answered ERR_CERT_AUTHORITY_INVALID on the office PC's first run - and
    the browser refuses to open them at all. A source can opt in with `insecure: true`.

    It gets a SEPARATE, throwaway browser with no access to your saved sign-ins, for two reasons.
    A certificate that cannot be verified means the connection cannot be proven to be with the
    real portal, so nothing of yours should travel over it; and relaxing the check for one portal
    must not relax it for the portals you do sign in to. Signing in over such a connection is
    refused outright - see fetch_source.
    """
    kw = dict(headless=browser.st.get("headless", True))
    if browser.st.get("browser_executable"):
        kw["executable_path"] = browser.st["browser_executable"]
    elif browser.st.get("browser_channel"):
        kw["channel"] = browser.st["browser_channel"]
    b = browser.pw.chromium.launch(**kw)
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900},
                        locale="en-GB", timezone_id="Asia/Karachi")
    log(f"  {src['id']}: certificate not verified, reading it in a separate browser with no sign-ins")
    return b, ctx, ctx.new_page()


def fetch_source(browser, src, log):
    """Returns (status, records, error). status: ok | empty | needs_login | error."""
    insecure = bool(src.get("insecure"))
    if insecure and src.get("login"):
        # Never send a password over a connection whose certificate cannot be verified.
        return "error", [], ("This portal is marked insecure (its certificate does not check out) "
                             "and also needs a sign-in. Those cannot be combined: remove one of "
                             "them in config/sources.yaml.")
    extra_browser = extra_ctx = None
    if insecure:
        extra_browser, extra_ctx, page = _insecure_page(browser, src, log)
    else:
        page = browser.ctx.new_page()
    try:
        status, recs = ADAPTERS[src.get("adapter", "generic")](page, src, browser.st, log)
        if status == "ok" and not recs:
            capture(page, src["id"])
            blocked = looks_blocked(page)
            if blocked:
                return "error", [], (
                    "The portal's firewall refused us, so no tender list was ever sent: "
                    + blocked
                    + "  This is not a sign-in problem and not a layout change. Open the same "
                      "address in your normal browser on this PC: if it works there, send the "
                      "saved page in data/captures to whoever maintains this tool.")
            down = looks_down(page)
            if down:
                return "error", [], "The portal is not responding properly: " + down + " Nothing to do but try later."
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
        if extra_ctx is not None:
            try:
                extra_ctx.close()
                extra_browser.close()
            except Exception:
                pass


def capture(page, sid):
    """Save the page as it stands, and return where it went so the operator can be told."""
    try:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        path = CAPTURE_DIR / f"{sid}.html"
        path.write_text(page.content(), encoding="utf-8")
        return path
    except Exception:
        return None
