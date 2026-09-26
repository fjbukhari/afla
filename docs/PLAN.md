# Plan: Illumina NGS analysis inside EPI2ME Desktop

Status: **proposal, Stage 0 not started**. Education and research use only, not for clinical use.

## 1. How this fits EPI2ME Desktop

EPI2ME Desktop is a GUI launcher for **Nextflow** workflows running in **Docker**
containers. The ONT workflows (wf-human-variation, wf-metagenomics, …) are ordinary
GitHub repositories that follow the `epi2me-labs/wf-template` layout:

```
main.nf                 # Nextflow entry point
nextflow.config         # profiles, containers, resources
nextflow_schema.json    # drives the EPI2ME form (sections, file pickers, help text)
bin/ lib/ modules/      # helper scripts, Groovy helpers, processes
test_data/  docs/       # demo data button + docs tab
output: <wf>-report.html  # shown in the app's "Report" tab
```

EPI2ME Desktop has an **Import workflow → from GitHub URL** option. So nothing about
it is ONT-specific: if we write Illumina workflows in the same layout, they show up
in the app with the same form, progress view, and HTML report as the ONT ones.
**Stage 0 verifies this on the target laptop before anything else is built.**

## 2. Architecture

### 2.1 Workflows (one GitHub repo each, because EPI2ME imports a repo root)

| Workflow | Scope | Stage |
|---|---|---|
| `wf-illumina-germline` (this repo) | WES / panels / (later WGS): QC → align → call → annotate → prioritise → report | 1–3 |
| `wf-illumina-somatic` | tumour-only and tumour-normal panels/WES | 4 |
| `wf-illumina-bacterial` | isolate assembly, typing, AMR | 5 |
| `wf-illumina-metagenomics` | taxonomic profiling, host removal, AMR | 5 |

Shared pieces (container images, reference-download scripts, report library) live in
this repo or a small `afla-core` repo.

### 2.2 "Start from any stage"

A single `start_from` parameter (auto-detected from file extensions, overridable in
the form):

```
 FASTQ ──► fastp QC/trim ──► bwa-mem2 align ──► markdup ──► BAM/CRAM
                                                              │
 BAM/CRAM (start_from=bam) ──────────────────────────────────►┤
                                                              ▼
                                  coverage QC (mosdepth, HsMetrics, somalier)
                                                              ▼
                             DeepVariant (GPU) / GATK HaplotypeCaller → gVCF/VCF
                                                              │
 VCF / gVCF (start_from=vcf) ────────────────────────────────►┤
                                    normalise (bcftools norm, left-align, split)
                                                              ▼
                                   VEP + plugins (gnomAD, ClinVar, REVEL,
                                   AlphaMissense, SpliceAI, LOFTEE, …)
                                                              │
 Annotated VCF (start_from=annotated_vcf) ───────────────────►┤
                                                              ▼
              prefilter → virtual panel / HPO prioritisation (Exomiser)
                     → ACMG-assist evidence → interactive HTML report
```

Every stage publishes its outputs (BAM, VCF, annotated VCF, TSV/JSON), so a run can be
stopped and resumed from any of them; Nextflow `-resume` also works inside EPI2ME.
GRCh37 VCFs are accepted and lifted to GRCh38 (bcftools +liftover / CrossMap).

### 2.3 Tool choices (all free for non-commercial / academic use)

**Primary analysis (germline)**
- QC/trim: `fastp`; summary: `MultiQC`
- Alignment: `bwa-mem2` (prebuilt index; building it needs ~90 GB RAM, so it is downloaded, not built) with `bwa` as fallback; `samtools`, Picard/GATK `MarkDuplicates`
- Variant calling: **DeepVariant** (WES/panel models, BSD-3; `-gpu` image uses the 8 GB GPU), with **GATK4 HaplotypeCaller** as the alternative, for teaching comparisons
- Coverage/QC: `mosdepth` (per-target, % ≥20×), Picard `CollectHsMetrics`, `somalier` (sex, relatedness, ancestry)
- CNV (WES/panels): `ExomeDepth` (needs a reference set of ~10+ samples from the same capture kit) and/or `CNVkit`
- Runs of homozygosity: `bcftools roh` (useful in consanguineous cohorts)
- Trios: joint genotyping + `slivar` for de novo / compound-het / X-linked

**Annotation / tertiary**
- `Ensembl VEP` with offline cache (includes gnomAD AFs), plus plugins: ClinVar (custom VCF), REVEL, AlphaMissense, SpliceAI, LOFTEE, dbNSFP (academic), CADD (non-commercial, optional because files are large)
- SpliceAI can also be **run locally on the GPU for filtered candidates only**, instead of downloading tens of GB of precomputed scores
- Phenotype-driven prioritisation: **Exomiser** (AGPL) with HPO terms entered in the EPI2ME form
- Gene panels: Genomics England / Australian **PanelApp** (open) as "virtual panels" applied to exome data; ClinGen gene–disease validity and dosage; Orphanet; HPO
- ACMG/AMP assistance: automated evidence codes (PVS1, PM2/BA1/BS1 with gnomAD, PP3/BP4 using ClinGen-calibrated REVEL/AlphaMissense/SpliceAI thresholds, PS1/PM5, ClinVar), in the style of InterVar (free for non-commercial use), **always shown as suggestions for the student to accept or reject**
- Report: your existing HTML tool (see §4)

**Somatic (Stage 4)**: GATK `Mutect2` (+ public GATK panel of normals and germline resource), `FilterMutectCalls`, `CNVkit`, `MSIsensor-pro`, TMB, VEP + CIViC (CC0), Cancer Hotspots, OncoKB (free academic token), COSMIC (academic, each user downloads it); AMP/ASCO/CAP tiering in the report.

**Microbiology (Stage 5)**
- Isolates: fastp → `Shovill`/SPAdes → QUAST → `mlst`, `AMRFinderPlus`, `abricate`, `MOB-suite`, species-specific typers (e.g. Kleborate), optional snippy for outbreak SNP distance
- Metagenomics: host read removal (`Hostile`) → `Kraken2` + `Bracken` (Standard-8/PlusPF-8 DB, ~8 GB) → Krona/HTML report; optional `MetaPhlAn`; AMR via `AMRFinderPlus` on reads/contigs
- 16S amplicons (optional): DADA2 with SILVA (free academic licence)

### 2.4 Licensing rule

Anything under a non-commercial or registration licence (CADD, dbNSFP academic,
SpliceAI precomputed scores, OncoKB, COSMIC, InterVar, and so on) is **never baked
into containers or committed to git**. A `setup-references` step downloads it on
each machine after the user has accepted its terms. Open resources (GRCh38, VEP
cache, gnomAD, ClinVar, PanelApp, HPO) are fetched automatically. Every report carries
an "education only, not for clinical use" banner and lists each database version it used.

## 3. Laptop plan (ASUS TUF F15: i7-13th gen 16 cores, 64 GB RAM, 8 GB NVIDIA, 1 TB with ~100 GB free)

EPI2ME Desktop on Windows runs workflows through **WSL2 + Docker**.

- `.wslconfig`: `memory=52GB`, `processors=14`, `swap=16GB`, to leave room for Windows.
- NVIDIA driver with WSL CUDA support + Docker GPU (`--gpus all`); verify with `nvidia-smi` inside a container.
- Nextflow resource caps in the `local` profile: max 14 CPUs, 48 GB RAM, 1 GPU.

**Disk is the real bottleneck.** Rough footprint:

| Item | Size |
|---|---|
| GRCh38 analysis set + bwa-mem2/bwa + DeepVariant indexes | ~20 GB |
| VEP cache GRCh38 (+ ClinVar, REVEL, AlphaMissense) | ~30 GB |
| Exomiser data (hg38 + phenotype) | ~40–60 GB |
| Docker images (all workflows) | ~20–30 GB |
| Kraken2 Standard-8 | ~8 GB |
| Per exome, working space (FASTQ + BAM + Nextflow work dir) | ~30–50 GB |

**Recommendation:** buy a **2 TB external NVMe SSD (USB 3.2 Gen2 / USB4)**. Move the
Docker/WSL virtual disk there, and put references and Nextflow work dirs there as well.
Keep data inside the WSL ext4 filesystem rather than `/mnt/c`, because cross-filesystem I/O is much slower. Clean
`work/` dirs automatically after successful runs.

Expected runtimes on this laptop (rough): panel 10–20 min; exome ~2–3 h end to end
(alignment ~1 h, DeepVariant 30–60 min with GPU-accelerated calling, annotation ~10 min);
tertiary/report minutes. NVIDIA Parabricks is officially ≥16 GB GPU, so it is not a target.

## 4. Integrating the existing HTML annotation/report tool

Planned approach, to be confirmed once the tool is shared:
1. The workflow produces the annotated, prefiltered variant table in the **exact
   format your tool already reads** (VCF/TSV/JSON).
2. The tool gets **embedded as the workflow's final report** (single self-contained HTML
   with the data injected), so it opens in EPI2ME's Report tab and also as a standalone file.
3. Live ClinVar/gnomAD lookups stay as an **optional online mode**. The default becomes the
   offline, versioned annotations from the pipeline, which makes classroom results reproducible.
4. The tool also works on its own for users who only have a VCF (the `start_from=annotated_vcf` path).

## 5. Staged roadmap

| Stage | Deliverable | Done when |
|---|---|---|
| **0. Foundations** | WSL2/Docker/GPU setup guide; minimal "hello" workflow imported into EPI2ME from this repo; `setup-references` script (GRCh38, indexes, VEP cache) | Hello workflow runs from the EPI2ME GUI and the GPU is visible in a container |
| **1. Germline core** | FASTQ/BAM/VCF → QC → DeepVariant/GATK → normalised VCF + QC report; demo data (GIAB HG002 exome subset); **hap.py benchmarking** vs GIAB truth (a good teaching exercise) | HG002 exome SNV F1 > 0.99 in GIAB high-confidence regions within the capture |
| **2. Annotation + report** | VEP + plugins; prefiltering; your HTML tool embedded as the report; start from VCF / annotated VCF | Existing VCFs from other pipelines produce a report without re-running upstream steps |
| **3. Tertiary / clinical-style** | HPO input + Exomiser; PanelApp virtual panels; ACMG-assist; CNV (ExomeDepth/CNVkit); ROH; trio mode; exportable teaching report (PDF/HTML) | Known solved teaching cases rank the causal variant in the top 5 |
| **4. Somatic** | `wf-illumina-somatic` (tumour-only + paired), CNV, MSI, TMB, AMP tiers | SEQC2 / public reference samples reproduce the expected calls |
| **5. Microbiology & metagenomics** | `wf-illumina-bacterial`, `wf-illumina-metagenomics` | Reference isolates give the correct MLST/AMR; mock community profiles within tolerance |

Engineering conventions throughout: pinned container versions; nf-core modules (MIT) reused where
possible instead of rewriting processes; small CI test data run on GitHub Actions for every
change; every report lists the version of each tool and database it used.

## 6. Alternatives considered

- **Run nf-core pipelines (sarek, raredisease, taxprofiler, mag, bacass) directly.** These are mature and
  well validated, and can be launched from the command line or the Seqera Platform (free tier) today.
  In EPI2ME they may import, but the forms are huge and default resources/references (iGenomes, AWS) are
  not laptop-friendly. **Plan: reuse their modules and logic inside lean EPI2ME-style workflows**, and point
  advanced students at the full nf-core pipelines.
- **Galaxy (local Docker).** It has the richest *teaching* ecosystem (Galaxy Training Network has exome, somatic,
  and metagenomics tutorials), but it is heavier on a laptop and has a different UX from EPI2ME. It works well alongside
  this project for tool-by-tool lessons; EPI2ME stays the single push-button interface for ONT and Illumina.
- **Cloud/HPC later.** The same Nextflow workflows run unchanged on a university HPC or cloud via profiles, so
  scaling up after the laptop phase does not require rework.

## 7. Open questions for the project owner

1. Laptop OS: Windows 11 (→ WSL2) or Linux?
2. Capture kits / panels in use (need their BED files) and expected sample volumes.
3. Reference build: GRCh38 only (recommended), or GRCh37 support as well?
4. Share the existing HTML annotation/report tool (add to `report/` in this repo).
5. OK to use one repo per workflow (EPI2ME imports repo roots), with this repo as the germline workflow?
6. Is an external SSD possible?
