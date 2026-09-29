"""Turn the many date formats used by tender portals into YYYY-MM-DD."""
import re
from datetime import datetime, timezone

from dateutil import parser as dparser

_NET = re.compile(r"/Date\((-?\d+)")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def parse_date(value):
    """Return 'YYYY-MM-DD' or None. Day comes before month (Pakistani/UK style)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if n > 1e11:  # epoch milliseconds
            n /= 1000
        if 1e9 < n < 5e9:
            return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%d")
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _NET.search(s)
    if m:
        return parse_date(int(m.group(1)))
    if s.isdigit() and len(s) >= 10:
        return parse_date(int(s))
    if _ISO.match(s):
        return s[:10]
    # keep only the first date when a cell holds "27-Sep-2026 11:00 AM (Opening 12:00)"
    s = re.sub(r"\s+", " ", s)
    s = re.split(r"\s*(?:\(|\||;|\bto\b)", s)[0]
    try:
        d = dparser.parse(s, dayfirst=True, fuzzy=True, default=datetime(1900, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return None
    if d.year < 2000 or d.year > 2100:
        return None
    return d.strftime("%Y-%m-%d")
