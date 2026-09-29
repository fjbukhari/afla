"""Spot the same tender advertised on several portals (e.g. PPRA and EPADS)."""
import re

_STOP = set("the of for and in at to a an on with from by procurement purchase supply tender notice".split())


def norm_title(t):
    t = t.lower()
    t = re.sub(r"^\s*(t|tender|no|ref)?[-\s.#:]*\d+[a-z]?[-\s.:)]+", " ", t)  # "T-79 ...", "135217 ..."
    t = re.sub(r"\(re-?tender\w*\)|re-?tender\w*", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return [w for w in t.split() if w not in _STOP and len(w) > 1]


def _sim(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def _completeness(t):
    return sum(bool(t.get(k)) for k in ("ref", "org", "closing", "published", "doc_url")) + (
        0 if t.get("url_is_home") else 1)


def find_duplicates(tenders, threshold=0.85):
    """Return {id: id_of_kept_copy} for tenders that duplicate another one.

    Two rows are the same tender when their cleaned titles are near-identical and
    their closing dates agree (or one is missing). Within one portal we only merge
    exact title+closing matches, because portals legitimately list lots with
    similar names.
    """
    items = [(t, norm_title(t["title"])) for t in tenders]
    buckets = {}
    for t, w in items:
        for k in set(w):
            buckets.setdefault(k, []).append((t, w))
    parent = {}

    def root(i):
        while parent.get(i, i) != i:
            i = parent[i]
        return i

    for t, w in items:
        cands = {id(x[0]): x for k in set(w) if len(buckets[k]) <= 300 for x in buckets[k]}
        for u, v in cands.values():
            if u is t or u["id"] <= t["id"]:
                continue
            if t.get("closing") and u.get("closing") and t["closing"] != u["closing"]:
                continue
            same_src = t["source"] == u["source"]
            if same_src and not (t["title"].lower().split() == u["title"].lower().split()
                                 and t.get("closing") == u.get("closing") and (t.get("ref") or "") == (u.get("ref") or "")):
                continue
            if _sim(w, v) >= threshold:
                a, b = root(t["id"]), root(u["id"])
                if a != b:
                    parent[b] = a
    groups = {}
    for t in tenders:
        groups.setdefault(root(t["id"]), []).append(t)
    dup = {}
    for g in groups.values():
        if len(g) < 2:
            continue
        keep = max(g, key=lambda x: (_completeness(x), -len(x["id"])))
        for x in g:
            if x is not keep:
                dup[x["id"]] = keep["id"]
    return dup
