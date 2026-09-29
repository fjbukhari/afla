# AFLA user manual

**AFLA** analyses short-read DNA sequencing (Illumina, or DNBSEQ/BGI/MGI) of **gene panels and exomes** inside
**EPI2ME Desktop**, the same way EPI2ME runs Oxford Nanopore workflows: pick files in a form, click Run, read an
interactive report.

> **Education and research use only. Not for diagnosis or patient management.** Automatic suggestions (ACMG/AMP
> criteria, somatic tiers) are teaching aids and must be checked by a qualified person. Use pseudonymous sample names.

Contents: [1 What it does](#1-what-it-does) · [2 Choosing inputs](#2-inputs-where-the-analysis-starts) ·
[3 Library types](#3-library-types-capture-tagmentation-ligation-amplicon-umi) · [4 Germline](#4-germline-analysis) ·
[5 Somatic](#5-somatic-analysis) · [6 The report](#6-the-report) · [7 Outputs](#7-output-files) ·
[8 Command line](#8-command-line-no-gui) · [9 Troubleshooting](#9-troubleshooting) · [10 Limitations](#10-limitations) ·
[11 Licences](#11-data-sources-and-licences)

---

## 1. What it does

```
FASTQ ─► fastp QC ─► [UMI consensus] ─► bwa mem ─► [duplicates] ─► [primer clipping] ─► CRAM ─► coverage (mosdepth)
                                                                                         │
BAM/CRAM ────────────────────────────────────────────────────────────────────────────────┤
                                                                                         ▼
      germline: GATK HaplotypeCaller or DeepVariant (GPU)       somatic: GATK Mutect2 (tumour-only / tumour-normal)
      families: joint genotyping                                 + MSI (msisensor-pro) + TMB
      + ROH (bcftools)                                           
      both: CNV (CNVkit) · structural variants / DNA fusions (Manta)
                                                                                         │
VCF ─────────────────────────────────────────────────────────────────────────────────────┤
                                                                                         ▼
          Ensembl VEP annotation: genes, HGVS, gnomAD, ClinVar, REVEL, AlphaMissense, SpliceAI
                                                                                         ▼
  germline: ACMG/AMP evidence suggestions, HPO phenotype ranking, inheritance (de novo, compound het, ...)
  somatic : CIViC / OncoKB / COSMIC evidence, AMP/ASCO/CAP tier suggestions
                                                                                         ▼
          afla-report.html  (quality · variants · copy number · structural variants · case report · methods)
```

Two EPI2ME entries: **AFLA germline** (inherited variants; its "Analysis mode" can switch to somatic) and
**AFLA somatic** (tumours). Every step can be switched on or off in the form.

## 2. Inputs: where the analysis starts

Give **one** of:

| Input | Starts at | Use when |
|---|---|---|
| **FASTQ folder** | the beginning | raw data from the sequencer/provider (`*_R1_001.fastq.gz` + `*_R2_001.fastq.gz`, or `_1/_2`) |
| **BAM / CRAM** (file or folder) | after alignment | you already have aligned reads (GRCh38) |
| **VCF file** | annotation | a variant file from anywhere: a provider, Galaxy, DRAGEN, GATK, EPI2ME wf-human-variation (ONT)... |

Tips:
- One folder can hold many samples; lanes (`_L001`, `_L002`) of the same sample are merged automatically.
- Folder names: avoid spaces and `+`. Files are read in place (not copied).
- **Reference**: GRCh38 only. With a **Resources folder** (from `scripts/afla-setup.sh`) everything else is found automatically.
- **Target regions (BED)**: the capture kit/panel BED from the vendor. Needed for CNV and TMB; strongly recommended for everything.
  Unknown kit? Leave it empty: regions covered by the reads are used for calling (no CNV then).

### Sample sheet (optional CSV) for families and tumour/normal pairs

```csv
sample,role,sex,family,hpo
KID1,proband,female,FAM1,HP:0001250; HP:0001263
MUM1,mother,female,FAM1,
DAD1,father,male,FAM1,
```
```csv
sample,role,sex,family,hpo
T01,tumour,,PATIENT7,
N01,normal,,PATIENT7,
```
`sample` must match the FASTQ/BAM names (the part before `_S1_L001...`). A classic **PED** file also works for families.

## 3. Library types (capture, tagmentation, ligation, amplicon, UMI)

| Library | Examples | Settings |
|---|---|---|
| Hybrid capture | Agilent SureSelect, Twist, IDT xGen, Roche KAPA HyperCap, Illumina exome | defaults (duplicates marked) + kit BED |
| Tagmentation | Illumina DNA Prep (with Enrichment), Nextera Flex | defaults + BED |
| Ligation | TruSeq, KAPA HyperPrep, MGI/BGI libraries | defaults + BED |
| **Amplicon (PCR)** | AmpliSeq, TruSight/TSCA (e.g. TruSight Myeloid), QIAseq, CleanPlex | tick **Amplicon panel** (no duplicate marking) and give **Primer BED** (or Amplicon BED + insert BED) so primers are clipped |
| **UMI** | QIAseq, IDT xGen Prism/UDI-UMI, Twist UMI, Agilent XT HS | **UMIs** = `inline` + read structure, or `read_name` if BCL Convert wrote the UMI into the read names |

Why it matters:
- **Duplicates**: in capture libraries identical fragments are PCR copies and are counted once. In amplicon panels every
  read of an amplicon starts at the same place, so marking duplicates would throw away real data.
- **Primers**: primer bases are copied from the oligo, not from the patient. Unclipped, they hide variants under the primer
  and create false reference reads. Illumina manifest → primer BED: `python3 scripts/manifest_to_primers.py manifest.txt mypanel`
  (check coordinates: older manifests are hg19).
- **UMIs**: reads sharing a UMI come from one original molecule; merging them into a consensus removes PCR and sequencing
  errors, which is what makes 1–5% somatic variants believable. Read structures: `8M+T 8M+T` (8-base UMI at the start of both reads),
  `+T 12M11S+T` (QIAseq: 12-base UMI and 11-base spacer at the start of read 2). Families need ≥ `umi_min_reads` reads (germline 1, somatic 2).

## 4. Germline analysis

1. EPI2ME → **AFLA germline** → Run.
2. Input + Resources folder + Target regions. For a family: FASTQ folder with all members + **Sample sheet**.
3. Case information (optional but useful): **HPO terms** (e.g. `HP:0001250, HP:0001263`; find them at hpo.jax.org),
   **Gene list** (genes or a PanelApp gene list file), **Case ID** (pseudonym).
4. Steps: keep defaults. Tick **Structural variants** if you want Manta (slower). **Variant caller**: `gatk` (CPU) or
   `deepvariant` (GPU; first use downloads ~6 GB).
5. Run. Exome ≈ 2–4 h on a 16-core laptop; panel 10–30 min.

What you get: variants with inheritance labels (trios: *de novo*, *compound heterozygous (in trans)*, *homozygous*,
*hemizygous (X-linked)*, *inherited from mother/father*; singletons: *possible compound heterozygous (phase unknown)*),
ACMG/AMP evidence suggestions, phenotype match per gene, CNVs, ROH, optional SVs, and a printable case report.

**Quality labels** in the FILTER column (variants are never deleted, only labelled):
`LowQual` (QUAL < 30, depth < 10 or GQ < 20), `LowVAF` (heterozygous in < 20% of reads: usually PCR/homopolymer artefacts;
lower `min_het_vaf` to look for mosaicism).

## 5. Somatic analysis

1. EPI2ME → **AFLA somatic** (or AFLA germline with Analysis mode = somatic).
2. Tumour FASTQ/BAM. With a matched normal: give both in the folder and either a **sample sheet** (roles tumour/normal, same family)
   or **Matched normal sample name**. Without a normal: tumour-only.
3. Resources folder (provides the Mutect2 germline resource and panel of normals, CIViC).
4. **Tumour type** (free text, e.g. "acute myeloid leukaemia") lets evidence in the same tumour type support tier I.
5. Amplicon/UMI settings as in section 3. Optional: COSMIC file, OncoKB token (internet needed).

What you get: Mutect2 variants labelled PASS/LowSupport (VAF ≥ 2%, ≥ 5 alt reads, depth ≥ 50 by default), an *origin hint*
(somatic candidate / possible germline by VAF / likely germline by population frequency), suggested **AMP/ASCO/CAP tier**
with the evidence behind it, **TMB** (coding mutations per Mb), **MSI** score, CNVs (gains/losses; amplifications matched to CIViC),
optional SV/fusion candidates, and a somatic case report.

Tier logic (suggestion only): **I** = CIViC level A/B or OncoKB level 1/2/R1 in the given tumour type; **II** = A/B in another
tumour type, C/D, OncoKB 3A/3B/4/R2, or a recurrent COSMIC hotspot (≥ 20 samples); **III** = no evidence, rare (VUS);
**IV** = population frequency ≥ 1% or ClinVar benign.

## 6. The report

Open `afla-report.html` from EPI2ME's Report tab, or in any browser (it works offline and is a single file).
If there are several cases (samples, families or tumours), choose one at the top.

**Quality tab**: tiles with teaching hints (reads, Q30, mapped %, duplicates, depth, % ≥20×, uniformity, Ti/Tv, het/hom;
UMI families; amplicon uniformity), the family members' QC, coverage bars and poorly covered regions,
tumour biomarkers (TMB, MSI), runs of homozygosity.

**Variants tab**:
- *Presets* (germline): Prioritised (ACMG + phenotype), Rare protein-affecting, ClinVar P/LP, De novo, Recessive, All.
  (somatic): Tier I–II, Somatic candidates, All.
- *Filters*: PASS, depth, VAF, population frequency, VEP impact (+ SpliceAI), inheritance, ACMG class, HPO-matched genes,
  PanelApp panel or your gene list, text search.
- Click a column to sort; **Priority** combines ACMG points, phenotype match and your gene list.
- Click a row for the **detail card**: all annotations, family genotypes, links (gnomAD, ClinVar, UCSC, ClinGen, OMIM, PubMed,
  PanelApp; CIViC/OncoKB/COSMIC for somatic), **Check current gnomAD/ClinVar online** (needs internet).
- **ACMG panel** (germline): all 26 criteria. Suggested ones are ticked, with the reason. Tick/untick and change strength;
  the classification updates live (Tavtigian 2020 points: ≥10 pathogenic, 6–9 likely pathogenic, 0–5 VUS, −1 to −6
  likely benign, ≤ −7 benign; BA1 = benign). Criteria needing literature, segregation, functional data or phenotype
  (PS3, PS4, PP1, PP4, BS3, BS4, BP5...) are never ticked automatically.
- ☆ adds a variant to the case report; write your reasoning in *Interpretation note*.

**Exercise mode** (top bar): hides ClinVar, automatic ACMG ticks and tiers, so students classify first and compare after.

**Copy number tab**: CNVkit plot and segments per sample (log2 ≈ −1 one copy lost, ≈ +0.58 one copy gained; somatic
amplifications matched to CIViC). The reference type is shown: *user* (best), *pooled* (other samples of the run), *flat* (weak).

**Structural variants tab**: Manta calls; translocations between two genes are shown as fusion candidates.

**Case report tab**: a structured, printable report built from what you starred: case details (editable), indication/HPO,
variants with classification and criteria, CNVs/SVs, interpretation, quality, methods, limitations, signatures.
**Print / save as PDF** gives a clean document.

**Save my work** downloads your choices (stars, criteria, notes, edited fields) as a small `.json` file; **Load** brings them
back (also on another computer). Work is also kept automatically in the browser.

## 7. Output files

```
output/
  afla-report.html (or afla-somatic-report.html)
  <sample>/qc/            fastp report, mosdepth coverage, UMI family sizes
  <sample>/alignment/     CRAM + index, flagstat, primer clipping statistics
  <sample or family>/variants/  <name>.vcf.gz (labelled), .annotated.vcf.gz (VEP), .roh.txt, .mutect2.vcf.gz (somatic)
  <sample>/cnv/           .call.cns segments, .cnr bins, .genemetrics.tsv, .cnv_scatter.png
  <sample>/sv/            .sv.vcf.gz (Manta)
  <sample>/msi/           .msi.txt
  targets/                BEDs actually used (padded targets, primers)
  execution/              Nextflow timeline, report, trace (run times, memory)
```
Open CRAM/VCF files in **IGV** (free) with the same GRCh38 reference to look at the reads behind any call.

## 8. Command line (no GUI)

```bash
nextflow run ~/afla/main.nf --fastq /mnt/c/data/run1 --resources_dir /mnt/c/Users/<you>/afla-resources \
   --bed /mnt/c/data/kit.bed --samplesheet /mnt/c/data/samples.csv --hpo_terms "HP:0001250" --out_dir run1_out
nextflow run ~/afla/main.nf --mode somatic --fastq /mnt/c/data/tumour --resources_dir ... --bed panel.bed \
   --amplicon true --primer_bed primers.bed --umi_mode inline --umi_read_structure "+T 12M11S+T" --tumour_type "AML"
```
Add `-resume` to continue a stopped run. All form fields are available as `--name value` (see `nextflow_schema.json`).

## 9. Troubleshooting

| Message / problem | Cause and fix |
|---|---|
| "No paired FASTQ files found in ..." | Wrong folder (the message lists what is there), or names without `_R1/_R2`/`_1/_2`. Choose the folder that holds the reads. |
| "... is an index file; using ... instead" | You picked a `.fai/.tbi/.bai`; fine, the data file next to it is used. |
| "No bwa index found" | Use the reference from `afla-setup.sh`, or tick *Build bwa index* once (1 h). |
| "Annotation needs the Ensembl VEP cache" | Set the Resources folder, or untick *Annotate variants*. |
| "CNV analysis skipped: it needs the ... BED" | Give the kit/panel BED. |
| Nothing in ClinVar/REVEL columns | Chromosome naming mismatch or missing file: run `afla-setup.sh` again (it prepares files in the right naming). |
| Run killed / out of memory | Close other programs, lower `max_memory`, or raise WSL memory in `.wslconfig`. |
| DeepVariant fails immediately | GPU not visible to Docker: run `scripts/afla-gpu-check.sh`, or untick *Use the GPU*. |
| Many LowVAF calls in a tumour | You ran germline mode on a tumour: use somatic mode. |
| Many T>C (or other single change) somatic calls | Library/polymerase artefact: see the base-change tile; be careful with those calls. |
| Disk filling up | Each run keeps a `work` folder: delete it after a successful run. |

## 10. Limitations

- Not validated for clinical use. Panels/exomes miss repeat expansions, most SVs, deep intronic/regulatory variants,
  regions of low coverage or high homology (pseudogenes, e.g. PMS2, SMN1/2, CYP2D6), low-level mosaicism, mitochondrial heteroplasmy.
- CNV calls from exome/panel depth are screening-level: confirm with MLPA/array/qPCR. A *flat* reference is unreliable for small changes.
- Tumour-only somatic analysis cannot separate germline and somatic variants with certainty; purity is not estimated;
  panels < 1 Mb give imprecise TMB; MSI cut-offs must be calibrated per assay.
- ACMG/AMP and AMP tier suggestions are partial automations: they do not read the literature.
- Databases change; re-check classifications against current ClinVar/gnomAD (the report has a live-check button).

## 11. Data sources and licences

Free/open: GRCh38 (NCBI), Ensembl VEP + cache, gnomAD, ClinVar, HPO, PanelApp, CIViC (CC0), GIAB, GATK resources.
Free for **non-commercial/academic** use only (each user downloads and accepts the terms): REVEL, AlphaMissense (CC BY-NC-SA),
SpliceAI precomputed scores, COSMIC, OncoKB. Tools: open-source (fastp, bwa, samtools, bcftools, GATK, DeepVariant, fgbio,
CNVkit, Manta, msisensor-pro, mosdepth, Nextflow). Cite the tools and databases you use in any publication.
