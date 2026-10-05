# Website tender portal: the server-side reader

This is the reader that runs **on jb-scientific.com**, not on the office PC. It is plain PHP on
shared hosting (no Composer), lives at `catalogue/staff/tenders/` on the server, and is what
produces the "READ BY THE WEBSITE" portals on the staff dashboard.

Only `lib.php` is kept here, because that is the file this work changed. The complete portal is
shipped to the site as a pack (`JBS-tender-portal-update`), which also carries `api.php`,
`lib_tw2.php`, `tenders.html`, `run.php` and `rules.json`. The server's own `config.php` (secret
key, e-mail settings, portal list) and its `data/` directory are never shipped and never kept
here: they hold live settings and real tender data.

## Why it is in this repository

The office PC program (`tenderwatch/`) and this reader read many of the same portals, in two
different languages, and the same page defeats both in the same way. The faults found from the
pages captured on the office PC on 5 Oct 2026 had to be fixed twice - once in Python, once here -
and keeping this file alongside makes the pair reviewable.

## Tests

`tools-tests/tender_generic.php` covers the generic reader, and `tools-tests/tender_parse.php`
and `tender_dedup.php` cover import, scoring and duplicate matching. Run them against a copy of
the portal directory:

    php tools-tests/tender_generic.php /path/to/catalogue/staff/tenders
    php tools-tests/tender_parse.php   /path/to/catalogue/staff/tenders
    php tools-tests/tender_dedup.php   /path/to/catalogue/staff/tenders

As of 5 Oct 2026: 10 + 67 + 17 checks, all passing.
