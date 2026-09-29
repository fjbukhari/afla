# AFLA: context for Claude Code

## What this project is
Nextflow workflows that run in **EPI2ME Desktop** but analyse **Illumina/DNBSEQ short reads**: germline and somatic
panels and exomes (capture, amplicon, UMI), with CNV/SV/MSI/TMB, ACMG/AMP and AMP-tier suggestions, HPO ranking and an
offline single-file HTML report with a printable case report. Later: bacterial isolates, metagenomics.
Non-profit, **education and research use only, not for clinical use**. Only free/open or free-for-non-commercial tools and data.
Docs: `docs/INSTALL.md`, `docs/USER_MANUAL.md`, `docs/TEACHING_GUIDE.md`, `docs/WORKFLOW.md` (technical), `docs/PLAN.md`.
Laptop survey: `docs/INVENTORY.md`, `scripts/afla-inventory.sh`, `scripts/afla-gpu-check.sh`.

## Development rules
- Parameters: edit `nextflow.config`, then `scripts/make_schema.py` (never hand-edit the two `nextflow_schema.json`).
- Code must run on Nextflow 23.04 (bundled with EPI2ME) AND pass `nextflow lint` of Nextflow 25+ (strict syntax: no `for`
  loops, no calling closures stored in variables; use top-level functions).
- Before pushing: `python3 tests/test_units.py`, a small run (`scripts/afla-testdata.sh` data), `node tests/report_smoke.js`.
- After `git pull`, refresh EPI2ME's copies: `bash scripts/install-epi2me.sh`.

## The machine (when running locally in WSL)
- ASUS TUF F15, Windows 11, WSL2 Ubuntu, Docker Desktop (WSL integration), EPI2ME Desktop installed.
- i7 13th gen 16 cores, 64 GB RAM, **8 GB NVIDIA GPU** (use it: DeepVariant-GPU, SpliceAI), 1 TB disk (187 GB free on C: at the 2026-09-28 inventory; WSL virtual disk needs periodic compaction).
- **Zero budget**: no extra storage, no paid cloud, no HPC. Overflow = free public Galaxy servers.
- Reference: **GRCh38 only**. There is **no BGI exome and no project exome yet**; do not assume one. First test data: TruSight Myeloid
  NA12877/Horizon MiSeq run in `C:\Users\fjbuk\Downloads\BaseSpace\` (public reference material), then GIAB/public samples.
- Some databases, tools and containers were downloaded earlier: **inventory and reuse them before downloading anything**.

## Rules when working on the user's laptop
1. Start read-only: run `scripts/afla-inventory.sh` and `scripts/afla-gpu-check.sh`, and summarise keep/update/re-download/delete.
2. **Ask before** deleting or moving anything, any download >1 GB, installing system packages, or editing `.wslconfig`/Docker settings.
3. Check free disk before every large download or run (`df -h /mnt/c`: real Windows free space; `df -h ~` only shows the virtual disk limit); keep ≥15 GB headroom.
4. Never install a Linux NVIDIA driver inside WSL (the Windows driver provides GPU support).
5. Never commit sequencing data, VCFs from real people, or licence-restricted databases to git (see `.gitignore`).
6. Read FASTQs in place (e.g. `/mnt/d/...`); do not copy them into WSL.
7. The user is a clinician-educator, not a Linux specialist: explain each step briefly in plain language.
