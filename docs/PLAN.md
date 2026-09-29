# Plan: Illumina short-read NGS analysis in EPI2ME Desktop, zero-cost

Status: **proposal v3, Stage 0 not started**. Education and research use only, not for clinical use.

Constraints (confirmed):
- **Zero budget:** no hardware upgrades, no paid cloud, no university HPC (not available in Pakistan).
- **Laptop:** Windows 11, 64 GB RAM, 16 cores, 8 GB NVIDIA GPU (RTX 4070 Laptop), 1 TB disk. Inventory on 2026-09-28 found
  187 GB free on C: before clean-up; the plan still keeps the lean design so it works on laptops with less space.
- **Reference:** GRCh38 only.
- **First data:** no project-specific exome yet. Development and testing use public reference samples: the TruSight Myeloid
  NA12877/Horizon panel run already on the laptop (Illumina MiSeq), GIAB exomes and public teaching VCFs.
- The existing HTML tertiary tool can't be shared → **we build a new one ("AFLA Interpreter")**.

Compute model: **laptop for everything, one exome at a time; free public Galaxy servers as overflow.**

## 1. Guiding decisions

1. **Write the workflows once, in the portable format.** They are Nextflow + containers following the EPI2ME
   `wf-template` layout. They run in EPI2ME Desktop on the laptop, and the same code can later run on any
   Linux server or cloud unchanged if resources ever become available.
2. **Start at any stage:** `start_from = fastq | bam | vcf | annotated`, auto-detected from file type.
3. **Move small files, not big ones.** When FASTQ → VCF is done on Galaxy, only the VCF (a few MB) comes back.
   All tertiary work happens on the laptop, offline.
4. **Licensing:** only free/open or free-for-non-commercial resources. Registration-licensed data is
   downloaded by each user and never redistributed. Every report carries a "not for clinical use" banner
   and lists tool and database versions.

## 2. What fits on the laptop (lean design, sized for ~100 GB free)

The v1 design needed ~150 GB+ (full VEP cache, Exomiser data, bwa-mem2 index). The lean design:

| Component | Lean choice | Size |
|---|---|---|
| Reference | GRCh38 no-alt analysis set + `bwa` index (not bwa-mem2: its index is 3× larger and needs ~90 GB RAM to build) | ~9 GB |
| Containers | fastp, bwa/samtools, DeepVariant, bcftools, VEP, report | ~12 GB |
| Gene annotation | Ensembl VEP in **GTF + FASTA mode** (no 25 GB cache) | <1 GB |
| **AFLA exome annotation bundle** | gnomAD v4 exome AF/AC/hom (+ genome AF for exome regions), ClinVar, REVEL, AlphaMissense, gnomAD constraint, **restricted to coding exons ±50 bp** (bcftools annotate) | ~5–8 GB |
| Knowledge | PanelApp panels, HPO ontology + gene annotations, ClinGen validity/dosage, Orphanet | <1 GB |
| **Fixed total** | | **~30 GB** |
| One exome in flight | FASTQ ~10 GB + CRAM ~5 GB + temp (streamed, work dir auto-cleaned) | ~25–35 GB |

**Verdict:** the laptop runs **panels comfortably**, **one exome at a time** (FASTQs are read in place, not
copied), and **all VCF-onward/tertiary analysis**. Class-wide batches and big-database metagenomics can
overflow to free Galaxy servers (§3.2).

Laptop housekeeping built into the workflows: CRAM output instead of BAM, `cleanup = true`
for Nextflow work dirs, a periodic "compact WSL disk" step (the WSL virtual disk does not shrink by itself), and
WSL memory capped at ~52 GB. The GPU is used when available (§3.4).

## 3. Zero-cost compute

### 3.1 Laptop: "one exome at a time" recipe
- **FASTQs are read where they already are** (e.g. `C:\\Users\\<you>\\Downloads\\…` via `/mnt/c`), never copied into WSL.
  This is slower I/O, but it saves 10–15 GB per sample.
- Alignment is **streamed** (`bwa mem | samtools sort` → CRAM) with no intermediate SAM/BAM. Duplicate marking
  is done on the fly (`samtools markdup`).
- Variant calling is **restricted to the capture BED ±100 bp**, which is faster and needs less temporary space.
- The Nextflow `work/` directory is deleted on success. Outputs kept per exome: CRAM (~4–6 GB), gVCF/VCF, QC, report.
- After a batch, a helper script shrinks the WSL virtual disk (`wsl --shutdown` + `Optimize-VHD`/`diskpart compact`).
- Budget: ~30 GB fixed (references, containers, lean annotation) + ~25 GB peak per exome. This fits in 100 GB with margin.
  Old CRAMs can be archived to any spare USB stick or phone storage if needed.
- With the GPU (§3.4), DeepVariant on an exome takes ~35–45 min (~1 h on CPU only). An exome end to end is roughly 3 h, so it can run overnight.

### 3.2 Free overflow: public Galaxy servers
usegalaxy.eu / usegalaxy.org / usegalaxy.org.au are free, need no install, and give a few hundred GB of quota each. They also offer
**free TIaaS** (Training Infrastructure as a Service) queues for classes. Use them when the laptop is busy, for
whole-class exercises, or for metagenomics with big databases. Students do FASTQ → VCF there (BWA-MEM2,
DeepVariant/FreeBayes, Kraken2 …), download the VCF (a few MB) and open it in the AFLA Interpreter on any computer.
Tip: if the sequencing provider gives download links for the data, give Galaxy the URL directly instead of uploading over a slow connection.

### 3.3 Not used
Paid cloud, Parabricks (needs a ≥16 GB GPU), and free-tier ARM cloud VMs (most bioinformatics containers are
x86-only). Colab/Kaggle are ruled out by disk and session limits.

### 3.4 Using the GPU (8 GB NVIDIA, via WSL2 + Docker Desktop)
Already installed on the laptop: Ubuntu (WSL2), Docker Desktop, EPI2ME Desktop, and some databases (to be inventoried).
The GPU is reached through the **Windows** NVIDIA driver; no Linux driver goes inside WSL. Containers get it with
`--gpus all`. `scripts/afla-gpu-check.sh` verifies this end to end.

Where the GPU is used (all free, and all fit in 8 GB VRAM):
| Step | Tool | Benefit |
|---|---|---|
| Variant calling | **DeepVariant GPU image** (`google/deepvariant:<ver>-gpu`) | `call_variants` several times faster. `make_examples` stays CPU-bound, so an exome goes from ~1 h to ~35–45 min |
| Splice prediction | **SpliceAI** (TensorFlow GPU) on filtered candidates | seconds instead of minutes; avoids downloading tens of GB of precomputed scores |
| Later / optional | ONT basecalling in EPI2ME (Dorado) if nanopore data is added | large |

Not possible on 8 GB: NVIDIA Parabricks (needs ≥16 GB). Alignment therefore stays on CPU (bwa, 14 threads).
The workflows have a `use_gpu` switch (default **on** when a GPU is detected), which gives GPU processes
`containerOptions '--gpus all'`. With the switch off, identical CPU containers are used. To save disk, only the GPU
DeepVariant image is kept (it also runs on CPU).

## 3a. Data from other providers (optional support)
- Some providers (e.g. BGI/MGI) sequence on **DNBSEQ**. The FASTQ format is the same as Illumina; headers differ and the read
  group uses `PL:DNBSEQ`. fastp handles MGI adapters. This is optional support, not a current priority; if DNBSEQ data is
  used, DeepVariant should first be checked on public DNBSEQ GIAB data with hap.py.
- **Unknown capture kit → auto-detection:** for exomes delivered without a kit name, the workflow measures on-target coverage against candidate BEDs
  (Agilent SureSelect V5/V6/V7/V8, IDT xGen v1/v2, Twist Exome 2.x, BGI/MGI Exome V4/V5 where available) and
  reports the best match. Agilent BEDs need a free SureDesign login, so each user downloads them once. If none matches, it
  falls back to a **data-derived target BED** (regions ≥20× from `mosdepth`, intersected with GENCODE coding exons ±50 bp).
- Providers often also deliver **BAM and VCF**. Those enter directly through `start_from = bam | vcf`.

## 4. AFLA Interpreter (new tertiary analysis tool)

A **single self-contained HTML file**: no server, no install, works offline. It is used in two ways:
- as the **final report** of the germline workflow (opens in EPI2ME's Report tab, data embedded);
- **standalone**: open in any browser and drop in a VCF from *any* source (our pipeline, Galaxy, DRAGEN, GATK…).

**Inputs**
- VCF/gVCF (plain or VEP/SnpEff-annotated, GRCh38 or GRCh37), optional PED (trio), HPO terms, panel choice.
- Un-annotated VCFs are first annotated by the `annotate` entry point (laptop), or annotated live online
  (gnomAD GraphQL API, ClinVar E-utilities, Ensembl VEP REST) in small batches after pre-filtering.

**Features (in build order)**
1. QC panel: variant counts, Ti/Tv, het/hom ratio, sex check, coverage of panel genes (when BAM/CRAM QC is available).
2. Pre-filter presets: quality (GQ/DP/AB), population frequency (gnomAD AF/popmax/hom counts),
   consequence, ClinVar status, inheritance mode (AD/AR/compound-het/X-linked/de novo with a trio).
3. Gene focus: PanelApp virtual panels (England & Australia), custom gene lists, HPO → gene matching
   with a phenotype-similarity score ("Exomiser-lite" that works offline).
4. Variant cards: transcript (MANE Select), HGVS c./p., gnomAD, ClinVar (stars, conditions),
   REVEL / AlphaMissense / SpliceAI, gene constraint (pLI/LOEUF), ClinGen validity/dosage, links out.
5. **ACMG/AMP assistant:** auto-suggested codes (PVS1 decision tree, PM2/BA1/BS1/BS2, PP3/BP4 using the ClinGen-calibrated
   REVEL/AlphaMissense/SpliceAI thresholds, PS1/PM5, PM1 hotspots, BP7 …) that the student accepts or rejects.
   A points-based combiner (Tavtigian 2020) gives the classification, and the evidence behind every code is shown.
6. Case report: selected variants, evidence, interpretation notes, methods and database versions, and the
   disclaimer. Printable to PDF, and the whole session can be saved and reloaded (JSON) for marking.
7. Later: CNV and ROH tracks, a somatic mode (AMP/ASCO/CAP tiers, CIViC/OncoKB), and a teaching mode
   (hide the answer, compare the student's classification with the instructor key).

Offline-first: all core annotation comes from the lean local bundle. Live gnomAD/ClinVar/Ensembl lookups are an
optional extra when there is internet. Heavy add-ons (full Exomiser, CADD, SpliceAI precomputed scores, dbNSFP) are
optional because of disk. SpliceAI can instead be run locally on the GPU for the handful of filtered candidates.

## 5. Workflows

| Workflow | Laptop | Galaxy overflow | Stage |
|---|---|---|---|
| `wf-illumina-germline` (this repo): fastp → bwa → markdup → DeepVariant/GATK → annotate → Interpreter | panels, 1 exome at a time | class-wide FASTQ → VCF | 1–3 |
| `wf-illumina-somatic`: Mutect2 (+ GATK PoN), CNVkit, MSIsensor-pro, TMB | panels, 1 WES at a time | ✓ | 4 |
| `wf-illumina-bacterial`: Shovill, QUAST, mlst, AMRFinderPlus, MOB-suite | ✓ | ✓ | 5 |
| `wf-illumina-metagenomics`: Hostile, Kraken2/Bracken (8 GB DB), Krona | Kraken2 8 GB DB | large DBs | 5 |

## 6. Staged roadmap (revised)

| Stage | Deliverable | Done when |
|---|---|---|
| **0. Foundations** | Repo skeleton in EPI2ME layout; minimal workflow imported into EPI2ME; `setup-references --lean`; Windows 11/WSL2 setup guide with disk-compaction helper | Imported workflow runs from the EPI2ME GUI; lean references use <35 GB |
| **1. AFLA Interpreter v1** (first, because it delivers value immediately with *existing* VCFs) | Standalone HTML: VCF load, filters, panels, variant cards, live gnomAD/ClinVar lookup, case report | A GIAB or public teaching VCF goes through filtering → report entirely in the browser |
| **2. Germline workflow** | FASTQ/BAM/VCF entry, capture-kit auto-detection, QC, DeepVariant, lean annotation bundle, Interpreter as the EPI2ME report; hap.py benchmark on a GIAB exome | SNV F1 > 0.99 in high-confidence capture regions; one public exome completes on the laptop within the disk budget |
| **3. Tertiary depth** | ACMG assistant, HPO matching, trio/inheritance, CNV (ExomeDepth/CNVkit), ROH (important for consanguineous families), teaching mode; Galaxy → Interpreter handover guide | Solved teaching cases rank the causal variant in the top 5 |
| **4. Somatic** | workflow + Interpreter somatic mode | Public reference samples (e.g. SEQC2) reproduce expected calls |
| **5. Microbiology & metagenomics** | two workflows + HTML reports | Reference isolates/mock communities give the expected results |

## 7. Open questions

1. Which real panels/exomes (kit, sequencer) will be analysed first, once available?
2. Typical number of students/samples per class (decides whether Galaxy TIaaS is worth requesting).
