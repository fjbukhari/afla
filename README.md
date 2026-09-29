# AFLA: short-read NGS analysis in EPI2ME Desktop (teaching / non-profit)

AFLA runs inside the Oxford Nanopore **EPI2ME Desktop** app, but analyses **Illumina/DNBSEQ short reads**:
germline and somatic **gene panels and exomes** (hybrid capture, tagmentation, ligation, amplicon, UMI libraries).
Start from **FASTQ, BAM/CRAM or a VCF**; finish with an interactive report and a printable, teaching-style case report.

> **Education and research use only. Not for clinical diagnosis or patient management.**

| | Germline | Somatic |
|---|---|---|
| Calling | GATK HaplotypeCaller or DeepVariant (GPU); trios/families jointly | GATK Mutect2, tumour-only or tumour/normal |
| Library support | duplicate marking, primer clipping (amplicons), UMI consensus (fgbio) | same |
| Beyond SNVs | CNV (CNVkit), SV (Manta), runs of homozygosity | CNV, SV/DNA fusions, MSI, TMB |
| Interpretation | VEP + gnomAD, ClinVar, REVEL, AlphaMissense, SpliceAI; ACMG/AMP evidence suggestions; HPO gene ranking; PanelApp panels; de novo / compound het / recessive labels | CIViC, OncoKB, COSMIC evidence; AMP/ASCO/CAP tier suggestions |
| Report | QC, variants, CNV, SV, interactive ACMG panel, exercise mode, printable case report, save/load | QC, TMB/MSI, tiers and evidence, CNV, fusions, case report |

## Start here

1. **Install**: [`docs/INSTALL.md`](docs/INSTALL.md) (Windows 11 + WSL2 + Docker Desktop + EPI2ME; resources with `scripts/afla-setup.sh`).
2. **Use**: [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md).
3. **Teach**: [`docs/TEACHING_GUIDE.md`](docs/TEACHING_GUIDE.md) with public GIAB practice data (`scripts/afla-testdata.sh`).
4. **Beginner slide decks**: [`docs/slides/`](docs/slides/).
5. Technical reference: [`docs/WORKFLOW.md`](docs/WORKFLOW.md); tests: [`tests/README.md`](tests/README.md); background plan: [`docs/PLAN.md`](docs/PLAN.md).

Any computer with EPI2ME can import `https://github.com/fjbukhari/afla` (Workflows → Import workflow).
CPU and memory are detected automatically (minimum 4 cores / 12 GB RAM).

Uses only free/open tools and data; some databases are free for non-commercial use only (REVEL, AlphaMissense, SpliceAI,
COSMIC, OncoKB) and are downloaded by each user under their own licence.
