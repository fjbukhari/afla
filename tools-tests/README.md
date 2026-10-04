# Primer designer stress tests

Tests for the two primer designers in the JB Scientific staff area
(`catalogue/staff/designers/`). They were written for the October 2026 audit and
are the evidence behind the fixes made then.

Nothing here trusts what the tools report. Each test drives the real page in a
browser, then re-checks every primer it produced against the reference sequence
and against primer3 (the program Primer-BLAST uses).

## What each file does

| File | Checks |
|---|---|
| `gpd_lib.py` | The stand-in reference genome, plus the browser routes that serve it. The base at any position is fixed by its coordinate, so a region always comes back identical and a reported primer can be looked up independently. Deliberately hard features are placed at known coordinates: GC-rich and AT-rich blocks, a homopolymer run, a CAG repeat, and a 400-base duplicated copy of a real target standing in for a pseudogene. |
| `gpd_ngs.py` | Step 5. Both primers really at the reported coordinates, product size matches, target exon inside the product, promised intronic flank achieved, melting temperature agrees with primer3, and the uniqueness claim matches an independent scan of the same 50 kb window. |
| `gpd_hrm.py` | Step 14. Primer and product positions, the variant inside the product with the promised gap, and the predicted melting temperatures against the long-duplex formula. |
| `gpd_qpcr.py` | Step 16. Product size in range, probe between the primers and clear of both, probe melting temperature above the primers', no G at the probe's 5' end, and the probe sequence matching its reported position and strand. |
| `sid_pool.py` | Species ID multiplex pooling: no two conflicting assays may share a pool, and no assay may be left unassigned. |
| `sid_deg.py` | Species ID degenerate primers: at most 2 ambiguous positions, never within 3 bases of the 3' end, for forward and reverse primers alike. |
| `FINDINGS.md` | The audit notes, including what was checked and found correct. |

## Running them

They need a local web server holding a copy of the site, a browser, and primer3:

```
pip install primer3-py playwright
python -m playwright install chromium        # or set the path used in the scripts
php -S 127.0.0.1:8900 test/router.php        # from the website working copy
python tools-tests/gpd_ngs.py TP53 20 400
```

Each prints JSON with an `issues` list. An empty list is a pass. The last run
before the fixes were published: NGS 12 designs / 0 issues, qPCR 5 designs /
0 issues, pooling 12 trials / 0 violations, degenerate rules 400 windows / 0
violations.

## What they do not cover

UCSC, Ensembl, NCBI and BOLD cannot be reached from the environment these were
written in, so they are simulated. The design logic is fully exercised; the live
connections are not, and need one real run in each step after any deployment.

## Tender portal tests

| File | Checks |
|---|---|
| `tender_parse.php` | The portal readers and the import from the office PC against hostile and malformed input: empty, truncated and deeply nested pages, XML entity tricks, script and data addresses in links, path traversal in a source name, enormous payloads, 2,000 rows at once, unparseable dates. Runs against a copy in a temporary folder, so live tender data is never touched. |
| `tender_dedup.php` | Duplicate detection and relevance scoring. Weighted towards the expensive mistake: merging two genuinely different tenders hides one of them, while failing to merge only shows the same tender twice. |
| `tender_xss.py` | Serves the dashboard a crafted feed where every text field carries a script payload and every address is a `javascript:` one, then checks that nothing executed, no markup was injected, no link carries an unsafe scheme, and ordinary tenders still render. |

```
php tools-tests/tender_parse.php      # 67 checks
php tools-tests/tender_dedup.php      # 17 checks
python3 tools-tests/tender_xss.py     # needs the local server on 127.0.0.1:8900
```
