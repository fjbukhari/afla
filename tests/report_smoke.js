// Loads an AFLA report in a simulated browser (jsdom) and clicks through it: tabs, presets, filters, the variant
// detail card with the ACMG panel, report selection, exercise mode and the printable case report.
//   npm i jsdom@24   (once)      then:   node tests/report_smoke.js <report.html> [GENE1,GENE2]
// or with Docker:  docker run --rm -v "$PWD":/w -w /w node:22-alpine sh -c "npm i -s jsdom@24 >/dev/null 2>&1 && node tests/report_smoke.js <report.html>"
const {JSDOM} = require('jsdom');
const fs = require('fs');
const [file, genes = ''] = process.argv.slice(2);
const errors = [];
const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/'});
dom.window.addEventListener('error', e => errors.push(e.message));
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
const d = dom.window.document;
const fail = [];
const check = (ok, what) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`); if (!ok) fail.push(what); };
setTimeout(() => {
  const count = () => d.getElementById('count').textContent;
  const fire = (el, ev = 'input') => el.dispatchEvent(new dom.window.Event(ev, {bubbles: true}));
  console.log('title:', d.getElementById('title').textContent);
  const tabs = [...d.querySelectorAll('#tabs button')].filter(b => !b.hidden).map(b => b.textContent);
  console.log('tabs:', tabs.join(' | '));
  console.log('default view:', count());
  const presets = [...d.querySelectorAll('[data-preset]')];
  presets.forEach(b => { b.click(); console.log(`preset "${b.textContent}":`, count()); });
  check(errors.length === 0, 'presets run without script errors');
  if (genes) {
    presets[presets.length - 1].click();
    const g = d.getElementById('fGenes'); g.value = genes; fire(g);
    console.log(`genes ${genes}:`, count());
  }
  presets[presets.length - 1].click();
  d.querySelector('th[data-k="gene"]').click();
  const row = d.querySelector('#body tr[data-i]');
  check(!!row, 'variant table has rows');
  if (row) {
    row.click();
    check(!d.getElementById('detail').hidden, 'detail card opens');
    console.log('detail:', d.querySelector('#detail h2').textContent.trim());
    const crit = d.querySelector('#detail [data-crit="PM2"]');
    if (crit) {
      const before = d.querySelector('#detail .cls').textContent;
      crit.checked = !crit.checked; fire(crit, 'change');
      const after = d.querySelector('#detail .cls').textContent;
      console.log(`ACMG toggle PM2: ${before} -> ${after}`);
      check(d.querySelectorAll('#detail [data-crit]').length === 26, 'ACMG panel lists 26 criteria');
    }
    const tier = d.querySelector('#detail h3');
    console.log('interpretation section:', tier ? tier.textContent : 'none');
    d.getElementById('dStar').click();
  }
  const ex = d.getElementById('exercise'); ex.checked = true; fire(ex, 'change');
  console.log('exercise mode columns:', [...d.querySelectorAll('#head th')].map(t => t.textContent).join(' | '));
  check(![...d.querySelectorAll('#head th')].some(t => t.textContent === 'ClinVar'), 'exercise mode hides ClinVar');
  ex.checked = false; fire(ex, 'change');
  d.querySelector('#tabs [data-tab="report"]').click();
  const rep = d.getElementById('rep');
  console.log('case report rows:', rep.querySelectorAll('tbody tr').length, '| sections:', [...rep.querySelectorAll('h2')].map(h => h.textContent).join(', '));
  check(rep.querySelectorAll('tbody tr').length >= 1, 'selected variant appears in the case report');
  for (const t of ['quality', 'cnv', 'sv', 'methods']) {
    const b = d.querySelector(`#tabs [data-tab="${t}"]`); if (b && !b.hidden) b.click();
  }
  console.log('QC tiles:', d.querySelectorAll('#tiles .tile').length, '| CNV tables:', d.querySelectorAll('#cnvBody table').length, '| SV rows:', d.querySelectorAll('#svBody tbody tr').length);
  check(errors.length === 0, 'no script errors' + (errors.length ? ': ' + errors.join('; ') : ''));
  process.exit(fail.length ? 1 : 0);
}, 300);
