# AFLA — Illumina NGS workflows for EPI2ME Desktop (teaching / non-profit)

Nextflow workflows that run inside the Oxford Nanopore **EPI2ME Desktop** app, but
analyse **Illumina** short-read data: human germline exomes and panels first, then
somatic, microbial isolates and metagenomes. Each workflow can start from raw
FASTQ, from an aligned BAM/CRAM, or from an existing VCF, and ends in an HTML
report for teaching-style tertiary interpretation.

> **Education and research use only.** Nothing produced here is intended for
> clinical diagnosis or patient management.

See [`docs/PLAN.md`](docs/PLAN.md) for the architecture, tool choices, licensing
notes and staged roadmap.
