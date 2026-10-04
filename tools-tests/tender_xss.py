"""Feed the tender dashboard hostile tender data and see what it does with it.

Tender titles, organisations, references and URLs come from scraped government portals and
from the office PC. None of that is under our control, so the dashboard has to treat all of
it as untrusted. This serves a crafted feed and checks that nothing executes, no markup is
injected, and no script URL reaches a link.
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8900/catalogue/staff/tenders/tenders.html'
GATE = 'http://127.0.0.1:8900/catalogue/staff/api/gate-sso.php'

PAYLOADS = {
    'img_onerror': '<img src=x onerror="window.__xss=1">',
    'script_tag': '<script>window.__xss=1</script>',
    'svg_onload': '<svg onload="window.__xss=1">',
    'quote_break': '"><img src=x onerror="window.__xss=1">',
    'attr_break': "' onmouseover='window.__xss=1",
    'entity': '&lt;img src=x onerror=window.__xss=1&gt;',
}


def build_feed():
    tenders = []
    for i, (name, payload) in enumerate(PAYLOADS.items()):
        tenders.append({
            'id': f't{i}', 'source': 'evil', 'source_name': payload, 'region': payload,
            'ref': payload, 'title': payload, 'org': payload, 'location': payload,
            'institute': payload, 'city': payload, 'type': payload,
            'published': '2026-10-01', 'closing': '2026-12-01',
            'url': 'javascript:window.__xssurl=1',
            'doc_url': 'javascript:window.__xssdoc=1',
            'score': 5, 'has_sm': True, 'relevant': True, 'core': True,
            'categories': [payload], 'matched': [payload], 'excluded': [payload],
            'first_seen': '2026-10-01', 'dup_of': None,
            'items': [payload, 'Taq polymerase 500U'],
        })
    # one ordinary tender, so we can tell rendering still works
    tenders.append({
        'id': 'tok', 'source': 'ppra-fed', 'source_name': 'PPRA Federal', 'region': 'Federal',
        'ref': 'TE-2026-001', 'title': 'Supply of PCR reagents and consumables',
        'org': 'National Institute of Health', 'location': 'Islamabad',
        'institute': 'National Institute of Health', 'city': 'Islamabad', 'type': 'Goods',
        'published': '2026-10-01', 'closing': '2026-12-01', 'url': 'https://example.gov.pk/t/1',
        'doc_url': 'https://example.gov.pk/t/1.pdf', 'score': 9, 'has_sm': True,
        'relevant': True, 'core': True, 'categories': ['PCR'], 'matched': ['pcr'],
        'excluded': [], 'first_seen': '2026-10-01', 'dup_of': None, 'items': [],
    })
    return {
        'generated': '2026-10-04 10:00:00', 'threshold': 3,
        'categories': {'PCR': True, PAYLOADS['img_onerror']: False},
        'team': [{'name': PAYLOADS['img_onerror'], 'email': 'x@jb-scientific.com'}],
        'sources': [
            {'id': 'evil', 'name': PAYLOADS['script_tag'], 'region': PAYLOADS['svg_onload'],
             'url': 'javascript:window.__xsssrc=1', 'login': False, 'enabled': True,
             'group': 'Read by the website', 'status': 'error', 'error': PAYLOADS['img_onerror'],
             'rows': 0, 'relevant': 0, 'last_run': '2026-10-04 09:00', 'last_ok': ''},
            {'id': 'ppra-fed', 'name': 'PPRA Federal', 'region': 'Federal',
             'url': 'https://example.gov.pk', 'login': False, 'enabled': True,
             'group': 'Read by the website', 'status': 'ok', 'error': '', 'rows': 12,
             'relevant': 3, 'last_run': '2026-10-04 09:00', 'last_ok': '2026-10-04 09:00'},
        ],
        'tenders': tenders, 'notes': {}, 'catalogue_url': '/catalogue/jbs-catalog.html',
        'live': True, 'can_email': True,
    }


def main():
    out = {'issues': [], 'errors': [], 'observed': {}}
    feed = build_feed()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
        ctx = b.new_context(viewport={'width': 1400, 'height': 1000})
        ctx.request.get(GATE)
        ctx.route('**/api.php**', lambda r: r.fulfill(
            status=200, content_type='application/json', body=json.dumps(feed)))
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: out['errors'].append(str(e)[:300]))
        pg.on('dialog', lambda d: (out['issues'].append({'issue': 'a dialog opened: ' + d.message[:120]}), d.accept()))
        pg.goto(BASE, timeout=120000)
        pg.wait_for_timeout(3000)
        pg.evaluate("document.querySelectorAll('script').forEach(s=>s.setAttribute('data-own','1'))")

        # switch to table view too, so both renderers are exercised
        for view in ('cards', 'table'):
            try:
                pg.evaluate("(v)=>{ if(typeof setView==='function') setView(v); }", view)
            except Exception:
                pass
            pg.wait_for_timeout(600)

            flags = pg.evaluate("""()=>({xss:!!window.__xss, url:!!window.__xssurl,
                doc:!!window.__xssdoc, src:!!window.__xsssrc})""")
            for k, v in flags.items():
                if v:
                    out['issues'].append({'issue': f'script executed ({k}) in {view} view'})

            # any element the payloads would have created?
            # only elements the payloads would have created; the page's own scripts are
            # marked beforehand so they are not miscounted as injected
            injected = pg.evaluate("""()=>{
                const bad=[...document.querySelectorAll('img[src="x"], svg[onload], script:not([data-own])')]
                  .filter(e=>!e.src || !e.src.startsWith('http'));
                return bad.length;}""")
            if injected:
                out['issues'].append({'issue': f'{injected} injected element(s) in {view} view'})

            # any link whose href is not http(s)?
            bad_links = pg.evaluate("""()=>[...document.querySelectorAll('a[href]')]
                .map(a=>a.getAttribute('href'))
                .filter(h=>h && !/^(https?:|#|\\/|mailto:)/i.test(h));""")
            if bad_links:
                out['issues'].append({'issue': f'{view} view: links with an unsafe scheme',
                                      'examples': bad_links[:4]})
            out['observed'][view] = {
                'rows_rendered': pg.evaluate("document.querySelectorAll('[data-id]').length"),
                'bad_links': bad_links[:4],
            }

        # the ordinary tender must still render properly
        txt = pg.evaluate("document.body.innerText")
        if 'Supply of PCR reagents' not in txt:
            out['issues'].append({'issue': 'the ordinary tender did not render'})
        # the payload should be visible as literal text, not interpreted
        if '<img src=x' not in txt and '&lt;img' not in txt:
            out['issues'].append({'issue': 'payload text not shown literally (may have been stripped or executed)'})
        ctx.close()
        b.close()
    print(json.dumps(out, indent=1))
    return 1 if out['issues'] else 0


if __name__ == '__main__':
    sys.exit(main())
