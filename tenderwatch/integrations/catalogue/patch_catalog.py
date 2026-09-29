"""Adds the Tender Watch link to jbs-catalog.html (Match Customer List tab). Run: python patch_catalog.py in out"""
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
assert "tenderPanel" not in s, "already patched"

CSS = """
  /* ---- Tender Watch link (Match tab, staff view) ---- */
  .match-upload-box{display:block;} /* the <label> was inline, which squashed the dashed upload box */
  .tender-panel{max-width:900px; margin:0 auto 16px; text-align:left; background:var(--paper-2); border:1px solid var(--line); border-radius:10px; padding:14px 18px;}
  .tender-panel h3{margin:0 0 4px; font-size:15px; color:var(--ink);}
  .tender-panel p{margin:0 0 10px; font-size:12.5px; color:var(--slate);}
  .tender-controls{display:flex; flex-wrap:wrap; gap:8px; align-items:center;}
  .tender-controls input[type=search]{flex:1 1 220px; min-width:0; padding:8px 10px; border:1px solid var(--line); border-radius:7px; font:inherit; font-size:13px;}
  .tender-controls select{padding:7px 8px; border:1px solid var(--line); border-radius:7px; font:inherit; font-size:12.5px; background:#fff;}
  .tender-controls label{font-size:12.5px; color:var(--slate); display:flex; gap:6px; align-items:center;}
  .tender-status{font-size:12.5px; color:var(--slate); margin-top:8px;}
  .tender-list{padding:0 24px 40px; max-width:900px; margin:0 auto; display:flex; flex-direction:column; gap:14px;}
  .tender-card .rfq-item-header{flex-wrap:wrap;}
  .tender-card .t-title{font-weight:600; font-size:14px; color:var(--ink); text-decoration:none;}
  .tender-card .t-title:hover{text-decoration:underline;}
  .tender-meta{font-size:12px; color:var(--slate); margin:-4px 0 10px; display:flex; flex-wrap:wrap; gap:4px 14px;}
  .tender-meta b{color:var(--ink); font-weight:600;}
  .t-badge{font-family:'IBM Plex Mono'; font-size:10.5px; font-weight:700; border-radius:999px; padding:2px 9px; background:var(--line-2); color:var(--teal-dark); white-space:nowrap;}
  .t-badge.soon{background:var(--red-bg); color:var(--red);}
  .t-line{font-size:12px; color:var(--ink); font-weight:600; margin:8px 0 4px;}
  .t-miss{font-size:12px; color:var(--slate); margin-top:8px;}
  .t-miss summary{cursor:pointer;}
"""
s = s.replace("</style>", CSS + "</style>", 1)

HTML = """<div class="tender-panel" id="tenderPanel" style="display:none;">
      <h3>Open tenders from Tender Watch</h3>
      <p>Matches each open tender's item list (or its title when no item list could be read) against the catalogue. Suggested matches are keyword-based; check the tender document before quoting.</p>
      <div class="tender-controls">
        <button type="button" class="match-paste-btn" id="tenderLoadBtn">Match open tenders</button>
        <input type="search" id="tenderSearch" placeholder="Filter tenders: e.g. ELISA, Karachi, NIH" aria-label="Filter tenders">
        <select id="tenderMin" aria-label="Minimum relevance">
          <option value="0.5">Relevance 50% or more</option>
          <option value="0.7">Relevance 70% or more</option>
          <option value="0.3">Relevance 30% or more</option>
        </select>
        <select id="tenderSort" aria-label="Sort tenders">
          <option value="match">Most matched items first</option>
          <option value="closing">Closing soonest</option>
        </select>
        <label><input type="checkbox" id="tenderOnlyMatched" checked> Only tenders with matches</label>
        <button class="clear-btn" id="tenderExportBtn" type="button" style="display:none;">Export (Excel)</button>
      </div>
      <div class="tender-status" id="tenderStatus"></div>
    </div>
    <label class="match-upload-box" id="matchUploadBox">"""
s = s.replace('<label class="match-upload-box" id="matchUploadBox">', HTML, 1)
s = s.replace('<div class="rfq-list" id="rfqList" style="display:none;"></div>',
              '<div class="rfq-list" id="rfqList" style="display:none;"></div>\n  <div class="tender-list" id="tenderList"></div>', 1)

JS = r"""
// ---------- Tender Watch link (staff view) ----------
// Tender Watch (runs on the office PC) publishes open tenders with the item lists it read from
// their documents: as tender-feed.json next to this page, and live at http://localhost:8765/api/tenders
// while its dashboard is running. Each item is matched with the same matchCustomerItem() as uploads.
const tenderPanel = document.getElementById('tenderPanel');
const tenderList = document.getElementById('tenderList');
const tenderStatus = document.getElementById('tenderStatus');
const tenderSearch = document.getElementById('tenderSearch');
const tenderMin = document.getElementById('tenderMin');
const tenderSort = document.getElementById('tenderSort');
const tenderOnlyMatched = document.getElementById('tenderOnlyMatched');
const tenderExportBtn = document.getElementById('tenderExportBtn');
const TENDER_FEEDS = ['tender-feed.json', 'http://localhost:8765/api/tenders'];
let TENDERS = null, TENDER_ONLY = null;
const lineCache = new Map();
if (PRICES_VISIBLE) tenderPanel.style.display = 'block';

async function loadTenderFeed(){
  for (const url of TENDER_FEEDS){
    try {
      const r = await fetch(url + (url.includes('?') ? '&' : '?') + 'v=' + Date.now(), {cache: 'no-store'});
      if (!r.ok) continue;
      const j = await r.json();
      if (j && Array.isArray(j.tenders)) return { feed: j, from: url.startsWith('http') ? 'Tender Watch on this PC' : 'tender-feed.json' };
    } catch(e){}
  }
  return null;
}
function tenderDaysLeft(t){
  if (!t.closing) return null;
  const d = new Date(t.closing + 'T00:00:00'), now = new Date(); now.setHours(0,0,0,0);
  return Math.round((d - now) / 864e5);
}
function matchLine(text){
  if (!lineCache.has(text)) lineCache.set(text, matchCustomerItem(text));
  return lineCache.get(text);
}
function bestPct(res){
  if (res.verified && res.verified.rows.length) return 1.01;
  return res.candidates.length ? res.candidates[0].pct : 0;
}
async function matchTenders(list){
  const out = [];
  for (let i = 0; i < list.length; i++){
    const t = list[i];
    const lines = (t.items && t.items.length ? t.items : [t.title]).slice(0, 80);
    t._lines = lines.map(text => ({ text, res: matchLine(text) }));
    t._fromItems = !!(t.items && t.items.length);
    out.push(t);
    if (i % 5 === 4){
      tenderStatus.textContent = 'Matching tenders against the catalogue… ' + (i + 1) + ' of ' + list.length;
      await new Promise(r => setTimeout(r, 0)); // keep the page responsive
    }
  }
  return out;
}
function renderTenders(){
  if (!TENDERS) return;
  const min = parseFloat(tenderMin.value);
  const words = tenderSearch.value.toLowerCase().split(/\s+/).filter(Boolean);
  let rows = TENDERS.filter(t => !TENDER_ONLY || t.id === TENDER_ONLY).map(t => {
    const hits = t._lines.filter(l => bestPct(l.res) >= min);
    return { t, hits, misses: t._lines.filter(l => bestPct(l.res) < min) };
  }).filter(({t, hits}) => {
    if (tenderOnlyMatched.checked && !hits.length) return false;
    const hay = [t.title, t.institute, t.city, t.region, t.ref, t.source_name, ...(t.items || [])].join(' ').toLowerCase();
    return words.every(w => hay.includes(w));
  });
  rows.sort(tenderSort.value === 'closing'
    ? (a, b) => (a.t.closing || '9999').localeCompare(b.t.closing || '9999')
    : (a, b) => b.hits.length - a.hits.length || (a.t.closing || '9999').localeCompare(b.t.closing || '9999'));
  tenderStatus.textContent = rows.length + ' of ' + TENDERS.length + ' open tenders shown · ' +
    rows.reduce((s, r) => s + r.hits.length, 0) + ' tender items matched to catalogue products';
  tenderExportBtn.style.display = rows.length ? 'inline-block' : 'none';
  tenderExportBtn._rows = rows;
  tenderList.innerHTML = rows.slice(0, 150).map(({t, hits, misses}) => {
    const dl = tenderDaysLeft(t);
    const due = t.closing ? `<span class="t-badge${dl !== null && dl <= 7 ? ' soon' : ''}">closes ${escapeHtml(t.closing)}${dl !== null ? ' · ' + dl + ' day' + (dl === 1 ? '' : 's') : ''}</span>` : '';
    const lines = hits.map(l => {
      const v = l.res.verified && l.res.verified.rows.length;
      const matches = v
        ? l.res.verified.rows.map(({row}) => renderMatchLine(row, '<span class="rfq-relevance verified">Verified</span>')).join('')
        : l.res.candidates.slice(0, 3).map(c => renderMatchLine(c.row, `<span class="rfq-relevance suggested">${Math.round(c.pct * 100)}% relevance</span>`, 'suggested')).join('');
      return `<div class="t-line">${escapeHtml(l.text)}</div><ul class="rfq-matches">${matches}</ul>`;
    }).join('');
    const miss = misses.length ? `<details class="t-miss"><summary>${misses.length} item${misses.length === 1 ? '' : 's'} with no good catalogue match</summary><ul>${misses.map(l => '<li>' + escapeHtml(l.text) + '</li>').join('')}</ul></details>` : '';
    return `<div class="rfq-item tender-card">
      <div class="rfq-item-header">
        <a class="t-title" href="${escapeHtml(t.url || '#')}" target="_blank" rel="noopener">${escapeHtml(t.title)}</a> ${due}
      </div>
      <div class="tender-meta"><span><b>${escapeHtml(t.institute || '')}</b></span>${t.city ? '<span>' + escapeHtml(t.city) + '</span>' : ''}<span>${escapeHtml(t.source_name || '')}</span>${t.ref ? '<span>Ref ' + escapeHtml(t.ref) + '</span>' : ''}<span>${t._fromItems ? t._lines.length + ' items read from the tender document' : 'Matched on the tender title (no item list read yet)'}</span>${t.doc_url ? '<span><a href="' + escapeHtml(t.doc_url) + '" target="_blank" rel="noopener">Tender document</a></span>' : ''}</div>
      ${lines || '<div class="rfq-not-found">No catalogue match at this relevance.</div>'}
      ${miss}
    </div>`;
  }).join('') + (rows.length > 150 ? '<div class="tender-status">Showing the first 150; filter to narrow the list.</div>' : '');
}
async function runTenderMatch(onlyId){
  tenderStatus.textContent = 'Loading open tenders…';
  const got = await loadTenderFeed();
  if (!got){
    tenderStatus.textContent = 'No tender list found. Put tender-feed.json (written by Tender Watch) next to this page, or open this page on the PC where the Tender Watch dashboard is running.';
    return false;
  }
  buildCatalogIndex();
  TENDER_ONLY = onlyId || null;
  const list = got.feed.tenders.filter(t => !TENDER_ONLY || t.id === TENDER_ONLY);
  if (TENDER_ONLY && !list.length){ tenderStatus.textContent = 'That tender is not in the current tender list (it may have closed).'; return false; }
  TENDERS = await matchTenders(list);
  tenderStatus.dataset.from = got.from + (got.feed.generated ? ', updated ' + got.feed.generated : '');
  renderTenders();
  tenderStatus.textContent += ' · from ' + tenderStatus.dataset.from;
  return true;
}
document.getElementById('tenderLoadBtn').addEventListener('click', () => runTenderMatch(null));
[tenderSearch, tenderMin, tenderSort, tenderOnlyMatched].forEach(el => el.addEventListener(el === tenderSearch ? 'input' : 'change', renderTenders));
tenderExportBtn.addEventListener('click', () => {
  // Re-use the formatted Excel export: one row group per tender item.
  const min = parseFloat(tenderMin.value);
  matchResults = [];
  (tenderExportBtn._rows || []).forEach(({t, hits}) => hits.forEach(l => {
    matchResults.push({ orig: t.title + ' [' + (t.institute || '') + (t.closing ? ', closes ' + t.closing : '') + '] › ' + l.text,
                        verified: l.res.verified, candidates: l.res.candidates.filter(c => c.pct >= min).slice(0, 3),
                        origIndex: matchResults.length + 1 });
  }));
  matchSortSelect.value = 'original';
  matchExportExcelBtn.click();
});

// Deep links: ?tab=match (also workflow/takara), &q=<lines to match>, &tender=<Tender Watch id>
(function(){
  const qp = new URLSearchParams(location.search);
  const tab = qp.get('tab');
  const btn = {match: matchTabBtn, workflow: workflowTabBtn, takara: crossRefTabBtn, catalog: catalogTabBtn}[tab];
  if (btn) btn.click();
  if (tab !== 'match') return;
  const q = qp.get('q'), tid = qp.get('tender');
  const fallback = () => { if (q){ matchPasteInput.value = q; parsePastedText(q); } };
  if (tid && PRICES_VISIBLE){
    runTenderMatch(tid).then(ok => { if (!ok) fallback(); else tenderPanel.scrollIntoView(); });
  } else fallback();
})();
"""
marker = "// ---------- catalog filters/search (existing logic, extended) ----------"
assert marker in s
s = s.replace(marker, JS + "\n" + marker, 1)
open(dst, "w", encoding="utf-8").write(s)
print("patched ->", dst)
