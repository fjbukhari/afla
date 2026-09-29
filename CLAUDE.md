# AFLA: context for Claude Code

## What this project is
Nextflow workflows that run in **EPI2ME Desktop** but analyse **Illumina short reads** (human germline
exomes and panels first; later somatic, bacterial isolates, metagenomics), plus **AFLA Interpreter**, an offline
single-file HTML tool for tertiary analysis and teaching-style reporting.
Non-profit, **education and research use only, not for clinical use**. Only free/open or free-for-non-commercial tools and data.
Full plan: `docs/PLAN.md`. Laptop survey: `docs/INVENTORY.md`, `scripts/afla-inventory.sh`, `scripts/afla-gpu-check.sh`.

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
