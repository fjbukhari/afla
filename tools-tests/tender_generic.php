<?php
/*
 * The website's generic portal reader: the faults found with the pages captured on the office
 * PC, 5 Oct 2026.
 *
 * On the live dashboard the KP health department read as 0 tenders. Its page puts a <style>
 * block inside a table row, so the one "tender" the reader found was a block of CSS - and
 * because that counted as a result, the link pass below it never ran and the 400 genuine
 * notices on the page were never seen. BPPRA's front page gave the opposite problem: the link
 * pass turned its office address and a software vendor's URL into tenders.
 *
 * Run:  php tender_generic.php /path/to/catalogue/staff/tenders
 */
$dir = $argv[1] ?? dirname(__DIR__) . '/catalogue/staff/tenders';
if (!file_exists("$dir/lib.php")) { fwrite(STDERR, "lib.php not found in $dir\n"); exit(2); }
if (!file_exists("$dir/config.php") && !file_exists("$dir/config.sample.php")) {
    file_put_contents("$dir/config.php", "<?php return ['timezone'=>'Asia/Karachi','http'=>['delay_ms'=>0]];");
}
require_once "$dir/lib.php";

$pass = 0; $fail = 0;
function check($name, $ok, $detail = '') {
    global $pass, $fail;
    if ($ok) { $pass++; printf("  ok    %s\n", $name); }
    else { $fail++; printf("  FAIL  %s   %s\n", $name, $detail); }
}

/* ---------- a tenders page that is a list of links, with a <style> block in a table ---------- */
$rows = '';
for ($i = 0; $i < 8; $i++) {
    $n = 1257 - $i;
    $rows .= "<li><a href='/news/view/$n'>INVITATION FOR BIDS FOR THE PROCUREMENT OF LABORATORY "
           . "REAGENTS AND CONSUMABLES, BATCH $n</a>"
           . "<a href='/public/uploads/news-$n.pdf'>Attachment : Download</a></li>";
}
$kp = "<html><body><table><tr><td><style>/* ---- */ #newlist ol{margin:0;padding:0;list-style:none}"
    . ".newsitem a{color:#036}</style></td><td>Tenders and procurement notices</td></tr></table>"
    . "<ul>$rows</ul></body></html>";

$items = tw_parse_generic($kp, 'https://www.healthkp.gov.pk/news/tenders');
check('a stylesheet is not read as a tender',
      !array_filter($items, fn($i) => str_contains($i['title'], 'padding') || str_contains($i['title'], '#newlist')),
      $items ? substr($items[0]['title'], 0, 60) : '(none)');
check('the notices behind it are found', count($items) >= 8, count($items) . ' items');
check('their titles are the notices', str_contains($items[0]['title'] ?? '', 'LABORATORY REAGENTS'),
      $items[0]['title'] ?? '(none)');

/* ---------- a portal front page whose stray links are not tenders ---------- */
$front = "<html><body>"
    . "<div><a href='https://www.google.com/maps/place/Balochistan+Public+Procurement'>"
    . "House # 2 Arbab Town Joint Road, Quetta-Pakistan</a> Tenders e-PPs</div>"
    . "<div><a href='http://www.devexpress.com/purchase'>www.devexpress.com/purchase - to "
    . "purchase a licence for these tender grids</a></div>"
    . "<div><a href='https://bppra.gob.pk'>2026 Balochistan Public Procurement Regulatory "
    . "Authority - tenders and notices</a></div></body></html>";
check('a stray link on a front page is not a tender',
      tw_parse_generic($front, 'https://www.bppra.gob.pk/') === [],
      json_encode(array_column(tw_parse_generic($front, 'https://www.bppra.gob.pk/'), 'title')));

/* ---------- a small institution publishing two PDF notices ---------- */
$pdfs = "<html><body><ul>"
    . "<li><a href='/docs/tender-reagents.pdf'>Tender notice: supply of laboratory reagents</a></li>"
    . "<li><a href='/docs/tender-glass.pdf'>Tender notice: supply of laboratory glassware</a></li>"
    . "</ul></body></html>";
$two = tw_parse_generic($pdfs, 'https://uhs.edu.pk/');
check('two PDF notices still count', count($two) === 2, count($two) . ' items');
check('the PDF is kept as the document', ($two[0]['doc_url'] ?? '') !== '', json_encode($two[0] ?? []));

/* ---------- an ordinary table still reads as before ---------- */
$table = "<html><body><table>"
    . "<tr><th>S.No</th><th>Tender</th><th>Agency</th><th>Closing</th></tr>"
    . "<tr><td>1</td><td>Supply of ELISA kits and controls</td><td>Services Hospital</td><td>14-10-2026</td></tr>"
    . "<tr><td>2</td><td>Annual maintenance of PCR thermal cyclers</td><td>Services Hospital</td><td>21-10-2026</td></tr>"
    . "<tr><td>3</td><td>Supply of laboratory glassware</td><td>Services Hospital</td><td>28-10-2026</td></tr>"
    . "</table></body></html>";
$t = tw_parse_generic($table, 'https://example.test/');
check('an ordinary table is unaffected', count($t) === 3, count($t) . ' items');
check('its dates are read', ($t[0]['closing'] ?? '') === '2026-10-14', $t[0]['closing'] ?? '(none)');

/* ---------- a repeated field label is stripped ---------- */
$undp = '';
for ($i = 1; $i <= 4; $i++) {
    $undp .= "<div><a href='/view_negotiation.cfm?nego_id=503$i'>Title Procurement of laboratory "
           . "equipment for lot $i Ref No UNDP-PAK-0080$i</a></div>";
}
$u = tw_parse_generic("<html><body>$undp</body></html>", 'https://procurement-notices.undp.org/');
check('a repeated "Title" label is stripped',
      str_starts_with($u[0]['title'] ?? '', 'Procurement of laboratory'), $u[0]['title'] ?? '(none)');

/* ---------- an archive is capped ---------- */
$many = '';
for ($i = 0; $i < 200; $i++) {
    $many .= "<li><a href='/news/view/" . (2000 - $i) . "'>INVITATION FOR BIDS FOR THE PROCUREMENT "
           . "OF MEDICAL EQUIPMENT, NOTICE " . (2000 - $i) . "</a></li>";
}
$cap = tw_parse_generic("<html><body><ul>$many</ul></body></html>", 'https://www.healthkp.gov.pk/news/tenders');
check('an undated archive is capped, newest first',
      count($cap) === TW_LINKLIST_MAX && str_contains($cap[0]['title'], '2000'),
      count($cap) . ' items, first: ' . ($cap[0]['title'] ?? ''));

printf("\n%d passed, %d failed\n", $pass, $fail);
exit($fail ? 1 : 0);
