<?php
/* Deduplication and relevance scoring.
 *
 * The expensive mistake here is a FALSE MERGE: two genuinely different tenders folded into one
 * hides a real opportunity, and nobody finds out. A missed merge only shows the same tender twice,
 * which is untidy but harmless. These cases are weighted accordingly.
 */
$src = '/home/user/jbs-site/public_html/catalogue/staff/tenders';
$tmp = sys_get_temp_dir() . '/twdedup_' . getmypid();
@mkdir("$tmp/data", 0777, true);
foreach (['lib.php','lib_tw2.php','config.php','config.sample.php','rules.json','mailer.php'] as $f) {
    if (file_exists("$src/$f")) copy("$src/$f", "$tmp/$f");
}
require "$tmp/lib.php";

$fail = []; $pass = 0;
function check($name, $cond, $detail = '') {
    global $fail, $pass;
    if ($cond) { $pass++; return; }
    $fail[] = $name . ($detail !== '' ? "  [$detail]" : '');
}

function mk($i, $src, $title, $closing, $org = '', $ref = '') {
    return ['id' => "t$i", 'source' => $src, 'source_name' => ucfirst($src), 'title' => $title,
            'closing' => $closing, 'org' => $org, 'ref' => $ref, 'relevant' => true,
            'url' => "https://$src.example/$i", 'score' => 5];
}

/* each case: [rows, [pairs that MUST be merged], [pairs that MUST NOT be merged], label] */
$cases = [
    [[mk(0,'ppra','Supply of PCR Reagents and Consumables','2026-12-01','NIH'),
      mk(1,'epads','Supply of PCR Reagents and Consumables','2026-12-01','NIH')],
     [[0,1]], [], 'same tender listed on two portals'],

    [[mk(0,'ppra','Supply of Laboratory Equipment Lot 1','2026-12-01','NIH','R-1'),
      mk(1,'ppra','Supply of Laboratory Equipment Lot 2','2026-12-01','NIH','R-2')],
     [], [[0,1]], 'two lots of one tender on the same portal stay separate'],

    [[mk(0,'ppra','Supply of ELISA Kits','2026-12-01','NIH'),
      mk(1,'epads','Supply of ELISA Kits','2027-03-15','NIH')],
     [], [[0,1]], 'same words but different closing dates'],

    [[mk(0,'ppra','Tender No 44/2026 Supply of Microscopes','2026-12-01','NIH'),
      mk(1,'epads','Supply of Microscopes (Re-Tender)','2026-12-01','NIH')],
     [[0,1]], [], 'a re-tender of the same item'],

    /* The case that matters: a generic title used by two different buyers. Merging these would
       hide one of them entirely. */
    [[mk(0,'ppra','Supply of Medical Equipment','2026-12-01','Health Department Punjab'),
      mk(1,'epads','Supply of Medical Equipment','2026-12-01','Health Department Sindh')],
     [], [[0,1]], 'same generic title, different buyers'],

    [[mk(0,'ppra','Supply of Chemicals','2026-12-01','University of Karachi'),
      mk(1,'kppra','Supply of Chemicals','2026-12-01','University of Peshawar')],
     [], [[0,1]], 'same short title, universities in different provinces'],

    [[mk(0,'ppra','Procurement of Next Generation Sequencing Reagents','2026-12-01','NIH'),
      mk(1,'epads','Procurement of Next Generation Sequencing Reagents','2026-12-01','NIH'),
      mk(2,'punjab','Procurement of Next Generation Sequencing Reagents','2026-12-01','NIH')],
     [[0,1],[1,2],[0,2]], [], 'the same tender on three portals all group together'],
];

foreach ($cases as [$rows, $mustMerge, $mustNot, $label]) {
    $out = tw_dedup($rows);
    $group = [];
    foreach ($out as $i => $r) $group[$i] = $r['dup_of'] === null ? $i : array_search($r['dup_of'], array_column($out, 'id'), true);
    $same = function ($a, $b) use ($out) {
        $ga = $out[$a]['dup_of'] ?? null; $gb = $out[$b]['dup_of'] ?? null;
        $ida = $out[$a]['id']; $idb = $out[$b]['id'];
        return ($ga === $idb) || ($gb === $ida) || ($ga !== null && $ga === $gb);
    };
    foreach ($mustMerge as [$a, $b]) check("dedup: $label — rows $a and $b merge", $same($a, $b));
    foreach ($mustNot as [$a, $b]) {
        $merged = $same($a, $b);
        check("dedup: $label — rows $a and $b stay separate", !$merged,
              $merged ? 'FALSE MERGE: "' . $rows[$a]['title'] . '" (' . $rows[$a]['org'] . ') + "' . $rows[$b]['title'] . '" (' . $rows[$b]['org'] . ')' : '');
    }
}

/* ---------------------------------------------------------------- scoring */
$rules = tw_rules();
$scoreCases = [
    ['Supply of PCR reagents and master mix', true,  'core PCR tender'],
    ['Procurement of ELISA kits for hepatitis screening', true, 'ELISA tender'],
    ['Supply of next generation sequencing consumables', true, 'NGS tender'],
    ['Construction of boundary wall at district hospital', false, 'construction at a hospital'],
    ['Supply of school uniforms', false, 'uniforms'],
    ['Repair of vehicles for health department', false, 'vehicle repair'],
    ['Hiring of security services at NIH', false, 'security services'],
    ['Supply of laboratory chemicals and glassware', true, 'lab consumables'],
];
foreach ($scoreCases as [$title, $wantRelevant, $label]) {
    /* tw_score returns a list: [score, categories, core, matched, relevant, excluded] */
    [$score, $cats, $core, $matched, $isRel, $excluded] = tw_score($title, "National Institute of Health");
    check("score: $label", ((bool)$isRel) === $wantRelevant,
          "score $score, relevant=" . var_export((bool)$isRel, true)
          . ', matched=' . implode('/', (array)$matched)
          . ', minus=' . implode('/', (array)$excluded));
}

echo "tender dedup + scoring test\n";
echo "  checks passed: $pass\n";
echo "  failures: " . count($fail) . "\n";
foreach ($fail as $f) echo "    - $f\n";
exec('rm -rf ' . escapeshellarg($tmp));
exit(count($fail) ? 1 : 0);
