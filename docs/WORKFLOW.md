# AFLA workflows (germline and somatic): user guide

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

## AFLA somatic (second EPI2ME workflow)

The same code in **somatic mode**, listed in EPI2ME as **AFLA somatic (Illumina short reads)**. It is for tumour
panels such as TruSight Myeloid, where variants can be present in only a few % of reads.

- **Caller:** GATK **Mutect2**, then FilterMutectCalls. Down-sampling is switched off, because panels are deep.
- **Tumour-only** by default. If the input folder also has the patient's **normal** sample, enter its name in
  *Matched normal sample name*. Every other sample is then called against it, which removes inherited variants
  much more reliably.
- **Support filter:** VAF ≥ 2%, ≥ 5 supporting reads, depth ≥ 50. Weaker calls are kept but labelled `LowSupport`.
- **Optional resources:** a gnomAD af-only germline resource and a panel of normals (PoN) for your own assay.
- **Report:** an *Origin (hint)* column says *somatic candidate*, *possible germline (VAF ~50%/100%)*,
  *likely germline (population)* (gnomAD AF > 0.1%), or *likely germline (Mutect2)*. There is also a
  "somatic candidates only" filter. The defaults are VAF ≥ 2% and population AF ≤ 0.1%.
- **Amplicon panels:** tick *Amplicon panel*. This switches off duplicate marking (in both workflows). In somatic
  mode it also stops Mutect2's `strand_bias` and `position` labels from rejecting calls, because amplicon reads come
  from one strand and start at the primers. Primer/probe sequences are not trimmed (no panel manifest), so variants
  at amplicon ends need a careful look in IGV.
- **Base-change QC tile:** the share of each substitution type (C>T, T>C, ...) among PASS SNVs. C>T usually
  dominates in blood cancers; a strong excess of another type suggests artefacts.
- **Speed:** Mutect2 is the slow step (~30 min for a myeloid panel). *Mutect2 parallel chunks* can split the work.
  On this laptop, 6 chunks gave identical calls but were not faster for a panel; it may help for exomes.
- **Not included (yet):** CNVs, fusions, MSI, TMB, COSMIC/CIViC/OncoKB evidence, and AMP/ASCO/CAP tiering.

**What the TruSight Myeloid test (NA12877 + Horizon) showed, as a teaching example:**
- DNMT3A p.Arg882His was detected at only 0.3% VAF (11 of 3,927 reads), far below any usable cut-off. The Horizon
  variants in this sample are probably diluted to very low levels; the product sheet is needed to know the expected
  variants and levels.
- In amplicon mode, 152 calls PASS and 33 appear in the default report view (VAF 3–16%). But 56% of PASS SNVs are
  T>C, an unusual pattern that points to library or polymerase artefacts rather than tumour mutations. The pipeline
  works; the data needs caution.

Command line: add `--mode somatic` (and `--normal_sample NAME` if you have a normal) to the command below.

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
   (after changing the code here, run `scripts/install-epi2me.sh`; see the end of this file). It appears in EPI2ME's workflow list
   as **AFLA germline (Illumina short reads)**. Restart EPI2ME if it doesn't show.
2. Click it, then **Run**. Fill in the form:
   - **Input**: one of FASTQ folder / BAM / VCF.
   - **Reference**: the GRCh38 FASTA with its bwa index next to it.
   - **Target regions**: the capture-kit BED if you have it. If empty, covered regions are used.
   - **Steps to run**: tick/untick. For **amplicon** panels tick *Amplicon panel*.
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
Add `--amplicon true` for amplicon panels, and `--caller deepvariant` for DeepVariant (GPU).
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

## Updating the copies that EPI2ME uses

EPI2ME runs its own copies, `workflows\fjbukhari\afla` (germline) and `workflows\fjbukhari\afla-somatic`
(the same code plus `somatic/mode.config`, `somatic/nextflow_schema.json` and `somatic/output_definition.json`).
After changing the code, refresh both copies and restart EPI2ME:

```bash
bash ~/afla/scripts/install-epi2me.sh
```
