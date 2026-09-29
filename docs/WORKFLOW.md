# AFLA germline workflow: user guide

Education and research use only. Not for clinical diagnosis or patient management.

## What it does

Germline (inherited) small variants, meaning SNVs and small indels, from **Illumina short reads**: gene panels and exomes.

```
FASTQ ─► fastp ─► bwa mem ─► (mark duplicates) ─► CRAM/BAM ─► coverage (mosdepth)
                                                        │
                                                        ▼
                            target regions (your BED, or regions the reads cover)
                                                        │
                                                        ▼
                     GATK HaplotypeCaller  or  DeepVariant (GPU) ─► normalise + quality label
                                                        │
                                                        ▼
                     Ensembl VEP 115 offline (+ ClinVar, REVEL, AlphaMissense) ─► afla-report.html
```

You can **start at any point**. Give a FASTQ folder to run everything, a BAM/CRAM to skip alignment, or a VCF
(from any pipeline, e.g. Galaxy or a sequencing provider) to run annotation and the report only.
**Every step can be switched on or off** in the "Steps to run" section.

What it does *not* do (yet): ONT data (use EPI2ME's own `wf-human-variation`), somatic or low-frequency
variants (germline callers expect ~50%/100% allele fractions), CNVs, and ACMG classification.

## The report (`afla-report.html`, opens in EPI2ME's Report tab)

- **Quality control tiles** with teaching hints: reads, Q30, % mapped, duplicates, mean depth, % of targets ≥20×,
  Ti/Tv, het/hom ratio.
- **Coverage**: % of target bases at 10–100×, plus a list of poorly covered regions.
- **Variant explorer**: filter by PASS, depth, VAF, population frequency (gnomAD v4.1), VEP impact, ClinVar P/LP,
  your own gene list and free text. It has presets (rare protein-affecting, ClinVar pathogenic, gene list, all),
  sortable columns, a detail card with links to gnomAD/ClinVar/UCSC/ClinGen/dbSNP, and CSV export.
- **Methods**: steps run, containers, annotation sources and all parameters.

## Using it in EPI2ME Desktop

1. The workflow is installed as a copy of this repository in `C:\Users\fjbuk\epi2melabs\workflows\fjbukhari\afla`
   (after changing the code here, copy it again with `rsync`; see the end of this file). It appears in EPI2ME's workflow list
   as **AFLA germline (Illumina short reads)**. Restart EPI2ME if it doesn't show.
2. Click it, then **Run**. Fill in the form:
   - **Input**: one of FASTQ folder / BAM / VCF.
   - **Reference**: the GRCh38 FASTA with its bwa index next to it.
   - **Target regions**: the capture-kit BED if you have it. If empty, covered regions are used.
   - **Steps to run**: tick/untick. For **amplicon** panels untick *Mark duplicate reads*.
   - **Annotation sources**: VEP cache folder, Ensembl FASTA (for HGVS names), ClinVar, REVEL, AlphaMissense.
3. EPI2ME can only see files on the Windows side (`C:\...`), not the Ubuntu home folder. On this laptop the
   copies for EPI2ME are in `C:\Users\fjbuk\afla-data\`:

   | Form field | File or folder |
   |---|---|
   | Reference genome | `afla-data\reference\hg38.analysisSet.fa` (bwa index next to it) |
   | VEP cache folder | `afla-data\annotation\vep_cache` |
   | Ensembl FASTA for HGVS | `afla-data\annotation\fasta\Homo_sapiens.GRCh38.dna.primary_assembly.fa` |
   | ClinVar VCF | `afla-data\annotation\clinvar\clinvar_GRCh38.vcf.gz` |
   | REVEL scores | `afla-data\annotation\revel\new_tabbed_revel_grch38.tsv.gz` |
   | AlphaMissense scores | `afla-data\annotation\alphamissense\AlphaMissense_hg38.bare.tsv.gz` |

4. Tested run times (TruSight Myeloid, 2.6 M read pairs, GATK): about 15 minutes in total. Alignment and calling
   take ~5 minutes each.

## Running it from the Ubuntu terminal (same workflow, no GUI)

```bash
H=~/jbs-human-refs
nextflow run ~/afla/main.nf -w ~/afla-runs/<run>/work --out_dir ~/afla-runs/<run>/output \
  --fastq /mnt/c/path/to/fastq_folder \
  --ref ~/afla-refs/GRCh38_analysisSet/hg38.analysisSet.fa \
  --bed /mnt/c/path/to/targets_hg38.bed \
  --vep_cache $H/vep_cache --vep_fasta $H/fasta/Homo_sapiens.GRCh38.dna.primary_assembly.fa \
  --clinvar_vcf $H/clinvar/clinvar_GRCh38.vcf.gz \
  --revel_file $H/revel/new_tabbed_revel_grch38.tsv.gz \
  --alphamissense_file $H/alphamissense/AlphaMissense_hg38.bare.tsv.gz
```
Add `--mark_duplicates false` for amplicon panels, and `--caller deepvariant` for DeepVariant (GPU).
Add `-resume` to continue a stopped run without redoing finished steps.

## Outputs (`output/`)

| Path | Content |
|---|---|
| `afla-report.html` | the interactive report (all samples) |
| `<sample>/qc/` | fastp report, mosdepth coverage files |
| `<sample>/alignment/` | CRAM/BAM + index, flagstat, duplicate statistics |
| `<sample>/variants/` | `<sample>.vcf.gz` (normalised, LowQual-labelled), `.annotated.vcf.gz`, VEP summary |
| `targets/` | padded target BED actually used |
| `execution/` | Nextflow run report, timeline, trace |

## Files in this repository

| File | Role |
|---|---|
| `main.nf` | connects the steps; decides the start point and which steps run |
| `modules/*.nf` | one process per step (command + container) |
| `nextflow.config` | default settings, Docker, CPU/memory, GPU switch |
| `nextflow_schema.json` | the EPI2ME form: fields, help texts, defaults |
| `bin/afla_report.py`, `bin/afla_report_template.html` | report builder (Python standard library only) |
| `bin/pad_merge_bed.sh` | cleans, pads and merges target BEDs |
| `tests/data/synthetic_germline.vcf` | synthetic test VCF (ClinVar positions, invented genotypes) |

## Updating the copy that EPI2ME uses

```bash
rsync -a --delete --exclude output --exclude work --exclude '.nextflow*' ~/afla/ /mnt/c/Users/fjbuk/epi2melabs/workflows/fjbukhari/afla/
```
