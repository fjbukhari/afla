"""Generic extraction of tender lists from HTML tables, div grids and JSON.

Portals change their layouts often, so instead of hard-coding each page we read
the column headers (or JSON keys) and map them to our fields by meaning.
A source can still pin a header/key to a field with `fields:` in sources.yaml.
"""
import re
from urllib.parse import urljoin

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
        rec[f] = cell.get_text(" ", strip=True)
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
        mapping = map_headers(headers, overrides)
        recs = [r for r in (_finish(_row_to_rec(c, mapping, base_url), base_url) for c in rows) if r]
        q = _grid_quality(mapping, len(recs))
        if q > best_q:
            best, best_q = recs, q
    return best


def _tables(soup):
    out = []
    for t in soup.find_all("table"):
        if t.find("table"):  # layout table wrapping the real one
            continue
        trs = t.find_all("tr")
        if len(trs) < 2:
            continue
        head = None
        thead = t.find("thead")
        if thead and thead.find("tr"):
            head = thead.find_all("tr")[-1]
        else:
            for tr in trs[:3]:
                if tr.find("th"):
                    head = tr
        if head is None:
            head = trs[0]
        headers = [c.get_text(" ", strip=True) for c in head.find_all(["th", "td"])]
        rows = []
        for tr in trs:
            if tr is head or (thead and tr.find_parent("thead") is thead):
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
                try:
                    rec["url"] = detail_url.format(**{_words(k).replace(" ", "_"): v for k, v in f.items()}, **f)
                except (KeyError, IndexError, ValueError):
                    pass
            rec = _finish(rec, base_url)
            if rec:
                rec["raw"] = {k: v for k, v in f.items() if isinstance(v, (str, int, float)) and len(str(v)) < 300}
                recs.append(rec)
        if recs:
            best, best_q = recs, _grid_quality(m, len(recs))
    return best
