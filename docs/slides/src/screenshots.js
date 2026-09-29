const {chromium} = require('playwright-core');
(async () => {
  const b = await chromium.launch({executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'});
  const p = await b.newPage({viewport: {width: 1400, height: 860}, deviceScaleFactor: 1.5, colorScheme: 'light'});
  const shot = async (n, opts = {}) => { await p.waitForTimeout(400); await p.screenshot({path: `/opt/shots/${n}.png`, ...opts}); };
  // germline trio
  await p.goto('file:///opt/runs/trio/out_demo/afla-report.html');
  await shot('g_variants');
  await p.click('#tabs [data-tab="quality"]'); await shot('g_quality', {fullPage: false});
  await p.click('#tabs [data-tab="cnv"]'); await shot('g_cnv');
  await p.click('#tabs [data-tab="variants"]');
  await p.click('[data-preset="1"]');
  await p.click('#body tr[data-i="0"] td:nth-child(2)');
  await p.waitForTimeout(300);
  const d = await p.$('#detail'); await d.scrollIntoViewIfNeeded(); await shot('g_detail');
  await p.evaluate(() => document.querySelector('#detail .acmg').scrollIntoView()); await shot('g_acmg');
  await p.click('#dStar');
  await p.click('#tabs [data-tab="report"]'); await shot('g_report');
  await p.click('#tabs [data-tab="variants"]');
  await p.check('#exercise'); await p.evaluate(() => window.scrollTo(0, 0)); await shot('g_exercise');
  await p.click('#tabs [data-tab="sv"]'); await shot('g_sv');
  // somatic
  await p.goto('file:///opt/runs/som/somatic_report.html');
  await p.click('#tabs [data-tab="quality"]'); await shot('s_quality');
  await p.click('#tabs [data-tab="variants"]'); await p.click('[data-preset="1"]'); await shot('s_variants');
  await p.click('#body tr[data-i="0"] td:nth-child(2)'); await p.evaluate(() => document.querySelector('#detail').scrollIntoView()); await shot('s_detail');
  await b.close();
})();
