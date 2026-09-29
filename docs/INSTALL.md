# AFLA installation guide (Windows 11 laptop)

Education and research use only. Allow **2–4 hours** the first time (most of it is waiting for downloads).
You need about **60 GB of free disk** for the full install (about 25 GB with the lean option), plus room for your data.

What you will have at the end:

```
Windows 11
 ├─ EPI2ME Desktop  ──runs──►  Nextflow workflows "AFLA germline" / "AFLA somatic"
 ├─ Docker Desktop  ──runs──►  the tools in containers (bwa, GATK, VEP, CNVkit, ...)
 └─ WSL2 Ubuntu     ──holds──► the AFLA code, helper scripts, (optionally) Claude Code
C:\Users\<you>\afla-resources  = reference genome + annotation databases (one folder)
```

---

## Step 1. WSL2 and Ubuntu

1. Open **PowerShell as administrator** and run `wsl --install -d Ubuntu`. Restart when asked.
2. Open **Ubuntu** from the Start menu and create a user name and password (remember the password: `sudo` asks for it).
3. Give WSL enough memory: create `C:\Users\<you>\.wslconfig` with Notepad:
   ```ini
   [wsl2]
   memory=52GB      # on a 64 GB laptop; use about 75% of your RAM
   processors=14    # leave 2 cores for Windows
   swap=16GB
   ```
   then in PowerShell: `wsl --shutdown` (Ubuntu restarts with the new limits next time).

## Step 2. Docker Desktop

1. Install Docker Desktop from docker.com (free for education and small non-profit use; check their current terms).
2. Settings → General → **Use the WSL 2 based engine** ✔.
3. Settings → Resources → WSL integration → **Ubuntu** ✔ → Apply & restart.
4. In Ubuntu, check: `docker run --rm hello-world`.

## Step 3. The GPU (optional, for DeepVariant)

Install the latest **Windows** NVIDIA driver (Game Ready or Studio). **Do not install any NVIDIA driver inside Ubuntu.**
Then check everything with:
```bash
bash ~/afla/scripts/afla-gpu-check.sh
```

## Step 4. EPI2ME Desktop

Install from the Oxford Nanopore website (free). Open it once so it creates its folders.

## Step 5. The AFLA code

In Ubuntu:
```bash
sudo apt update && sudo apt install -y git curl rsync python3
cd ~
git clone -b claude/epi2me-illumina-ngs-pipeline-6qkr8o https://github.com/fjbukhari/afla.git
```
(If the repository is private, first run `sudo apt install -y gh && gh auth login`.)
To update later: `cd ~/afla && git pull`.

## Step 6. Resources (reference genome and databases)

```bash
cd ~/afla
bash scripts/afla-setup.sh            # asks before each large download; shows sizes and licences
```
It creates **`C:\Users\<you>\afla-resources`** (a Windows folder, so EPI2ME can see it) with:

| Folder | Content | Size |
|---|---|---|
| `reference/` | GRCh38 no-alt analysis set + bwa index | ~9 GB |
| `vep/` | Ensembl VEP 115 cache (includes gnomAD v4.1 frequencies), Ensembl FASTA, plugins | ~30 GB |
| `clinvar/` | ClinVar VCF + amino-acid index (ACMG PS1/PM5) | 0.2 GB |
| `constraint/`, `hpo/`, `panelapp/` | gene constraint, phenotype ontology, gene panels | 0.3 GB |
| `revel/`, `alphamissense/` | missense predictors (free for non-commercial use) | 1.4 GB |
| `somatic/`, `civic/` | Mutect2 resources, CIViC cancer evidence | 3.5 GB |
| `annotation/`, `targets/`, `msi/` | gene models, an example exome BED, microsatellites | 1 GB |

Useful options: `--only reference,clinvar` (some parts), `--skip revel`, `--lean` (no 30 GB VEP cache; gene models only),
`--dir D:/afla-resources` (another drive), `--yes` (no questions). Already downloaded files are **kept**, so you can
re-run it any time (ClinVar is refreshed when older than 60 days).

**Already have files?** Set "Resources folder" to your existing folder: the workflow also recognises the older
`afla-data` layout (`reference/`, `annotation/vep_cache`, `annotation/clinvar`, ...). Or give individual files in the form.

SpliceAI precomputed scores need a free Illumina login: see `bash scripts/afla-setup.sh --only spliceai`.

## Step 7. Put AFLA into EPI2ME

**Option A (this laptop, two entries "AFLA germline" + "AFLA somatic"):**
```bash
bash ~/afla/scripts/install-epi2me.sh
```
Restart EPI2ME. Re-run after every `git pull`.

**Option B (any computer with EPI2ME):** EPI2ME → Workflows → **Import workflow** → paste
`https://github.com/fjbukhari/afla` → choose the latest version. You get "AFLA germline"; its form has an
**Analysis mode** switch for somatic. (The repository must be public, or the computer's GitHub account must have access.)

## Step 8. First test run (10–20 minutes)

```bash
bash ~/afla/scripts/afla-testdata.sh /mnt/c/Users/<you>/afla-testdata
```
Then in EPI2ME → AFLA germline → Run:
- FASTQ folder: `C:\Users\<you>\afla-testdata\fastq`
- Sample sheet: `C:\Users\<you>\afla-testdata\trio.csv`
- Resources folder: `C:\Users\<you>\afla-resources`
- Reference genome: `C:\Users\<you>\afla-testdata\ref\chr20.fa` (small test reference; overrides the one in resources)
- Target regions: `C:\Users\<you>\afla-testdata\ref\chr20.targets.bed`

Open the **Report** tab when it finishes. See `docs/USER_MANUAL.md` for what everything means.

## Other computers (students)

- Minimum: 4 CPU cores, **12 GB RAM** (16 GB better), 60 GB free disk, Windows 10/11, macOS or Linux with Docker and EPI2ME.
- CPU and memory are detected automatically; nothing to edit.
- Copy the `afla-resources` folder from a USB disk instead of downloading it again (it is portable).
- No Docker? Galaxy (usegalaxy.eu) can produce the VCF; AFLA can then start from the VCF (annotation + report only).

## Optional: Claude Code inside Ubuntu (an assistant that can run and fix things with you)

```bash
curl -fsSL https://claude.ai/install.sh | bash
sudo ln -sf ~/.local/bin/claude /usr/local/bin/claude     # makes "claude" work in every new window
cd ~/afla && claude
```
Needs a Claude Pro/Max plan or API key. It reads `CLAUDE.md` in this folder and asks before changing anything.

## Troubleshooting installation

| Problem | Fix |
|---|---|
| `claude: command not found` in new windows | `sudo ln -sf ~/.local/bin/claude /usr/local/bin/claude` |
| `docker: command not found` in Ubuntu | Docker Desktop → Settings → Resources → WSL integration → Ubuntu ✔ |
| GPU not seen in containers | Update the Windows NVIDIA driver and Docker Desktop, then `wsl --shutdown` |
| EPI2ME cannot see files | Put data under `C:\...` (not only inside Ubuntu); avoid spaces and `+` in folder names |
| Disk full | Delete `work` folders of old runs; in PowerShell `wsl --shutdown` then compact the WSL disk (Docker Desktop → Troubleshoot → Clean/Purge data, or `Optimize-VHD`) |
| Download interrupted | Just re-run `afla-setup.sh`; it resumes |
