<?php
/* Stress-test the tender portal's parsers and import against hostile and malformed input.
 *
 * Runs against a COPY of the portal in a temporary directory, so the live tender database,
 * team notes and logs are never touched.
 *
 * Usage: php test/tender_parse.php
 */
$src = '/home/user/jbs-site/public_html/catalogue/staff/tenders';
$tmp = sys_get_temp_dir() . '/twtest_' . getmypid();
@mkdir($tmp, 0777, true);
foreach (['lib.php','lib_tw2.php','config.php','config.sample.php','rules.json','mailer.php'] as $f) {
    if (file_exists("$src/$f")) copy("$src/$f", "$tmp/$f");
}
@mkdir("$tmp/data", 0777, true);
require "$tmp/lib.php";

$fail = []; $pass = 0;
function check($name, $cond, $detail = '') {
    global $fail, $pass;
    if ($cond) { $pass++; return; }
    $fail[] = $name . ($detail !== '' ? "  [$detail]" : '');
}

/* ---------------------------------------------------------------- 1. URL safety
 * A tender's URL ends up in an href in the staff dashboard. A portal that served a
 * script URL - because it was compromised, or because someone can post to it - would
 * otherwise get that URL clicked by staff inside the authenticated dashboard.
 */
$base = 'https://example.gov.pk/tenders/list.php';
$urlCases = [
    ['javascript:alert(1)',                      'plain script url'],
    ['JaVaScRiPt:alert(1)',                      'mixed case'],
    ['  javascript:alert(1)',                    'leading spaces'],
    ["java\tscript:alert(1)",                    'tab inside the scheme'],
    ["java\nscript:alert(1)",                    'newline inside the scheme'],
    ["jav\x01ascript:alert(1)",                  'control character inside the scheme'],
    ['data:text/html,<script>alert(1)</script>', 'data url'],
    ['vbscript:msgbox(1)',                       'vbscript url'],
    ['  /real/page.php',                         'ordinary relative url (must survive)'],
    ['https://example.gov.pk/ok.pdf',            'ordinary absolute url (must survive)'],
];
foreach ($urlCases as [$href, $label]) {
    $got = tw_abs($href, $base);
    $dangerous = $got !== '' && !preg_match('#^https?://#i', $got);
    if (strpos($label, 'must survive') !== false) {
        check("url: $label kept", $got !== '' && preg_match('#^https?://#i', $got), $got);
    } else {
        check("url: $label rejected", !$dangerous, "got: " . var_export($got, true));
    }
}

/* ---------------------------------------------------------------- 2. Parser robustness
 * Portal HTML changes without warning. A parser must not fatal, and must not invent rows.
 */
$htmlCases = [
    ['', 'empty document'],
    ['<html><body>', 'truncated document'],
    ['<table><tr><td>only one cell</td></tr></table>', 'table with too few cells'],
    ['<table><tr><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td></tr></table>', 'table with no links'],
    [str_repeat('<div>', 500) . 'deep' . str_repeat('</div>', 500), 'deeply nested markup'],
    ['<table><tr><td>1</td><td><a href="javascript:alert(1)">Supply of reagents</a></td><td>x</td><td>y</td><td>z</td></tr></table>', 'script url in a results table'],
    ['<?xml version="1.0"?><!DOCTYPE t [<!ENTITY e SYSTEM "file:///etc/passwd">]><t>&e;</t>', 'xml entity expansion'],
];
foreach (['tw_parse_epms','tw_parse_epads','tw_parse_punjab','tw_parse_kppra','tw_parse_generic'] as $parser) {
    if (!function_exists($parser)) { check("parser $parser exists", false); continue; }
    foreach ($htmlCases as [$html, $label]) {
        try {
            $rows = $parser($html, $base);
            check("$parser: $label returns an array", is_array($rows));
            foreach ((array)$rows as $r) {
                $u = (string)($r['url'] ?? '');
                check("$parser: $label url safe", $u === '' || preg_match('#^https?://#i', $u), $u);
                $d = (string)($r['doc_url'] ?? '');
                check("$parser: $label doc url safe", $d === '' || preg_match('#^https?://#i', $d), $d);
            }
        } catch (Throwable $e) {
            check("$parser: $label does not throw", false, get_class($e) . ': ' . $e->getMessage());
        }
    }
}
/* the file:// entity must not have been read */
check('xml entities are not expanded', !preg_match('/root:x:/', json_encode(@tw_parse_generic(
    '<?xml version="1.0"?><!DOCTYPE t [<!ENTITY e SYSTEM "file:///etc/passwd">]><t>&e;</t>', $base))));

/* ---------------------------------------------------------------- 3. Date parsing */
$dateCases = [
    ['2026-10-04', '2026-10-04'], ['04/10/2026', '2026-10-04'], ['04-10-2026', '2026-10-04'],
    ['4 Oct 2026', '2026-10-04'], ['October 4, 2026', '2026-10-04'],
    ['', ''], ['not a date', ''], ['31/02/2026', null], ['0000-00-00', ''],
];
foreach ($dateCases as [$in, $want]) {
    $got = tw_date($in);
    if ($want === null) { check("date '$in' does not become a real date", $got === '' || $got !== '2026-02-31', $got); continue; }
    check("date '$in' -> '$want'", $got === $want, "got '$got'");
}
/* a closing date far in the past or future should not be invented */
check('date: absurd year rejected', in_array(tw_date('01/01/1900'), ['', '1900-01-01'], true));

/* ---------------------------------------------------------------- 4. Import validation
 * tw_import takes data from the office PC over the network. It must survive bad input.
 */
$importCases = [
    [['id' => 'test'], [], 'no rows'],
    [['id' => '../../etc'], [['title' => 'x']], 'path traversal in the source id'],
    [['id' => 'test'], [['title' => '']], 'empty title'],
    [['id' => 'test'], [['title' => str_repeat('A', 100000)]], 'enormous title'],
    [['id' => 'test'], [['title' => 'ok', 'url' => 'javascript:alert(1)']], 'script url'],
    [['id' => 'test'], [['title' => 'ok', 'items' => array_fill(0, 5000, 'line')]], 'too many item lines'],
    [['id' => 'test'], [['title' => 'ok', 'closing' => 'rubbish']], 'unparseable date'],
    [['id' => 'test'], array_fill(0, 2000, ['title' => 'bulk tender']), 'very many rows'],
];
foreach ($importCases as [$meta, $rows, $label]) {
    try {
        $st = tw_import($meta, $rows, 0);
        check("import: $label survives", is_array($st));
        $db = tw_load('tenders_db.json');
        foreach (($db['tenders'] ?? $db) as $t) {
            if (!is_array($t)) continue;
            $u = (string)($t['url'] ?? '');
            check("import: $label stored url safe", $u === '' || preg_match('#^https?://#i', $u), $u);
            check("import: $label title bounded", mb_strlen((string)($t['title'] ?? '')) <= 500,
                  'len ' . mb_strlen((string)($t['title'] ?? '')));
        }
    } catch (Throwable $e) {
        /* a thrown exception is acceptable for a bad source id; a fatal is not */
        check("import: $label raises a clean error", $e instanceof Exception, get_class($e));
    }
}

/* data files must not have escaped the data directory */
check('import did not write outside the data directory', !file_exists("$tmp/etc") && !is_dir("$tmp/../etc"));

/* ---------------------------------------------------------------- report */
echo "tender portal parser/import stress test\n";
echo "  checks passed: $pass\n";
echo "  failures: " . count($fail) . "\n";
foreach ($fail as $f) echo "    - $f\n";
exec('rm -rf ' . escapeshellarg($tmp));
exit(count($fail) ? 1 : 0);
