// Loads an AFLA report in a simulated browser (jsdom) and exercises the filters.
// docker run --rm -v "$PWD":/w -w /w node:22-alpine sh -c "npm i -s jsdom@24 >/dev/null 2>&1 && node tests/report_smoke.js <report.html> GENE1,GENE2"
const {JSDOM} = require('jsdom');
const fs = require('fs');
const [file, genes = ''] = process.argv.slice(2);
const errors = [];
const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {runScripts: 'dangerously', pretendToBeVisual: true});
dom.window.addEventListener('error', e => errors.push(e.message));
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
const d = dom.window.document;
setTimeout(() => {
  const count = () => d.getElementById('count').textContent;
  const click = sel => d.querySelector(sel).click();
  console.log('title:', d.getElementById('title').textContent);
  console.log('default filters:', count());
  click('[data-preset="all"]'); console.log('all:', count());
  click('[data-preset="clinvar"]'); console.log('ClinVar P/LP:', count());
  click('[data-preset="all"]');
  const g = d.getElementById('fGenes'); g.value = genes; g.dispatchEvent(new dom.window.Event('input'));
  console.log(`genes ${genes}:`, count());
  const som = d.getElementById('fSom');
  if (!d.getElementById('somBox').hidden) { som.checked = true; som.dispatchEvent(new dom.window.Event('input')); console.log('  + somatic candidates only:', count()); }
  click('th[data-k="vaf"]');
  const row = d.querySelector('#body tr[data-i]');
  if (row) { row.click(); console.log('detail:', d.querySelector('#detail h2').textContent); }
  console.log('columns:', [...d.querySelectorAll('#head th')].map(t => t.textContent).join(' | '));
  console.log('QC tiles:', d.querySelectorAll('.tile').length);
  console.log('errors:', errors.length ? errors : 'none');
}, 200);
