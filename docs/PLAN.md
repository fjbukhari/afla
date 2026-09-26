# Plan: Illumina NGS analysis in EPI2ME Desktop, laptop + online hybrid

Status: **proposal v2, Stage 0 not started**. Education and research use only, not for clinical use.

Changes since v1:
- No hardware purchases → a **disk-lean laptop design** plus an **online path for heavy jobs**.
- The existing HTML tertiary tool can't be shared → **we build a new tertiary analysis tool ("AFLA Interpreter")**.

## 1. Guiding decisions

1. **Write the workflows once and run them anywhere.** They are Nextflow + containers following the EPI2ME
   `wf-template` layout. The same `nextflow_schema.json` that draws the EPI2ME form also draws
   the launch form on Seqera Platform, and the same code runs on the laptop, a cloud VM, or a university
   HPC (`-profile local | cloud | hpc`).
2. **Start at any stage:** `start_from = fastq | bam | vcf | annotated`, auto-detected from file type.
3. **Move small files, not big ones.** The heavy primary steps (FASTQ → CRAM/VCF) run wherever there is
   space. The VCF (a few MB) comes back to the laptop, where all tertiary work happens, offline.
4. **Licensing:** only free/open or free-for-non-commercial resources. Registration-licensed data is
   downloaded by each user and never redistributed. Every report carries a "not for clinical use" banner
   and lists tool and database versions.

## 2. What fits on the laptop (100 GB free, no upgrades)

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

**Verdict:** the laptop can run **panels comfortably**, **one exome at a time** (tight; FASTQ deleted or archived
after it is converted to CRAM), and **all VCF-onward/tertiary analysis**. Batches of exomes, somatic WES,
WGS, and metagenomics with large databases go online (§3).

Laptop housekeeping built into the workflows: CRAM output instead of BAM, `cleanup = true`
for Nextflow work dirs, a periodic "compact WSL disk" step (the WSL virtual disk does not shrink by itself), and
WSL memory capped at ~52 GB. The GPU is optional (DeepVariant runs fine on CPU for exomes, ~1 h).

## 3. Online options for heavy jobs

| Option | Cost | Runs *our* workflows? | GUI | Best for |
|---|---|---|---|---|
| **A. Cloud VM (AWS/GCP/Azure) via Seqera Platform or Nextflow CLI** | ~US$1–3 per exome on spot/preemptible 16 vCPU/64 GB VMs + storage; research/education **credit programmes** can cover this | Yes, identical | Seqera web launch form from the same schema | Batches, WES/WGS, somatic, metagenomics |
| **B. University / national HPC** | Usually free for academics | Yes (`-profile hpc`, Apptainer) | CLI (or Seqera if the site supports it) | If you have access, this is the best free route |
| **C. Public Galaxy servers** (usegalaxy.eu/.org/.org.au) | Free; a few hundred GB quota; free **Training Infrastructure as a Service (TIaaS)** queues for classes | No, Galaxy's own tools (BWA-MEM2, DeepVariant/FreeBayes, Mutect2, Kraken2 with prebuilt DBs …) | Web GUI | Zero-budget teaching; export the VCF → AFLA Interpreter |
| D. Cloud VM with remote desktop running EPI2ME for Linux | Pay while it is on, even idle | Yes | Same EPI2ME GUI | Only if EPI2ME-look is essential |
| ✗ Colab/Kaggle, BaseSpace/DRAGEN | Session/disk limits; commercial credits | No | | Not recommended |

**Recommendation:**
1. **Hybrid (A or B) + laptop.** The laptop runs EPI2ME for panels, single exomes and all tertiary work.
   Heavy runs use the *same* workflows on a cloud VM or HPC, and only the CRAM/VCF/report comes back.
   Apply for cloud research/education credits. If a university HPC is available, use that first.
2. **Galaxy (C) as the free fallback and teaching companion.** Students can do FASTQ → VCF on Galaxy with
   Galaxy Training Network tutorials, then load the VCF into the AFLA Interpreter. No cost at all.

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

Optional heavy add-ons on the cloud/HPC path: full Exomiser, CADD, SpliceAI precomputed scores, dbNSFP.

## 5. Workflows

| Workflow | Laptop | Online | Stage |
|---|---|---|---|
| `wf-illumina-germline` (this repo): fastp → bwa → markdup → DeepVariant/GATK → annotate → Interpreter | panels, 1 exome | batches, WGS | 1–3 |
| `wf-illumina-somatic`: Mutect2 (+ GATK PoN), CNVkit, MSIsensor-pro, TMB | panels | WES | 4 |
| `wf-illumina-bacterial`: Shovill, QUAST, mlst, AMRFinderPlus, MOB-suite | ✓ | batches | 5 |
| `wf-illumina-metagenomics`: Hostile, Kraken2/Bracken (8 GB DB), Krona | small DB | large DBs | 5 |

## 6. Staged roadmap (revised)

| Stage | Deliverable | Done when |
|---|---|---|
| **0. Foundations** | Repo skeleton in EPI2ME layout; minimal workflow imported into EPI2ME; `setup-references --lean`; `local`/`cloud`/`hpc` profiles; laptop setup guide | Imported workflow runs from the EPI2ME GUI; lean references use <35 GB |
| **1. AFLA Interpreter v1** (first, because it delivers value immediately with *existing* VCFs) | Standalone HTML: VCF load, filters, panels, variant cards, live gnomAD/ClinVar lookup, case report | A GIAB or public teaching VCF goes through filtering → report entirely in the browser |
| **2. Germline workflow** | FASTQ/BAM/VCF entry, QC, DeepVariant, lean annotation bundle, Interpreter as the EPI2ME report; hap.py benchmark on GIAB HG002 exome | HG002 SNV F1 > 0.99 in high-confidence capture regions |
| **3. Tertiary depth** | ACMG assistant, HPO matching, trio/inheritance, CNV (ExomeDepth/CNVkit), ROH, teaching mode; cloud profile tested end to end | Solved teaching cases rank the causal variant in the top 5 |
| **4. Somatic** | workflow + Interpreter somatic mode | Public reference samples (e.g. SEQC2) reproduce expected calls |
| **5. Microbiology & metagenomics** | two workflows + HTML reports | Reference isolates/mock communities give the expected results |

## 7. Open questions

1. Laptop OS (Windows 11 → WSL2)?
2. Does the institution have an HPC cluster, or can you apply for cloud research/education credits?
3. Capture kits/panels in use (BED files) and typical number of samples per class.
4. GRCh38 only (recommended), or GRCh37 VCF input too?
