# Tender Watch 2

Collects tenders every day from Pakistani and international procurement portals, **including portals
that need your account** (UNGM, EPADS and others), scores them for JB Scientific's business (NGS,
PCR, ELISA, reagents and kits, vaccines, lab equipment, medical supplies), removes copies of the same
tender listed on several portals, and shows them in one dashboard where the team can mark status and
add notes.

It runs **on your Windows PC**, not in the cloud: government portals block cloud servers, and your
sign-ins must stay on your own machine.

## What is new compared with the first Tender Watch

| | First version | Tender Watch 2 |
|---|---|---|
| Portals needing sign-in | not possible | UNGM, EPADS and any other: sign in once, or save the password in Windows Credential Manager for automatic sign-in |
| JavaScript portals (EPADS 2.0 Sindh/KP/GB/AJK) | separate "PC helper" | built in: reads the data the page loads |
| New portals | code per portal | usually just a URL in `config/sources.yaml`; columns are recognised by their headings |
| Duplicates across portals | 4 of ~38 caught | title + closing-date matching (19 groups in the old data) |
| False matches ("Injection Set", "Security services at NIH", IoT labs) | shown | excluded by new rules |
| Broken portal | silent "not read" | dashboard says what to do; page saved in `data/captures/` for fixing |
| Sharing | email form | copy for Excel, share list, CSV export, daily email digest, office-network dashboard |

## Set up (once, about 10 minutes)

1. Install **Python 3.12** from https://www.python.org/downloads/ . On the first installer screen tick
   **"Add python.exe to PATH"**.
2. Put this `tenderwatch` folder somewhere simple, e.g. `C:\TenderWatch`.
3. Double-click **`setup.bat`**. It installs what Tender Watch needs (about 60 MB) and creates
   `config\settings.yaml`. It uses the Microsoft Edge already on your PC, so there is no browser download.
4. Open `config\settings.yaml` in Notepad and put in your team's names and emails.

## Sign in to the portals that need your account

For each sign-in portal, choose **one** of these:

- **Save the password for automatic sign-in** (best for portals without a CAPTCHA):
  open a Command Prompt in the folder and type `tw set-login ungm`. You are asked for the username and
  password. They go into **Windows Credential Manager**, not into any file, and are never uploaded.
- **Sign in by hand** (for portals with a CAPTCHA or a code sent to your phone):
  `tw login epads-fed` opens a browser window; sign in, then press Enter in the Command Prompt.
  Tender Watch keeps that session until the portal logs you out. When that happens, the dashboard
  shows the portal as **sign in**, and you run `tw login <portal>` again.

Portal ids are in `config\sources.yaml` (`tw sources` lists them).

Tender Watch only **reads** tender lists. It never bids, uploads, or changes anything in your accounts.
It waits a couple of seconds between pages so it does not load the portals heavily. It does not try
to get past CAPTCHAs.

## Daily use

| To… | Do this |
|---|---|
| Check all portals now | double-click `run.bat` (or "Check portals now" on the dashboard) |
| Open the dashboard | double-click `dashboard.bat` (opens http://localhost:8765) |
| Check automatically twice a day | double-click `schedule.bat` once |
| Let colleagues on the office network use the dashboard | `dashboard.bat --lan`, and set `team_key` in settings.yaml |
| Get a daily email of new tenders | fill the `email:` part of settings.yaml, then `tw set-login email` |
| Excel file of relevant tenders | `tw export --csv` (writes `data\tenders.csv`) |
| One-file copy of the dashboard to send someone | `tw export` (writes `data\tender-watch-snapshot.html`) |
| Bring over the old Tender Watch's data | `tw import-old path\to\tenders.json` |

## Adding a portal you use

Open `config\sources.yaml`, copy an entry, change `id`, `name`, `region` and `url` (the page that lists
open tenders). For a sign-in portal add `login: true`, `login_url:` and a `logged_in_check:` (a word
that is only on the page when you are signed in, such as `Log ?out`). Then test it while watching:

```
tw test my-portal --show
```

It prints the tenders it found with their scores. If it finds nothing, the page is saved as
`data\captures\my-portal.html`; send that file to whoever maintains the tool so they can set the
`fields:` or `next:` options for that portal.

## Tuning what counts as relevant

`config\rules.yaml` holds the words that score a tender (strong 3, medium 2, weak 1) and the words that
exclude it (roads, uniforms, electrical test sets...). Edit it, then run `tw rescore`. The dashboard's
**Relevance threshold** slider shows borderline tenders without editing anything.

## First run: what to expect

The portal settings were written without access to the portals, because they block cloud servers, so
the first run on your PC is the real test. After `run.bat`, check `tw sources` or the portal row on the
dashboard:

- **green**: read fine.
- **sign in** (violet): run `tw login <id>`.
- **no list** / **error** (amber): click it on the dashboard for what to do. Usually one line in
  `sources.yaml` (`fields:` or `next:`) fixes it.

## For maintainers

- Python package `tw/`: `extract.py` (maps table headings / JSON keys to fields), `browser.py` (Playwright
  with a persistent profile; login, pagination, JSON capture, UNGM search, JSON APIs), `score.py`,
  `dedup.py`, `db.py` (SQLite in `data/tenders.db`), `server.py` + `web/index.html` (dashboard),
  `digest.py`, `export.py`.
- Tests: `pip install pytest` then `python -m pytest`. The browser tests run a headless browser
  against fake portals: a paginated table, a JavaScript app and a sign-in page. On Linux, set
  `TW_BROWSER_EXECUTABLE` if Playwright's Chromium is elsewhere.
- Works under WSL too (`python -m tw ...`), but password saving needs Windows Credential Manager, so use
  Windows Python for sign-in portals.
- Nothing personal is committed: `data/` (database, browser profile, cookies, captures) and
  `config/settings.yaml` are git-ignored.

Education/business-internal tool. Always confirm dates and documents on the official portal before bidding.
