<?php
/*
 * JBS Pakistan Tender Aggregator: core library
 * Pure PHP 7.4+ (curl, dom, json, mbstring). No Composer needed.
 */

define('TW_DIR', __DIR__);
define('TW_DATA', __DIR__ . '/data');

require_once __DIR__ . '/lib_tw2.php';

function tw_cfg() {
  static $c = null;
  if ($c === null) {
    $f = TW_DIR . '/config.php';
    if (!file_exists($f)) $f = TW_DIR . '/config.sample.php';
    $c = require $f;
    date_default_timezone_set($c['timezone'] ?? 'Asia/Karachi');
  }
  return $c;
}

function tw_rules() {
  static $r = null;
  if ($r === null) $r = json_decode(file_get_contents(TW_DIR . '/rules.json'), true);
  return $r;
}

function tw_log($msg) {
  if (!is_dir(TW_DATA)) @mkdir(TW_DATA, 0755, true);
  $line = '[' . date('Y-m-d H:i:s') . '] ' . $msg . "\n";
  file_put_contents(TW_DATA . '/run.log', $line, FILE_APPEND | LOCK_EX);
  if (PHP_SAPI === 'cli') echo $line;
}

function tw_clean($s) {
  $s = html_entity_decode((string)$s, ENT_QUOTES | ENT_HTML5, 'UTF-8');
  $s = preg_replace('/[\x{00A0}\s]+/u', ' ', $s);
  return trim($s);
}

/* ------------------------------------------------------------------ HTTP */

function tw_http($url, $post = null, $referer = null) {
  $c = tw_cfg()['http'];
  static $jar = null;
  if ($jar === null) $jar = tempnam(sys_get_temp_dir(), 'twc');
  $tries = max(1, (int)$c['retries'] + 1);
  $last = [0, '', $url, ''];
  for ($i = 0; $i < $tries; $i++) {
    $ch = curl_init($url);
    $opts = [
      CURLOPT_RETURNTRANSFER => true,
      CURLOPT_FOLLOWLOCATION => true,
      CURLOPT_MAXREDIRS      => 6,
      CURLOPT_CONNECTTIMEOUT => 20,
      CURLOPT_TIMEOUT        => (int)$c['timeout'],
      CURLOPT_USERAGENT      => $c['user_agent'],
      CURLOPT_ENCODING       => '',
      CURLOPT_COOKIEJAR      => $jar,
      CURLOPT_COOKIEFILE     => $jar,
      CURLOPT_SSL_VERIFYPEER => !empty($c['verify_ssl']),
      CURLOPT_SSL_VERIFYHOST => !empty($c['verify_ssl']) ? 2 : 0,
      CURLOPT_HTTPHEADER     => ['Accept: text/html,application/xhtml+xml,*/*;q=0.8', 'Accept-Language: en-US,en;q=0.9'],
    ];
    if ($referer) $opts[CURLOPT_REFERER] = $referer;
    if ($post !== null) {
      $opts[CURLOPT_POST] = true;
      $opts[CURLOPT_POSTFIELDS] = is_array($post) ? http_build_query($post) : $post;
    }
    curl_setopt_array($ch, $opts);
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $final = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    $err = curl_error($ch);
    curl_close($ch);
    $last = [$status, (string)$body, $final, $err];
    if ($status >= 200 && $status < 400 && strlen((string)$body) > 200) return $last;
    usleep(1500000 * ($i + 1));
  }
  return $last;
}

function tw_pause() { usleep((int)tw_cfg()['http']['delay_ms'] * 1000); }

/* ------------------------------------------------------------------ DOM helpers */

function tw_dom($html) {
  $d = new DOMDocument();
  libxml_use_internal_errors(true);
  if (!preg_match('/<meta[^>]+charset/i', substr($html, 0, 4000))) $html = '<?xml encoding="utf-8" ?>' . $html;
  $d->loadHTML($html, LIBXML_NOWARNING | LIBXML_NOERROR | LIBXML_COMPACT);
  libxml_clear_errors();
  return [$d, new DOMXPath($d)];
}

function tw_txt($node) { return $node ? tw_clean($node->textContent) : ''; }

function tw_q1($xp, $q, $ctx = null) {
  $n = $ctx ? $xp->query($q, $ctx) : $xp->query($q);
  return ($n && $n->length) ? $n->item(0) : null;
}

function tw_abs($href, $base) {
  $href = trim((string)$href);
  if ($href === '' || stripos($href, 'javascript:') === 0 || $href === '#') return '';
  if (preg_match('#^https?://#i', $href)) return $href;
  $p = parse_url($base);
  $root = $p['scheme'] . '://' . $p['host'] . (isset($p['port']) ? ':' . $p['port'] : '');
  if (strpos($href, '//') === 0) return $p['scheme'] . ':' . $href;
  if ($href[0] === '/') return $root . $href;
  $path = isset($p['path']) ? $p['path'] : '/';
  $path = preg_replace('#(\.(php|aspx?|html?))/.*$#i', '$1', $path); // "page.php/?p=2" style URLs
  $path = preg_replace('#/[^/]*$#', '/', $path);
  return $root . $path . $href;
}

function tw_cells($xp, $tr) {
  $out = [];
  foreach ($xp->query('./td', $tr) as $td) $out[] = $td;
  return $out;
}

/* ------------------------------------------------------------------ Dates */

function tw_date($s) {
  $s = tw_clean($s);
  if ($s === '') return '';
  $s = preg_replace('/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+/i', '', $s);
  // Common Pakistani portal formats
  $s = preg_replace('/^([A-Za-z]{3,9} \d{1,2}, \d{4}),\s*/', '$1 ', $s);   // "Sep 24, 2026, 5:14 AM" -> "Sep 24, 2026 5:14 AM"
  $fmts = ['M j, Y g:i A', 'd-M-Y', 'd-M-Y H:i', 'd M Y', 'd M Y H:i', 'M d, Y', 'M d, Y h:i A', 'F j, Y', 'F j, Y h:i A',
           'Y-m-d H:i:s', 'Y-m-d', 'd-m-Y', 'd/m/Y', 'd.m.Y', 'd F, Y', 'd F Y', 'j M, Y'];
  foreach ($fmts as $f) {
    $d = DateTime::createFromFormat('!' . $f, $s);
    if ($d && $d->format('Y') > 2000) return $d->format(strpos($f, 'H') !== false || strpos($f, 'h') !== false ? 'Y-m-d H:i' : 'Y-m-d');
  }
  if (!preg_match('/\d/', $s) || mb_strlen($s) > 40) return '';
  $t = strtotime($s);
  return ($t && date('Y', $t) > 2000) ? date('Y-m-d', $t) : '';
}

function tw_find_dates($text) {
  $pat = '/(\d{1,2}[-\/\. ](?:\d{1,2}|[A-Za-z]{3,9})[-\/\., ]+\d{4}|[A-Za-z]{3,9} \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})/';
  preg_match_all($pat, $text, $m);
  $out = [];
  foreach ($m[1] as $d) { $x = tw_date($d); if ($x) $out[] = $x; }
  return $out;
}

/* ------------------------------------------------------------------ Relevance scoring */

function tw_term_re($t) {
  static $cache = [];
  if (!isset($cache[$t])) $cache[$t] = '~(?<![A-Za-z0-9])(?:' . str_replace('~', '\\~', $t) . ')(?![A-Za-z0-9])~iu';
  return $cache[$t];
}

/** @return array [score, categories[], core(bool), matched[], relevant(bool), excluded[]] */
function tw_score($title, $org = '', $type = '') {
  $R = tw_rules();
  $text = $title . ' | ' . $org;
  $score = 0; $cats = []; $matched = []; $hasSM = false; $hasStrong = false; $core = false; $excl = [];
  foreach ($R['categories'] as $cat => $def) {
    foreach (['strong' => 3, 'medium' => 2] as $lvl => $w) {
      foreach ($def[$lvl] as $t) {
        // only match on title for strong/medium to avoid "Department of Pathology" org noise
        if (preg_match(tw_term_re($t), $title, $m)) {
          $k = strtolower($m[0]);
          if (isset($matched[$k])) continue;
          $matched[$k] = $w; $score += $w; $hasSM = true; if ($w === 3) $hasStrong = true;
          $cats[$cat] = ($cats[$cat] ?? 0) + $w;
          if (!empty($def['core']) && $w >= 2) $core = $core || $w === 3 || ($cats[$cat] >= 3);
        }
      }
    }
  }
  // Buyer is a hospital / lab / health office: budget-head titles like "Generic Consumables" or "Chemicals" count.
  $healthOrg = false;
  foreach (($R['health_orgs'] ?? []) as $t) if ($org !== '' && preg_match(tw_term_re($t), $org)) { $healthOrg = true; break; }
  if ($healthOrg) {
    foreach (($R['generic_supply'] ?? []) as $t) {
      if (preg_match(tw_term_re($t), $title, $m)) {
        $k = strtolower($m[0]); if (isset($matched[$k])) { $hasSM = true; continue; }
        $matched[$k] = 2; $score += 2; $hasSM = true;
        $c = 'Pharmaceuticals & Medical Supplies'; $cats[$c] = ($cats[$c] ?? 0) + 2;
        break;
      }
    }
    if ($hasSM) $score += (int)($R['health_org_bonus'] ?? 0);
  }
  foreach ($R['weak'] as $t) {
    if (preg_match(tw_term_re($t), $text, $m)) { $k = strtolower($m[0]); if (!isset($matched[$k])) { $matched[$k] = 1; $score += 1; } }
  }
  foreach ($R['exclude'] as $t) {
    if (preg_match(tw_term_re($t), $title, $m)) { $excl[] = strtolower($m[0]); $score -= $hasStrong ? intdiv((int)$R['exclude_penalty'], 2) : (int)$R['exclude_penalty']; }
  }
  if (preg_match('/^\s*(works?|civil)/i', $type)) $score -= (int)$R['works_type_penalty'];
  arsort($cats);
  $relevant = $hasSM && $score >= (int)$R['threshold'];
  return [$score, array_keys($cats), $core && $relevant, array_keys($matched), $relevant, $excl];
}

/* ------------------------------------------------------------------ Parsers
 * Every parser returns: ['items' => [...], 'next' => callable|null|string]
 * item fields: ref, title, desc, org, location, type, published, closing, url, doc_url
 */

function tw_parse_epms($html, $url) {
  [$d, $xp] = tw_dom($html);
  $items = [];
  foreach ($xp->query('//table//tbody/tr') as $tr) {
    $td = tw_cells($xp, $tr);
    if (count($td) < 7) continue;
    $ref = tw_txt(tw_q1($xp, './/strong', $td[1])) ?: tw_txt($td[1]);
    $title = tw_txt(tw_q1($xp, './/strong', $td[2]));
    if ($title === '' || $ref === '') continue;
    $desc = tw_txt(tw_q1($xp, './/small[contains(@class,"d-block")]', $td[2]));
    $cat = tw_txt(tw_q1($xp, './/small[contains(@class,"badge")]', $td[2]));
    $org = tw_txt(tw_q1($xp, './/span[contains(@class,"tender-org")]', $td[3]));
    $ministry = tw_txt(tw_q1($xp, './small', $td[3]));
    $loc = '';
    foreach ($xp->query('./small', $td[3]) as $s) { if ($xp->query('.//i[contains(@class,"map-pin")]', $s)->length) $loc = tw_txt($s); }
    $close = tw_txt(tw_q1($xp, './/strong', $td[6])) . ' ' . tw_txt(tw_q1($xp, './/small', $td[6]));
    $a = tw_q1($xp, './/a[contains(@href,"tender-details")]', $td[7] ?? $td[6]);
    $items[] = [
      'ref' => $ref, 'title' => $title, 'desc' => $desc, 'type' => $cat,
      'org' => trim($org . ($ministry && $ministry !== $org ? ' — ' . $ministry : '')),
      'location' => preg_replace('/\s*-\s*Pakistan$/i', '', $loc),
      'published' => tw_date(tw_txt($td[5])), 'closing' => tw_date(trim($close)),
      'url' => $a ? tw_abs($a->getAttribute('href'), $url) : $url, 'doc_url' => '',
    ];
  }
  return $items;
}

function tw_parse_epads($html, $url) {
  [$d, $xp] = tw_dom($html);
  $items = [];
  foreach ($xp->query('//table//tbody/tr') as $tr) {
    $td = tw_cells($xp, $tr);
    if (count($td) < 4) continue;
    $a = tw_q1($xp, './/a[contains(@href,"/procurements/") or contains(@href,"/opportunities/")]', $td[1]);
    if (!$a) continue;
    $spans = $xp->query('.//span[@data-bs-original-title or @title]', $td[1]);
    $title = $spans->length ? tw_clean($spans->item(0)->getAttribute('data-bs-original-title') ?: $spans->item(0)->getAttribute('title')) : tw_txt($a);
    if ($title === '') $title = tw_txt($a);
    $org = $spans->length > 1 ? tw_clean($spans->item(1)->getAttribute('data-bs-original-title') ?: $spans->item(1)->textContent) : '';
    $ref = tw_txt(tw_q1($xp, './/span[contains(@class,"badge")]', $td[1]));
    $badges = $xp->query('.//span[contains(@class,"badge")]', $td[2]);
    $pub = $badges->length ? tw_date($badges->item(0)->textContent) : '';
    $close = $badges->length > 1 ? tw_date($badges->item(1)->textContent) : '';
    $type = tw_txt(tw_q1($xp, './/span[contains(@class,"badge")]', $td[3]));
    $proc = tw_txt(tw_q1($xp, './/span[contains(@class,"text-secondary")]', $td[3]));
    $href = tw_abs($a->getAttribute('href'), $url);
    $region = preg_match('#/opportunities/([a-z\-]+)/#i', $href, $m) ? ucfirst($m[1]) : '';
    $items[] = [
      'ref' => $ref ?: basename($href), 'title' => $title, 'desc' => $proc, 'type' => $type,
      'org' => $org, 'location' => '', 'published' => $pub, 'closing' => $close,
      'url' => $href, 'doc_url' => '', 'region_hint' => $region,
    ];
  }
  return $items;
}

function tw_parse_punjab($html, $url) {
  [$d, $xp] = tw_dom($html);
  $items = [];
  foreach ($xp->query('//tr[contains(@class,"rgRow") or contains(@class,"rgAltRow")]') as $tr) {
    $td = tw_cells($xp, $tr);
    if (count($td) < 6) continue;
    $kind = tw_txt($td[0]);
    $nameCell = $td[1];
    $det = tw_q1($xp, './/a[contains(@href,"Detail")]', $nameCell);
    $title = tw_clean(preg_replace('/\(\s*View Tender Detail\s*\)/i', '', $nameCell->textContent));
    $notice = isset($td[7]) ? tw_q1($xp, './/a[@href]', $td[7]) : null;
    $bidDoc = isset($td[8]) ? tw_q1($xp, './/a[@href]', $td[8]) : null;
    $noticeUrl = $notice ? tw_abs($notice->getAttribute('href'), $url) : '';
    $id = $det && preg_match('/id=(\d+)/', $det->getAttribute('href'), $m) ? $m[1] : '';
    $items[] = [
      'ref' => $id ? 'PB-' . $id : '', 'title' => $title, 'desc' => $kind, 'type' => tw_txt($td[2]),
      'org' => tw_txt($td[5]), 'location' => '', 'published' => tw_date(tw_txt($td[3])), 'closing' => tw_date(tw_txt($td[4])),
      'url' => $det ? tw_abs($det->getAttribute('href'), $url) : ($noticeUrl ?: $url),
      'doc_url' => $noticeUrl ?: ($bidDoc ? tw_abs($bidDoc->getAttribute('href'), $url) : ''),
    ];
  }
  return $items;
}

/** ASP.NET/Telerik postback to the next page of the Punjab RadGrid. Returns [html, url] or null. */
function tw_punjab_next($html, $url, $nextPage) {
  [$d, $xp] = tw_dom($html);
  $target = null;
  foreach ($xp->query('//div[contains(@class,"rgNumPart")]//a') as $a) {
    if (trim($a->textContent) === (string)$nextPage && preg_match("/__doPostBack\\('([^']+)'/", $a->getAttribute('href'), $m)) { $target = $m[1]; break; }
  }
  if (!$target) return null;
  $post = [];
  foreach ($xp->query('//form//input[@name]') as $in) {
    $t = strtolower($in->getAttribute('type'));
    if (in_array($t, ['submit', 'image', 'button', 'checkbox', 'radio'])) continue;
    $post[$in->getAttribute('name')] = $in->getAttribute('value');
  }
  $post['__EVENTTARGET'] = $target;
  $post['__EVENTARGUMENT'] = '';
  $form = tw_q1($xp, '//form[@action]');
  $action = $form ? tw_abs($form->getAttribute('action'), $url) : $url;
  [$st, $body] = tw_http($action ?: $url, $post, $url);
  return ($st >= 200 && $st < 400) ? [$body, $action ?: $url] : null;
}

function tw_parse_kppra($html, $url) {
  [$d, $xp] = tw_dom($html);
  $items = [];
  foreach ($xp->query('//tr') as $tr) {
    $td = tw_cells($xp, $tr);
    if (count($td) < 6) continue;
    $id = tw_txt($td[0]);
    if (!preg_match('/^\d{3,}$/', $id)) continue;
    $pub = tw_date(tw_txt($td[3])); $close = tw_date(tw_txt($td[4]));
    if (!$pub && !$close) continue;
    $dl = tw_q1($xp, './/a[@href]', $td[5]);
    $items[] = [
      'ref' => 'KP-' . $id, 'title' => tw_txt($td[1]), 'desc' => '', 'type' => '',
      'org' => tw_txt($td[2]), 'location' => '', 'published' => $pub, 'closing' => $close,
      'url' => $url, 'doc_url' => $dl ? tw_abs($dl->getAttribute('href'), $url) : '',
    ];
  }
  return $items;
}

/** Remove the parts of a page that are never a tender: scripts, stylesheets, and (for the
 *  link pass) the site's own navigation. The KP health department's tenders page put a <style>
 *  block inside a table row, so the one "tender" read from that page was a block of CSS - and
 *  because that counted as a result, the link pass below never ran and the 400 real notices on
 *  the page were never seen. */
function tw_strip_noise($xp, $alsoChrome = false) {
  $q = ['//script', '//style', '//noscript'];
  if ($alsoChrome) { $q[] = '//nav'; $q[] = '//header'; $q[] = '//footer'; }
  foreach ($q as $sel) {
    foreach (iterator_to_array($xp->query($sel)) as $n) {
      if ($n->parentNode) $n->parentNode->removeChild($n);
    }
  }
}

/** A link's shape: /news/view/1257 and /news/view/1255 share one, a Google Maps link does not. */
function tw_url_shape($u) {
  $p = parse_url($u);
  $path = preg_replace('/\d+/', '#', $p['path'] ?? '/');
  $path = preg_replace('#/[^/]{24,}$#', '/*', $path);
  $keys = '';
  if (!empty($p['query'])) { parse_str($p['query'], $q); $k = array_keys($q); sort($k); $keys = implode(',', $k); }
  return ($p['host'] ?? '') . '|' . $path . '|' . $keys;
}

/** The column headings of the table a row belongs to, lower-cased, by column number.
 *  Used to tell a closing date from a publication date - see tw_generic_rows. */
function tw_generic_headers($xp, $tr) {
  $table = $tr->parentNode;
  while ($table && $table->nodeName !== 'table') $table = $table->parentNode;
  if (!$table) return [];
  $head = tw_q1($xp, '(.//thead//tr[th or td])[1]', $table) ?: tw_q1($xp, '(.//tr[th])[1]', $table);
  if (!$head) return [];
  $out = [];
  // tw_cells() collects only <td>, because the mapped parsers count columns that way; a heading
  // row is usually <th>, so its cells are taken here instead of changing that for everyone.
  foreach ($xp->query('./td|./th', $head) as $i => $c) $out[$i] = mb_strtolower(tw_txt($c));
  return $out;
}

/** Rows of a table that is not a layout wrapper. */
function tw_generic_rows($xp, $url) {
  $items = []; $seen = [];
  foreach ($xp->query('//tr[td]') as $tr) {
    $td = tw_cells($xp, $tr);
    if (count($td) < 2) continue;
    if ($xp->query('.//tr', $tr)->length) continue; // skip layout rows that wrap other tables
    $texts = array_map('tw_txt', $td);
    $full = implode(' | ', array_filter($texts));
    if (mb_strlen($full) < 25) continue;
    // Unknown layout: keep every non-numeric cell (title + organisation + notes) so scoring sees all of it.
    $title = implode(' | ', array_filter($texts, function ($t) { return $t !== '' && !preg_match('/^[\d\W]+$/u', $t) && !tw_date($t); }));
    // A row with one date used to make it the publication date always, so a list with only a
    // "Closing Date" column lost every deadline - and a tender with no closing date counts as
    // open for ever. Where the table names its columns, believe the names.
    $dates = tw_find_dates($full);
    $heads = tw_generic_headers($xp, $tr);
    $pubCol = $closeCol = '';
    foreach ($texts as $i => $t) {
      $d = tw_date($t);
      if (!$d || !isset($heads[$i])) continue;
      if (!$closeCol && preg_match('/clos|last ?date|deadline|due|submission|bid ?open|opening|expir|end ?date/i', $heads[$i])) $closeCol = $d;
      elseif (!$pubCol && preg_match('/publish|advertis|post|issue|upload|start|notice ?date|date of (ad|pub)|^date$/i', $heads[$i])) $pubCol = $d;
    }
    $a = tw_q1($xp, './/a[contains(translate(@href,"PDF","pdf"),".pdf")]', $tr) ?: tw_q1($xp, './/a[@href and not(starts-with(@href,"javascript"))]', $tr);
    $href = $a ? tw_abs($a->getAttribute('href'), $url) : '';
    $key = md5($title . $href);
    if (isset($seen[$key])) continue; $seen[$key] = 1;
    sort($dates);
    $items[] = [
      'ref' => '', 'title' => mb_substr($title, 0, 400), 'desc' => mb_substr($full, 0, 600), 'type' => '',
      'org' => '', 'location' => '',
      'published' => $pubCol ?: ($closeCol ? '' : ($dates[0] ?? '')),
      'closing' => $closeCol ?: (count($dates) > 1 ? end($dates) : ''),
      'url' => $href ?: $url, 'doc_url' => ($href && preg_match('/\.pdf/i', $href)) ? $href : '',
    ];
  }
  return $items;
}

/** Pages that are a list of links rather than a table - how most institutions publish.
 *  A stray link is not a tender: BPPRA's front page offered its own office address and a
 *  software vendor's URL, both worded tenderishly. A link counts only if it belongs to a list
 *  of at least three of its shape, or points straight at a document. */
define('TW_LINKLIST_MAX', 60);

function tw_generic_links($xp, $url) {
  $cand = []; $shapes = [];
  foreach ($xp->query('//a[@href]') as $a) {
    $t = tw_txt($a);
    if (mb_strlen($t) < 30 || !preg_match('/tender|procure|supply|purchase|notice|bid|quotation|EOI/i', $t)) continue;
    // Some listings repeat their field labels inside the row ("Title <subject> Ref No <ref>"),
    // which would otherwise be stored as part of every tender's name. UNDP does this.
    $t = tw_clean(preg_replace('/^(title|subject|description)\s*[:\-]?\s+/i', '', $t));
    $href = $a->getAttribute('href');
    if ($href === '' || preg_match('/^(#|javascript:|mailto:|tel:)/i', $href)) continue;
    $abs = tw_abs($href, $url);
    $shape = tw_url_shape($abs);
    $shapes[$shape] = ($shapes[$shape] ?? 0) + 1;
    $cand[] = ['t' => $t, 'url' => $abs, 'shape' => $shape];
  }
  $items = []; $seen = [];
  foreach ($cand as $c) {
    $isDoc = (bool)preg_match('/\.(pdf|docx?|xlsx?|zip|rar)(\?|$)/i', $c['url']);
    if (($shapes[$c['shape']] ?? 0) < 3 && !$isDoc) continue;
    if (isset($seen[$c['url']])) continue; $seen[$c['url']] = 1;
    $items[] = ['ref' => '', 'title' => mb_substr($c['t'], 0, 400), 'desc' => '', 'type' => '', 'org' => '',
      'location' => '', 'published' => '', 'closing' => '', 'url' => $c['url'],
      'doc_url' => $isDoc ? $c['url'] : ''];
  }
  // These pages carry no closing dates, and a tender with no closing date counts as open for as
  // long as the page lists it. The KP health department's page is its whole archive back to
  // 2019 - 389 notices - so every one of them would have shown as open for ever. They are
  // newest-first, so only the newest are kept.
  return array_slice($items, 0, TW_LINKLIST_MAX);
}

/** Fallback for portals whose layout is not yet mapped: every table row (or long link) becomes a candidate. */
function tw_parse_generic($html, $url) {
  [$d, $xp] = tw_dom($html);
  tw_strip_noise($xp);
  $items = tw_generic_rows($xp, $url);
  // A page can hold both a stray table and a real list of links. Taking the table's result
  // whenever it was not empty meant one junk row hid four hundred genuine notices, so read the
  // links too whenever the table gave almost nothing, and keep whichever found more.
  if (count($items) < 3) {
    tw_strip_noise($xp, true);
    $links = tw_generic_links($xp, $url);
    if (count($links) > count($items)) $items = $links;
  }
  return $items;
}

function tw_page_url($src, $page) {
  $u = $src['url'];
  switch ($src['parser']) {
    case 'epms':
    case 'epads':
      return $page == 1 ? $u : $u . (strpos($u, '?') === false ? '?' : '&') . 'page=' . $page;
    case 'kppra':
      return $page == 1 ? $u : preg_replace('#\?.*$#', '', $u) . '/?&sort=&order=&&p=' . $page;
  }
  return $u;
}

/* ------------------------------------------------------------------ Store */

function tw_load($name, $default = []) {
  $f = TW_DATA . '/' . $name;
  if (!file_exists($f)) return $default;
  $j = json_decode(file_get_contents($f), true);
  return is_array($j) ? $j : $default;
}

/* Read a data file, change it, and write it back while holding a lock on it.
 *
 * tw_load() + tw_save() on their own are a read-modify-write: two requests that overlap both
 * read the same starting file and the second one's write wipes out the first one's change.
 * Tested with 12 note saves sent at once, only 4 survived - the other 8 were lost silently,
 * which for a dashboard several people use at the same time means one person's status update
 * quietly undoes another's. $fn receives the current contents and returns the new contents;
 * everything between the read and the write happens under an exclusive lock, so saves queue up
 * instead of overwriting each other.
 */
function tw_update($name, callable $fn) {
  if (!is_dir(TW_DATA)) @mkdir(TW_DATA, 0755, true);
  $path = TW_DATA . '/' . $name;
  $lockPath = TW_DATA . '/.' . $name . '.lock';
  $lock = fopen($lockPath, 'c');
  if ($lock === false) {                       // cannot lock: fall back to the old behaviour
    $data = $fn(tw_load($name));
    tw_save($name, $data);
    return $data;
  }
  try {
    flock($lock, LOCK_EX);
    $cur = [];
    if (file_exists($path)) {
      $j = json_decode(file_get_contents($path), true);
      if (is_array($j)) $cur = $j;
    }
    $data = $fn($cur);
    $tmp = TW_DATA . '/.' . $name . '.tmp';
    file_put_contents($tmp, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
    rename($tmp, $path);
    return $data;
  } finally {
    flock($lock, LOCK_UN);
    fclose($lock);
  }
}

function tw_save($name, $data) {
  if (!is_dir(TW_DATA)) @mkdir(TW_DATA, 0755, true);
  $tmp = TW_DATA . '/.' . $name . '.tmp';
  file_put_contents($tmp, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), LOCK_EX);
  rename($tmp, TW_DATA . '/' . $name);
}

function tw_item_id($src, $it) {
  $basis = $it['ref'] !== '' ? $it['ref'] : ($it['title'] . '|' . $it['org'] . '|' . $it['closing'] . '|' . $it['url']);
  return $src['id'] . ':' . substr(sha1($basis), 0, 12);
}

/** The same tender is often advertised on two portals (e.g. EPMS and EPADS). Mark the copies so lists and emails show it once. */
function tw_norm($s, $n) {
  $s = strtolower(preg_replace('/[^a-z0-9]+/i', '', $s));
  $s = preg_replace('/^(tendernotice|tenderfor|tender|corrigendum|procurementof|purchaseof|supplyof)/', '', $s);
  return substr($s, 0, $n);
}
function tw_mark_duplicates($list) {
  // Same tender on two portals: same title start and same buyer, closing dates within 3 days of each other
  // (EPMS and EPADS sometimes record different closing days for the same notice).
  $pref = ['epads-fed' => 1, 'ppra-fed' => 2, 'ppra-punjab' => 3, 'kppra' => 4];
  $buckets = [];
  foreach ($list as $i => $t) { $list[$i]['dup_of'] = null; $buckets[tw_norm($t['title'], 70) . '|' . tw_norm($t['org'], 18)][] = $i; }
  foreach ($buckets as $idx) {
    if (count($idx) < 2) continue;
    usort($idx, function ($a, $b) use ($list, $pref) { return ($pref[$list[$a]['source']] ?? 9) <=> ($pref[$list[$b]['source']] ?? 9); });
    $mains = [];
    foreach ($idx as $i) {
      $ci = strtotime(substr((string)$list[$i]['closing'], 0, 10)) ?: 0;
      $hit = null;
      foreach ($mains as $m) { $cm = strtotime(substr((string)$list[$m]['closing'], 0, 10)) ?: 0; if (abs($ci - $cm) <= 3 * 86400 && $list[$m]['source'] !== $list[$i]['source']) { $hit = $m; break; } }
      if ($hit === null) { $mains[] = $i; continue; }
      $list[$i]['dup_of'] = $list[$hit]['id'];
      $list[$hit]['also_on'][] = ['source' => $list[$i]['source_name'], 'url' => $list[$i]['url']];
      // if either copy is relevant/core, the kept copy shows it
      if (!empty($list[$i]['core'])) $list[$hit]['core'] = true;
    }
  }
  return $list;
}

/** Write the dashboard feeds: tenders.json (for web) and tenders.js (works when the HTML is opened from disk). */
function tw_export($db, $sources) {
  $today = date('Y-m-d');
  $list = array_values($db);
  usort($list, function ($a, $b) { return strcmp($b['first_seen'], $a['first_seen']) ?: ($b['score'] <=> $a['score']); });
  foreach ($list as &$t) {
    $t['open'] = !$t['closing'] || substr($t['closing'], 0, 10) >= $today;
    $t['city'] = tw_city($t['location'] ?? '', $t['org'] ?? '', $t['title'] ?? '');
    $t['institute'] = tw_institute($t['org'] ?? '');
    $t['has_sm'] = !empty($t['relevant']) || !empty($t['categories']);   // hit at least one strong/medium term
    $t['excluded'] = $t['excluded_terms'] ?? [];
    $t['items'] = $t['items'] ?? [];
  }
  unset($t);
  $list = tw_dedup($list);   // Tender Watch 2 matching (was tw_mark_duplicates)
  $feed = ['generated' => date('c'), 'rules' => tw_rules(), 'sources' => $sources, 'tenders' => $list];
  tw_save('tenders.json', $feed);
  file_put_contents(TW_DATA . '/tenders.js', 'window.TENDER_FEED = ' . json_encode($feed, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . ";\n", LOCK_EX);
}

/* ------------------------------------------------------------------ Ingest */

/** Score parsed rows and merge them into the database. Returns how many rows were never seen before. */
function tw_ingest(&$db, &$seen, $src, $items, $now, &$st) {
  $fresh = 0;
  foreach ($items as $it) {
    $st['rows']++;
    $id = tw_item_id($src, $it);
    if (!isset($seen[$id])) { $seen[$id] = substr($now, 0, 10); $fresh++; }
    $scoreTitle = $it['title'] . ($src['parser'] === 'generic' ? ' ' . $it['desc'] : '');
    [$score, $cats, $core, $matched, $rel, $excl] = tw_score($scoreTitle, $it['org'], $it['type']);
    // keep "borderline" rows (a real category hit, but pulled under the threshold) so the dashboard can show them on request
    $borderline = !$rel && $cats && $score >= 1;
    if (!$rel && !$borderline) { if (isset($db[$id])) unset($db[$id]); continue; }
    if ($rel) $st['relevant']++;
    $isNew = !isset($db[$id]);
    $rec = $isNew ? ['first_seen' => $now] : $db[$id];
    $region = (!empty($it['region_hint']) && strtolower($it['region_hint']) !== 'federal') ? $it['region_hint'] : $src['region'];
    $rec = array_merge($rec, [
      'id' => $id, 'source' => $src['id'], 'source_name' => $src['name'], 'region' => $region,
      'ref' => $it['ref'], 'title' => $it['title'], 'desc' => $it['desc'], 'org' => $it['org'],
      'location' => $it['location'], 'type' => $it['type'], 'published' => $it['published'],
      'closing' => $it['closing'], 'url' => $it['url'], 'doc_url' => $it['doc_url'],
      'score' => $score, 'categories' => $cats, 'core' => $core, 'matched' => $matched,
      'excluded_terms' => $excl, 'relevant' => $rel, 'last_seen' => $now, 'generic' => $src['parser'] === 'generic',
    ]);
    if (!empty($it['items'])) $rec['items'] = array_values(array_slice($it['items'], 0, 300));
    // a borderline row that later becomes relevant counts as "new" for the digest from that moment
    if ($rel && ($isNew || empty($db[$id]['relevant']))) { $rec['first_relevant'] = $now; $st['new']++; }
    $db[$id] = $rec;
  }
  return $fresh;
}

/* ------------------------------------------------------------------ Import from the PC helper */

/** Tenders read by the PC helper (EPADS 2.0 portals that need a real browser). $meta: id, name, region, url. */
function tw_import($meta, $rows, $pagesRead = 0) {
  $id = preg_replace('/[^a-z0-9\-]/i', '', $meta['id'] ?? '');
  if (!$id) throw new Exception('source id missing');
  $src = ['id' => $id, 'name' => mb_substr($meta['name'] ?? $id, 0, 80), 'region' => mb_substr($meta['region'] ?? '', 0, 40),
          'url' => $meta['url'] ?? '', 'parser' => 'helper'];
  $db = tw_load('tenders_db.json'); $seen = tw_load('seen.json'); $status = tw_load('sources_status.json');
  $now = date('Y-m-d H:i:s');
  $st = ['id' => $id, 'name' => $src['name'], 'region' => $src['region'], 'url' => $src['url'], 'verified' => true,
         'last_run' => $now, 'ok' => false, 'pages' => (int)$pagesRead, 'rows' => 0, 'relevant' => 0, 'new' => 0, 'error' => '', 'via' => 'PC helper'];
  $items = [];
  foreach ($rows as $r) {
    $title = tw_clean($r['title'] ?? ''); if ($title === '') continue;
    $statusTxt = tw_clean($r['status'] ?? '');
    if (preg_match('/cancel/i', $statusTxt)) continue;   // cancelled tenders are not biddable
    $url = (string)($r['url'] ?? ''); $doc = (string)($r['doc_url'] ?? '');
    $lines = [];
    foreach (array_slice((array)($r['items'] ?? []), 0, 300) as $line) { $line = mb_substr(tw_clean((string)$line), 0, 260); if ($line !== '') $lines[] = $line; }
    $items[] = ['ref' => tw_clean($r['ref'] ?? ''), 'title' => $title, 'desc' => $statusTxt, 'type' => tw_clean($r['type'] ?? ''),
      'org' => tw_clean($r['org'] ?? ''), 'location' => tw_clean($r['location'] ?? ''),
      'published' => tw_date($r['published'] ?? ''), 'closing' => tw_date($r['closing'] ?? ''),
      'url' => preg_match('#^https?://#i', $url) ? $url : $src['url'], 'doc_url' => preg_match('#^https?://#i', $doc) ? $doc : '',
      'items' => $lines];
  }
  tw_ingest($db, $seen, $src, $items, $now, $st);
  $st['ok'] = $st['rows'] > 0 || count($rows) > 0;
  $st['last_ok'] = $st['ok'] ? $now : ($status[$id]['last_ok'] ?? '');
  $st['total_in_db'] = count(array_filter($db, function ($t) use ($id) { return $t['source'] === $id && $t['relevant']; }));
  $status[$id] = $st;
  tw_save('tenders_db.json', $db); tw_save('seen.json', $seen); tw_save('sources_status.json', $status);
  tw_export($db, array_values($status));
  tw_log(sprintf('%-12s (PC helper) rows=%d relevant=%d new=%d', $id, $st['rows'], $st['relevant'], $st['new']));
  return $st;
}

/* ------------------------------------------------------------------ Fetch run */

function tw_fetch_all($only = null) {
  $cfg = tw_cfg();
  $db = tw_load('tenders_db.json');
  $seen = tw_load('seen.json');
  $status = tw_load('sources_status.json');
  $now = date('Y-m-d H:i:s');
  $newRelevant = 0;

  foreach ($cfg['sources'] as $src) {
    if (empty($src['enabled'])) continue;
    if ($only && $only !== $src['id']) continue;
    // EPADS 2.0 portals are JavaScript apps: the website cannot read them, the office-PC program does.
    if (($src['parser'] ?? '') === 'generic' && stripos($src['url'] ?? '', 'eprocure.gov.pk') !== false) continue;
    $st = ['id' => $src['id'], 'name' => $src['name'], 'region' => $src['region'], 'url' => $src['url'],
           'verified' => !empty($src['verified']), 'last_run' => $now, 'ok' => false, 'pages' => 0,
           'rows' => 0, 'relevant' => 0, 'new' => 0, 'error' => ''];
    $html = null; $pageUrl = tw_page_url($src, 1);
    $firstRun = !isset($status[$src['id']]['ok']) || !$status[$src['id']]['ok'];
    try {
      for ($p = 1; $p <= max(1, (int)$src['max_pages']); $p++) {
        if ($p > 1) tw_pause();
        if ($src['parser'] === 'punjab' && $p > 1) {
          $r = tw_punjab_next($html, $pageUrl, $p);
          if (!$r) break;
          [$html, $pageUrl] = $r;
        } else {
          $pageUrl = tw_page_url($src, $p);
          if ($p > 1 && $pageUrl === $src['url']) break; // parser without paging
          [$code, $html, $final, $err] = tw_http($pageUrl);
          if ($code < 200 || $code >= 400 || strlen($html) < 200) {
            if ($p === 1) throw new Exception("HTTP $code " . ($err ?: 'empty response'));
            break;
          }
        }
        $fn = 'tw_parse_' . $src['parser'];
        $items = $fn($html, $pageUrl);
        $st['pages'] = $p;
        if (!$items) break;
        $fresh = tw_ingest($db, $seen, $src, $items, $now, $st);
        // Portals list newest first: once a whole page is already known (and this is not a first run), stop.
        if (!$firstRun && $p >= 2 && $fresh === 0) break;
      }
      $newRelevant += $st['new'];
      $st['ok'] = $st['rows'] > 0;
      if (!$st['ok'] && !$st['error']) $st['error'] = 'Page loaded but no tender rows recognised (layout may have changed).';
    } catch (Throwable $e) {
      $st['error'] = $e->getMessage();
    }
    $st['total_in_db'] = count(array_filter($db, function ($t) use ($src) { return $t['source'] === $src['id'] && $t['relevant']; }));
    $st['last_ok'] = $st['ok'] ? $now : ($status[$src['id']]['last_ok'] ?? '');
    $status[$src['id']] = $st;
    tw_log(sprintf('%-12s pages=%d rows=%d relevant=%d new=%d %s', $src['id'], $st['pages'], $st['rows'], $st['relevant'], $st['new'], $st['error'] ? 'ERROR: ' . $st['error'] : 'ok'));
  }

  // prune: closed long ago, and the seen-index older than 120 days
  $cut = date('Y-m-d', strtotime('-' . (int)$cfg['keep_days_after_close'] . ' days'));
  foreach ($db as $id => $t) if ($t['closing'] && substr($t['closing'], 0, 10) < $cut) unset($db[$id]);
  $cutSeen = date('Y-m-d', strtotime('-120 days'));
  foreach ($seen as $id => $d) if ($d < $cutSeen) unset($seen[$id]);

  tw_save('tenders_db.json', $db);
  tw_save('seen.json', $seen);
  tw_save('sources_status.json', $status);
  tw_export($db, array_values($status));
  tw_log("Fetch finished: $newRelevant new relevant tenders; " . count($db) . ' in database.');
  return $newRelevant;
}
