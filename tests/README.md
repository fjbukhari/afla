# Testing AFLA

## 1. Quick checks (seconds, no bioinformatics tools needed)

```bash
python3 tests/test_units.py                  # ACMG rules, CIViC matching, tiers, COSMIC, TMB, MSI, inheritance, manifest converter
python3 scripts/make_schema.py               # regenerates the EPI2ME forms (run after changing parameters)
nextflow lint main.nf modules/ nextflow.config   # Nextflow 25+ only: strict-syntax check
```

## 2. Report in a simulated browser

```bash
npm i jsdom@24                                # once
node tests/report_smoke.js output/afla-report.html GENE1,GENE2
```
It clicks through every tab, preset, the ACMG panel, exercise mode and the case report, and fails on any script error.

## 3. End-to-end runs on real data (GIAB trio, in-silico tumour)

```bash
bash scripts/afla-testdata.sh ~/afla-testdata          # ~1.5 GB: chr20 of the GIAB HG002/HG003/HG004 exomes + truth sets
nextflow run main.nf --fastq ~/afla-testdata/fastq --samplesheet ~/afla-testdata/trio.csv \
    --ref ~/afla-testdata/ref/chr20.fa --bed ~/afla-testdata/ref/chr20.targets.bed \
    --resources_dir <your afla-resources> --run_sv true --out_dir trio_test
bash scripts/afla-benchmark.sh --calls trio_test/AJ/variants/AJ.vcf.gz --sample HG002 \
    --truth ~/afla-testdata/truth/HG002.chr20.vcf.gz --truth-bed ~/afla-testdata/truth/HG002.chr20.bed \
    --targets ~/afla-testdata/ref/chr20.targets.bed --ref ~/afla-testdata/ref/chr20.fa
```

Without Docker (tools from conda/mamba on the PATH) add `-profile local`.

## Results obtained during development (GATK HaplotypeCaller, trio joint calling, chr20 exome targets, 0.91 Mb scored)

| Sample | SNV recall | SNV precision | Indel recall | Indel precision |
|---|---|---|---|---|
| HG002 | 0.997 | 1.000 | 0.941 | 0.865 |
| HG003 | 0.997 | 1.000 | 0.966 | 0.933 |
| HG004 | 0.996 | 0.999 | 0.909 | 0.833 |

(Small numbers: 672–685 SNVs and 29–34 indels per sample. Low-VAF heterozygous indels in homopolymers were the main
false positives; the `min_het_vaf` filter (0.2) removes most of them without losing true variants.)

Other checks that passed: FASTQ/BAM/VCF entry points, trio de novo/compound-het/homozygous labelling, CNVkit with
leave-one-out references (a known homozygous deletion found in HG002 and HG004, not HG003), Manta, ROH, UMI consensus
(simulated families of 1–4 reads recovered exactly), primer clipping (primer BED and amplicon-minus-insert), somatic
tumour/normal Mutect2 on the in-silico tumour (precision 0.96; common polymorphisms correctly treated as germline),
MSI (stable), TMB, CIViC matching and tier suggestions (with test rows).

Not testable in the development sandbox (no Docker/GPU there) and to be checked on the laptop: the Docker containers
themselves, DeepVariant (GPU) and GLnexus, OncoKB (needs internet + token), and the real ClinVar/CIViC/PanelApp downloads.
