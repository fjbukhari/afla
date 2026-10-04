"""Shared harness for stress-testing the Gene Panel Designer.

Serves a deterministic synthetic GRCh38 stand-in: the base at any genomic position is a pure
function of (chrom, position), so the same region fetched twice -- or fetched by two different
code paths, or by UCSC and Ensembl -- is byte-identical, and a reported primer can be checked
against the sequence independently.

Engineered "hard" zones are overlaid at fixed coordinates so each design path meets GC-rich
sequence, homopolymer runs, tandem repeats, an AT-rich stretch, and a duplicated (pseudogene-like)
copy of a real target region.
"""
import hashlib

BLOCK = 64


def _block(chrom, blk):
    h = hashlib.sha512(f"{chrom}:{blk}".encode()).digest()
    return ''.join('ACGT'[b & 3] for b in h)


def plain(chrom, start, end):
    """Background sequence: deterministic, ~50% GC, no engineered features."""
    out = []
    for b in range(start // BLOCK, (end - 1) // BLOCK + 1):
        out.append(_block(chrom, b))
    full = ''.join(out)
    off = start - (start // BLOCK) * BLOCK
    return full[off:off + (end - start)]


def _tile(pattern, n):
    return (pattern * (n // len(pattern) + 1))[:n]


# chrom -> list of (start, end, kind). Half-open, GRCh38-style 0-based.
# TP53 spans chr17:7,668,402-7,687,550; BRCA1 chr17:43,044,295-43,170,245.
ZONES = {
    'chr17': [
        (7_670_000, 7_670_600, 'gc'),        # GC-rich: covers TP53 exon 8 region
        (7_673_000, 7_673_400, 'at'),        # AT-rich
        (7_675_000, 7_675_120, 'homopolymer'),
        (7_676_500, 7_677_300, 'repeat'),    # tandem repeat near exon 4
        (43_090_000, 43_092_000, 'gc'),      # BRCA1 interior
    ],
}

# A duplicated copy: sequence at `dest` is identical to sequence at `src` (same length).
# Mimics a processed pseudogene / segmental duplication inside the 50 kb specificity window,
# so a primer pair has a second perfect binding site nearby.
DUPES = {
    'chr17': [
        # TP53 exon 6 region (~7,674,180-7,674,300) copied 9 kb downstream: inside the 50 kb window.
        {'src': (7_674_100, 7_674_500), 'dest': (7_665_000, 7_665_400)},
    ],
}


def _apply_zones(chrom, start, end, seq):
    s = list(seq)
    for z0, z1, kind in ZONES.get(chrom, []):
        a, b = max(start, z0), min(end, z1)
        if a >= b:
            continue
        if kind == 'gc':
            pat = 'GCGGCGCCGGCGGCCGCGGGCCGCCGGCGCGCCGGGCCGC'
        elif kind == 'at':
            pat = 'ATTTATAAATATTTAAATAAATTTATATTAAATATTTAAT'
        elif kind == 'homopolymer':
            pat = 'AAAAAAAAAAGGGGGGGGGGCCCCCCCCCCTTTTTTTTTT'
        elif kind == 'repeat':
            pat = 'CAGCAGCAGCAG'
        else:
            continue
        # phase the pattern on absolute coordinate so it is position-deterministic
        block = _tile(pat, (b - z0) + len(pat))
        for p in range(a, b):
            s[p - start] = block[(p - z0) % len(block)]
    return ''.join(s)


def genome(chrom, start, end):
    """The reference base sequence for [start, end) -- the single source of truth for tests."""
    start, end = int(start), int(end)
    if end <= start:
        return ''
    seq = _apply_zones(chrom, start, end, plain(chrom, start, end))
    # duplications last, so a copied block carries its source's engineered content verbatim
    for d in DUPES.get(chrom, []):
        ds, de = d['dest']
        a, b = max(start, ds), min(end, de)
        if a >= b:
            continue
        ss = d['src'][0] + (a - ds)
        src = _apply_zones(chrom, ss, ss + (b - a), plain(chrom, ss, ss + (b - a)))
        seq = seq[:a - start] + src + seq[b - start:]
    return seq


# ---------------------------------------------------------------- playwright routes

def install_routes(ctx, calls=None, fail_hosts=()):
    """Point the page's genome lookups at `genome()`. calls: optional list to record requests."""
    import json
    import re
    from urllib.parse import unquote

    def rec(tag, url):
        if calls is not None:
            calls.append((tag, url))

    def ucsc(route):
        u = unquote(route.request.url)
        if 'ucsc' in fail_hosts:
            return route.fulfill(status=503, headers={'Access-Control-Allow-Origin': '*'}, body='down')
        q = dict(x.split('=', 1) for x in u.split('?', 1)[1].split(';'))
        s, e = int(q['start']), int(q['end'])
        rec('ucsc', f"{q['chrom']}:{s}-{e}")
        route.fulfill(status=200, headers={'Access-Control-Allow-Origin': '*'},
                      content_type='application/json',
                      body=json.dumps({'dna': genome(q['chrom'], s, e)}))

    def ensembl(route):
        u = unquote(route.request.url)
        if 'ensembl' in fail_hosts:
            return route.fulfill(status=503, headers={'Access-Control-Allow-Origin': '*'}, body='down')
        m = re.search(r'/sequence/region/human/([^:]+):(\d+)-(\d+)', u)
        if m:
            # Ensembl: 1-based fully closed
            s1, e1 = int(m.group(2)), int(m.group(3))
            rec('ensembl', f"chr{m.group(1)}:{s1}-{e1}")
            return route.fulfill(status=200, headers={'Access-Control-Allow-Origin': '*'},
                                 content_type='text/plain',
                                 body=genome('chr' + m.group(1), s1 - 1, e1))
        rec('ensembl-other', u)
        route.fulfill(status=200, headers={'Access-Control-Allow-Origin': '*'},
                      content_type='application/json', body='[]')

    ctx.route('https://api.genome.ucsc.edu/**', ucsc)
    ctx.route('https://rest.ensembl.org/**', ensembl)


RC = str.maketrans('ACGT', 'TGCA')


def rc(s):
    return s.translate(RC)[::-1]


def find_all(hay, needle):
    out, i = [], hay.find(needle)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out
