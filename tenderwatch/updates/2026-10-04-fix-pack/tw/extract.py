"""Generic extraction of tender lists from HTML tables, div grids and JSON.

Portals change their layouts often, so instead of hard-coding each page we read
the column headers (or JSON keys) and map them to our fields by meaning.
A source can still pin a header/key to a field with `fields:` in sources.yaml.
"""
import re
import statistics
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup

from .dates import parse_date

FIELDS = ("title", "org", "ref", "closing", "published", "type", "location", "url", "doc_url")

# Order matters: the first rule that matches a header wins.
_RULES = [
    ("_skip", r"^(s\.?\s*no|sr\.?\s*(no|#)?|#|no\.?|serial( no)?|sl\.?\s*no|action|actions|view|details|status|select)\.?$"),
    ("doc_url", r"\b(document|download|attachment|file|pdf|bidding doc)"),
    ("url", r"^(url|link|href|detail ?url|notice ?url|web ?link)$"),
    ("closing", r"clos|deadline|due ?date|last ?date|submission|bid ?open|opening|expir|end ?date"),
    ("published", r"publish|advertis|posted|posting|issue ?date|upload|start ?date|notice ?date|date of (ad|pub)|created|^date$"),
    ("ref", r"\bref\b|reference|tender ?(no|number|id|#|code)|notice ?(no|number|id)|ppra ?(no|id)|bid ?(no|number)|\bid\b|^no$|code|solicitation"),
    ("org", r"organi[sz]|department|dept|agency|procuring|buyer|entity|office|ministry|institut|hospital|purchaser|client|employer|division|authority|borrower"),
    ("type", r"\btype\b|method|nature|categor"),
    ("location", r"city|district|location|province|region|country"),
    ("title", r"title|description|subject|particular|name of|tender|procurement|notice|item|work|detail|summary|name|scope"),
]
_RULES = [(f, re.compile(p, re.I)) for f, p in _RULES]


def _words(key):
    """'procuringAgencyName' / 'closing_date' -> 'procuring agency name' / 'closing date'."""
    k = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(key))
    k = re.sub(r"[_\-.:]+", " ", k)
    return re.sub(r"\s+", " ", k).strip().lower()


def map_headers(headers, overrides=None):
    """Return {index: field} for a list of header strings."""
    overrides = {str(k).lower(): v for k, v in (overrides or {}).items()}
    out, used = {}, set()
    for i, h in enumerate(headers):
        w = _words(h)
        if not w:
            continue
        if w in overrides or str(h).lower() in overrides:
            f = overrides.get(w) or overrides.get(str(h).lower())
            out[i] = f
            used.add(f)
            continue
        for field, rx in _RULES:
            if rx.search(w):
                if field != "_skip" and field not in used:
                    out[i] = field
                    used.add(field)
                break
    return out


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _finish(rec, base_url):
    """Normalise one record; return None if it is not a usable tender row."""
    title = _clean(rec.get("title"))
    if len(title) < 6 or not re.search(r"[A-Za-z]{3}", title):
        return None
    rec["title"] = title[:500]
    for k in ("org", "ref", "type", "location"):
        rec[k] = _clean(rec.get(k))[:300]
    rec["closing_raw"] = _clean(rec.get("closing"))
    rec["closing"] = parse_date(rec.get("closing"))
    rec["published"] = parse_date(rec.get("published"))
    for k in ("url", "doc_url"):
        v = rec.get(k)
        if v and base_url and not str(v).startswith(("http://", "https://")):
            v = urljoin(base_url, str(v))
        rec[k] = v or ""
    return rec


def _cell_links(cell, base_url):
    links = []
    for a in cell.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:void", "#")) or href == "":
            continue
        links.append(urljoin(base_url or "", href))
    return links


def _is_doc(u):
    return bool(re.search(r"\.(pdf|docx?|xlsx?|zip|rar)(\?|$)|download|attachment|getfile|viewfile", u, re.I))


_TITLE_RX = next(rx for f, rx in _RULES if f == "title")

# "OUTSOURCING OF SOLID WASTE MANAGEMENT ... ( View Tender Detail )" - Punjab PPRA puts the
# link label inside the title cell, so it would be stored as part of every tender's name.
_NAV_TEXT = re.compile(r"^\(?\s*(view|see|open|read|click|more)\b.{0,40}$", re.I)


def _cell_text(cell):
    """The cell's text, without link labels that are navigation rather than content."""
    drop = {id(a) for a in cell.find_all("a") if _NAV_TEXT.match(a.get_text(" ", strip=True))}
    if not drop:
        return cell.get_text(" ", strip=True)
    parts = [str(s) for s in cell.descendants
             if isinstance(s, str) and not any(id(p) in drop for p in s.parents)]
    txt = re.sub(r"\(\s*\)", " ", " ".join(parts))
    return re.sub(r"\s+", " ", txt).strip()


def _title_alternatives(headers, mapping):
    """Every column whose header also means "title" and that holds no other field."""
    out = []
    for i, h in enumerate(headers):
        w = _words(h)
        if not w or mapping.get(i) not in (None, "title"):
            continue
        if _TITLE_RX.search(w):
            out.append(i)
    return out


def _col_profile(rows, i):
    """(median length, share of distinct values) of one column's non-empty cells."""
    vals = [_cell_text(c[i]) for c in rows if len(c) > i]
    ne = [v for v in vals if v]
    if not ne:
        return 0.0, 0.0
    return float(statistics.median(len(v) for v in ne)), len(set(ne)) / len(ne)


def _refine_title(mapping, headers, rows, overrides=None):
    """Pick the right column when several headers mean "title".

    The first matching header wins, which is wrong on Punjab PPRA: its "Procurement Title"
    column holds the stage of the notice ("Tender", "Addendum" - six values over a hundred
    rows) while "Procurement Name" holds the actual subject. This only steps in when the
    chosen column reads like a repeated label rather than a tender name, and never overrides
    a column pinned with `fields:` in sources.yaml.
    """
    if "title" in (overrides or {}).values():
        return mapping
    cur = next((i for i, f in mapping.items() if f == "title"), None)
    if cur is None or not rows:
        return mapping
    cur_len, cur_var = _col_profile(rows, cur)
    if cur_len >= 25 and cur_var >= 0.3:
        return mapping
    best, best_len = cur, cur_len
    for i in _title_alternatives(headers, mapping):
        if i == cur:
            continue
        ln, var = _col_profile(rows, i)
        if ln >= max(25.0, best_len * 2) and var >= 0.3:
            best, best_len = i, ln
    if best == cur:
        return mapping
    mapping = {k: v for k, v in mapping.items() if k != cur}
    mapping[best] = "title"
    return mapping


def _row_to_rec(cells, mapping, base_url):
    rec = {}
    links = []
    for i, cell in enumerate(cells):
        f = mapping.get(i)
        cl = _cell_links(cell, base_url)
        links.extend(cl)
        if not f:
            continue
        if f in ("url", "doc_url"):
            if cl:
                rec[f] = cl[0]
            continue
        rec[f] = _cell_text(cell)
        if f == "title" and cl and not _is_doc(cl[0]):
            rec.setdefault("url", cl[0])
    if not rec.get("doc_url"):
        docs = [u for u in links if _is_doc(u)]
        if docs:
            rec["doc_url"] = docs[0]
    if not rec.get("url"):
        pages = [u for u in links if not _is_doc(u)]
        if pages:
            rec["url"] = pages[0]
    return rec


def _grid_quality(mapping, n):
    fs = set(mapping.values()) & {"title", "org", "closing", "ref", "published"}
    # a title plus at least one of buyer/closing/reference/published, so menus and news lists are ignored
    if "title" not in fs or len(fs) < 2 or n == 0:
        return 0
    return len(fs) * 1000 + n


def extract_tables(html, base_url="", overrides=None):
    """Best-matching <table> (or div grid) in the page -> list of records."""
    soup = BeautifulSoup(html, "html.parser")
    best, best_q = [], 0
    for grid in _tables(soup) + _div_grids(soup):
        headers, rows = grid
        mapping = _refine_title(map_headers(headers, overrides), headers, rows, overrides)
        recs = [r for r in (_finish(_row_to_rec(c, mapping, base_url), base_url) for c in rows) if r]
        q = _grid_quality(mapping, len(recs))
        if q > best_q:
            best, best_q = recs, q
    return best


def _own_rows(table):
    """The rows of this table, not those of a table nested inside it."""
    return [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]


def _header_row(table, trs):
    """The row carrying the column names.

    A Telerik RadGrid - Punjab PPRA - puts two rows in its <thead>: the column names, then
    an empty filter row. Taking the last row of the <thead> read nine blank headers, so
    nothing could be mapped and the whole portal looked unrecognised. Take the row that
    actually names the most columns instead.
    """
    thead = table.find("thead")
    cands = []
    if thead:
        cands = [tr for tr in thead.find_all("tr") if tr.find_parent("table") is table]
    if not cands:
        cands = [tr for tr in trs[:3] if tr.find("th")]
    if not cands:
        return trs[0]
    return max(cands, key=lambda tr: sum(
        1 for c in tr.find_all(["th", "td"]) if c.get_text(strip=True)))


def _tables(soup):
    out = []
    for t in soup.find_all("table"):
        # A table containing another table used to be skipped as a layout wrapper. That also
        # skipped every data grid with a pager or toolbar table inside it, which is how
        # Punjab PPRA's hundred tenders were missed. Judge a table by its OWN rows instead:
        # a layout wrapper has none, a data grid has all of them.
        trs = _own_rows(t)
        if len(trs) < 2:
            continue
        head = _header_row(t, trs)
        headers = [c.get_text(" ", strip=True) for c in head.find_all(["th", "td"])]
        rows = []
        for tr in trs:
            if tr is head or tr.find_parent("thead") is not None:
                continue
            cells = tr.find_all(["td", "th"], recursive=False)
            if len(cells) >= max(2, len(headers) - 2):
                rows.append(cells)
        out.append((headers, rows))
    return out


_ROWCLS = re.compile(r"(^|[\s_-])(table-?row|row|list-?item|result-?row|datarow)([\s_-]|$)", re.I)
_CELLCLS = re.compile(r"cell|col", re.I)


def _div_grids(soup):
    """Div-based tables such as UNGM's `div.tableRow > div.tableCell`, or ARIA grids."""
    groups = {}
    for el in soup.find_all(attrs={"role": "row"}) + soup.find_all(class_=_ROWCLS):
        cells = [c for c in el.find_all(recursive=False)
                 if c.get("role") in ("cell", "gridcell", "columnheader")
                 or _CELLCLS.search(" ".join(c.get("class", [])))]
        if len(cells) < 3:
            continue
        groups.setdefault(id(el.parent), []).append((el, cells))
    out = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        head_i = 0
        for i, (el, cells) in enumerate(rows[:3]):
            cls = " ".join(el.get("class", []))
            if re.search(r"head", cls, re.I) or any(c.get("role") == "columnheader" for c in cells):
                head_i = i
                break
        headers = [c.get_text(" ", strip=True) for c in rows[head_i][1]]
        out.append((headers, [cells for j, (_, cells) in enumerate(rows) if j != head_i]))
    return out


# ---------------------------------------------------------------- JSON

def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix} {k}".strip()
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif not isinstance(v, list):
            out[key] = v
    return out


def _lists_of_dicts(obj, depth=0):
    if depth > 6:
        return
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:20]):
            yield obj
        for x in obj[:50]:
            if isinstance(x, (dict, list)):
                yield from _lists_of_dicts(x, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _lists_of_dicts(v, depth + 1)


def extract_json(obj, base_url="", overrides=None, detail_url=None):
    """Find the list in a JSON response that looks most like tenders."""
    best, best_q = [], 0
    for lst in _lists_of_dicts(obj):
        flat = [_flatten(x) for x in lst]
        keys = list(dict.fromkeys(k for f in flat[:20] for k in f))
        m = map_headers(keys, overrides)
        mapping = {keys[i]: f for i, f in m.items()}
        q = _grid_quality(m, len(lst))
        if q <= best_q:
            continue
        recs = []
        for f in flat:
            rec = {field: f.get(k) for k, field in mapping.items() if f.get(k) not in (None, "")}
            for k in ("title", "org", "ref", "type", "location"):
                if k in rec:
                    rec[k] = str(rec[k])
            if detail_url and not rec.get("url"):
                # Both the tidied field names and the original ones are offered to the template,
                # so detail_url can use either. They must be merged into ONE mapping first:
                # passing two sets of keyword arguments fails the moment a name appears in both,
                # which is exactly what the World Bank feed does - it has a field called "id",
                # and the tidied form of "id" is also "id". That raised
                #   TypeError: str.format() got multiple values for keyword argument 'id'
                # and, because TypeError was not caught below, took the whole portal down with it.
                keys = {_words(k).replace(" ", "_"): v for k, v in f.items()}
                keys.update(f)                      # the feed's own names win
                try:
                    rec["url"] = detail_url.format(**keys)
                except (KeyError, IndexError, ValueError, TypeError):
                    pass                            # one odd record must never stop a portal
            rec = _finish(rec, base_url)
            if rec:
                rec["raw"] = {k: v for k, v in f.items() if isinstance(v, (str, int, float)) and len(str(v)) < 300}
                recs.append(rec)
        if recs:
            best, best_q = recs, _grid_quality(m, len(recs))
    return best


# ---------------------------------------------------------------- link lists

_TENDERISH = re.compile(r"tender|\bNIT\b|\bIFB\b|\bbid|quotation|\bRFQ\b|\bRFP\b|\bEOI\b|expression of interest|"
                        r"procurement|purchase|supply of|prequalification|pre-qualification|enlistment|invitation", re.I)
_DATE_IN_TEXT = re.compile(r"\b(\d{1,2}[-/. ](?:\d{1,2}|[A-Za-z]{3,9})[-/. ,]*\d{2,4}|\d{4}-\d{2}-\d{2})\b")


# Link labels that are not the name of anything: on the KP health department's tenders page
# every notice is followed by "Attachment : Download", and the page links to itself as "TENDERS".
# These became records with those as their titles.
_LABEL_ONLY = re.compile(
    r"^(all |view |see |open )?(tenders?|notices?|notifications?|procurements?|downloads?|"
    r"attachments?|archives?|bids?|documents?|advertisements?|more|details?|read more|"
    r"attachment\s*[:\-]\s*download|download\s*(file|pdf|now)?|click here|pdf)\W*$", re.I)
# UNDP's listing repeats its field labels inside the row - "Title <subject> Ref No <ref>
# UNDP Office/Country ..." - so the label and the reference are lifted out of the title.
_LEADING_LABEL = re.compile(r"^(title|subject|tender title|description)\s*[:\-]?\s+", re.I)
_REF_IN_LINE = re.compile(r"\bref(?:erence)?\.?\s*(?:no\.?|number|#)?\s*[:\-]?\s*"
                          r"([A-Z0-9][A-Z0-9/\-_.]{3,40})", re.I)


def _tidy_link_title(title):
    """Strip the field labels a listing repeats inside each row; return (title, ref)."""
    title = _LEADING_LABEL.sub("", title).strip()
    ref = ""
    m = _REF_IN_LINE.search(title)
    if m:
        ref = m.group(1).strip(" .,;")
        title = (title[:m.start()] + " " + title[m.end():]).strip()
    return re.sub(r"\s+", " ", title).strip(" :-|,"), ref


def _url_shape(u):
    """A link's shape, so that links belonging to one list can be told from stray ones:
    /news/view/1257 and /news/view/1255 share a shape, a Google Maps link does not."""
    p = urlsplit(u)
    path = re.sub(r"\d+", "#", p.path)
    path = re.sub(r"/[^/]{24,}$", "/*", path)          # a long filename or slug
    return p.netloc, path, ",".join(sorted(k for k, _ in parse_qsl(p.query)))


def _only_real_lists(recs):
    """Keep links that belong to a list of notices, drop the one-offs.

    Falling back to reading a page's links finds tenders on the institution pages, but on a
    portal's front page it also "found" the office address (because its line mentioned
    tenders) and a software vendor's URL. Wording alone cannot tell those apart. Belonging to
    a list can: a tender list has many links of the same shape, a stray link has none. A link
    straight to a PDF or Word notice is kept either way, since small institutions publish two
    or three of those and nothing else.
    """
    counts = {}
    for r in recs:
        counts[_url_shape(r["url"])] = counts.get(_url_shape(r["url"]), 0) + 1
    return [r for r in recs if counts[_url_shape(r["url"])] >= 3 or _is_doc(r["url"])]


def extract_links(html, base_url="", pattern=None):
    """Institution 'Tenders' pages are often just a list of links to PDF notices.
    Every link whose text (or its line) looks like a tender becomes a record."""
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup.select("nav, header, footer, script, style, noscript"):
        bad.decompose()
    rx = re.compile(pattern, re.I) if pattern else _TENDERISH
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        text = _clean(a.get_text(" "))
        line_el = a.find_parent(["li", "tr", "p", "div", "article"]) or a
        line = _clean(line_el.get_text(" "))[:600]
        title = text if len(text) >= 12 and not _LABEL_ONLY.match(text) else line
        if not rx.search(title) and not rx.search(href):
            continue
        title, ref = _tidy_link_title(title)
        if _LABEL_ONLY.match(title):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        dates = _DATE_IN_TEXT.findall(line)
        rec = {"title": title, "url": url, "doc_url": url if _is_doc(url) else "",
               "published": dates[0] if dates else None}
        if ref:
            rec["ref"] = ref
        m = re.search(r"(?:last date|closing|deadline|due date|submission)[^0-9A-Za-z]{0,20}(" + _DATE_IN_TEXT.pattern + ")", line, re.I)
        if m:
            rec["closing"] = m.group(1)
        rec = _finish(rec, base_url)
        if rec:
            out.append(rec)
    return _only_real_lists(out)
