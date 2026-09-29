# Changelog

Versions follow `MAJOR.MINOR.PATCH`. Each release is a git tag (`v0.3.0`) that EPI2ME shows as a version when the
workflow is imported from GitHub. Education and research use only.

## v0.3.0 (2026-09-29): first teaching release

- One portable workflow for **germline and somatic** short-read panels and exomes (Illumina/DNBSEQ), importable in EPI2ME
  on any computer; a second "AFLA somatic" entry via `scripts/install-epi2me.sh`.
- Start from FASTQ, BAM/CRAM or VCF. "Resources folder" fills every reference/database automatically; CPU and memory are
  detected per machine.
- Library types: hybrid capture, tagmentation, ligation, **amplicon** (primer clipping from a primer BED, amplicon-minus-insert,
  or Illumina manifest) and **UMI** consensus (fgbio).
- Germline: GATK HaplotypeCaller or DeepVariant (GPU); families jointly (GATK/GLnexus) with de novo, compound heterozygous,
  homozygous and X-linked labels; LowVAF artefact label; CNV (CNVkit), SV (Manta), runs of homozygosity; ACMG/AMP evidence
  suggestions with points; HPO phenotype ranking; PanelApp virtual panels.
- Somatic: Mutect2 tumour-only or tumour/normal, MSI (msisensor-pro), TMB, CNV, SV/DNA fusions, CIViC/COSMIC/OncoKB evidence,
  AMP/ASCO/CAP tier suggestions.
- Report: quality, variants, copy number, structural variants, interactive ACMG panel, exercise mode, printable case report,
  save/load of students' work, live gnomAD/ClinVar check.
- Tools: `afla-setup.sh` (resources), `afla-testdata.sh` (GIAB practice data), `afla-benchmark.sh` (RTG vcfeval),
  `afla-cnv-reference.sh`, `manifest_to_primers.py`, `afla-usb-kit.sh` (offline classroom installation).
- Documentation: installation guide, user manual, teaching guide (11 exercises), technical reference, three beginner decks.
- Validated in development on chromosome-20 slices of public GIAB data (see `tests/README.md`). Not yet validated on whole
  exomes, DeepVariant/GPU, a real amplicon manifest or DNBSEQ data: see "known gaps" in `docs/WORKFLOW.md`.

## v0.2 and earlier (2026-09-26 to 2026-09-29)

Plan, laptop inventory, first germline workflow and the somatic Mutect2 workflow tested on TruSight Myeloid data.
