# AFLA technical reference

For users see `USER_MANUAL.md`; for installation `INSTALL.md`; for teaching `TEACHING_GUIDE.md`.
Education and research use only.

## Code layout

| File | Role |
|---|---|
| `main.nf` | Orchestration: mode, resources, input type, sample sheet, which steps run, report metadata |
| `modules/reference.nf` | reference indexes, BED cleaning/padding, automatic targets, primers, microsatellite scan |
| `modules/reads.nf` | fastp, bwa alignment (+markdup), primer clipping, UMI consensus (fgbio), coverage (mosdepth) |
| `modules/variants.nf` | GATK/DeepVariant (single or gVCF), joint genotyping (GATK/GLnexus), normalise + labels, ROH, VEP |
| `modules/somatic.nf` | Mutect2 (chunked), FilterMutectCalls, support filter, MSI (msisensor-pro), Manta |
| `modules/cnv.nf` | CNVkit targets, coverage, reference (user / leave-one-out / flat), segmentation and calls |
| `modules/report.nf` | per-case summary JSON and the HTML report |
| `bin/afla_report.py` | parsers (fastp, flagstat, mosdepth, fgbio, ampliconclip, VCF, CNVkit, Manta, ROH, MSI), inheritance, summary |
| `bin/afla_acmg.py` | ACMG/AMP evidence suggestions and points |
| `bin/afla_hpo.py` | HPO parsing and phenotype similarity |
| `bin/afla_somatic.py` | CIViC/COSMIC/OncoKB evidence, AMP tiers, TMB, MSI interpretation |
| `bin/afla_report_template.html` | the single-file report (no external libraries) |
| `nextflow.config` | parameters, machine-size detection, resource labels, profiles |
| `scripts/make_schema.py` | generates `nextflow_schema.json` (germline form) and `somatic/nextflow_schema.json` |
| `scripts/afla-setup.sh` | resources installer; `afla-testdata.sh` practice data; `afla-benchmark.sh` RTG vcfeval scoring |
| `scripts/install-epi2me.sh` | installs the two EPI2ME entries; `afla-cnv-reference.sh` CNV reference from normals |
| `scripts/manifest_to_primers.py` | Illumina TSCA/TruSeq manifest → primer + insert BED; `panelapp_download.py` PanelApp panels |

## Units of analysis

A *unit* is one germline sample, one **family** (≥ 2 sample-sheet/PED members sharing `family`; genotyped jointly and
reported under the family name with the proband as main sample), or one **tumour** (paired with the normal of the same
`family`, or with `normal_sample`). Normal samples get QC-only entries.

## Parameters

All parameters are in `nextflow.config` (defaults) and the EPI2ME form. Mode-dependent defaults (empty = default):

| Parameter | Germline | Somatic |
|---|---|---|
| `min_dp` | 10 | 50 |
| `report_min_vaf` / `report_max_pop_af` | 0.2 / 0.01 | 0.02 / 0.001 |
| `umi_min_reads` | 1 | 2 |
| report file | afla-report.html | afla-somatic-report.html |

Machine size: `max_cpus` = all CPUs, `max_memory` = 85% of RAM (detected by the JVM). Labels: default 1 CPU/2 GB,
`medium` ≤ 4 CPU/8 GB, `big` ≤ `threads` CPU/24 GB; every request is capped by the machine size.

## Resources folder layout (made by `scripts/afla-setup.sh`)

```
afla-resources/
  reference/GRCh38_no_alt_analysis_set.fa(.fai,.dict,.amb,.ann,.bwt,.pac,.sa)
  vep/cache/homo_sapiens/115_GRCh38/   vep/fasta/Homo_sapiens.GRCh38.dna.primary_assembly.fa(.fai)   vep/Plugins/*.pm
  vep/gtf/genes.gtf.gz(.tbi)           (lean install only)
  clinvar/clinvar.vcf.gz(.tbi)  clinvar/clinvar_protein_index.tsv.gz
  revel/new_tabbed_revel_grch38.tsv.gz(.tbi)   alphamissense/AlphaMissense_hg38.tsv.gz(.tbi)   spliceai/*.vcf.gz (manual)
  constraint/gnomad.v4.1.constraint_metrics.tsv   hpo/{hp.obo,genes_to_phenotype.txt}   panelapp/panelapp_*.tsv
  somatic/{af-only-gnomad.hg38.vcf.gz,1000g_pon.hg38.vcf.gz}(.tbi)   civic/nightly-*.tsv
  annotation/refFlat.txt   targets/*.bed   msi/*.microsatellites.list
```
Chromosome naming: the VEP cache uses `1..22,X,Y,MT`; VCFs with `chr` names are renamed for VEP and back afterwards, so
ClinVar/REVEL/AlphaMissense are prepared without `chr`. The `--lean` install (GTF, no cache) keeps `chr` everywhere.
Older layouts (`annotation/vep_cache`, `annotation/clinvar/...`) are also recognised.

## Algorithms

**Read processing.** fastp (`--detect_adapter_for_pe`; QC-only when UMIs are present) → bwa mem `-Y` with read groups →
`samtools fixmate | sort | markdup -s` (not for amplicons/UMIs) → CRAM. Primer clipping: `samtools ampliconclip --soft-clip
--both-ends [--strand] --tolerance 5 --filter-len 30`, re-sorted. UMIs: fgbio FastqToBam (read structure or
`--extract-umis-from-read-names`) → bwa → ZipperBams → SortBam TemplateCoordinate → GroupReadsByUmi (adjacency, 1 edit,
MAPQ ≥ 20) → CallMolecularConsensusReads (`--min-reads`) → FilterConsensusReads (error rate 0.05, base Q ≥ 20) → bwa →
ZipperBams → sorted CRAM.

**Germline calling.** GATK HaplotypeCaller in padded targets (or DeepVariant WES/WGS); families: `-ERC GVCF` →
CombineGVCFs + GenotypeGVCFs (DeepVariant: GLnexus DeepVariantWES/WGS). `bcftools norm -m -both` + left-align, `*` alleles
removed, labels: LowQual (QUAL/DP/GQ; families QUAL only at site level), LowVAF (het AF < `min_het_vaf`; for families the
proband's call is labelled in the report).

**Inheritance** (report, proband with parents): de novo = proband het (VAF ≥ 0.25), both parents hom-ref with depth ≥ `min_dp`,
GQ ≥ `min_gq`, ≤ 1 alt read; lower VAF → "possible de novo". Homozygous / hemizygous (X, male). Inherited from mother/father
(one parent carries it, the other hom-ref). Compound heterozygous: ≥ 1 rare (AF ≤ 1%) HIGH/MODERATE het variant from each
parent in the same gene; without parents "possible compound heterozygous (phase unknown)". ROH: `bcftools roh --AF-dflt 0.4 -G 30`.

**ACMG/AMP suggestions** (`afla_acmg.py`; reasons shown in the report; "consider" items are not pre-ticked):
| Code | Rule |
|---|---|
| BA1 | max population AF > 5% (stand-alone) |
| BS1 | AF > 1% (use a disease-specific threshold) |
| PM2_Supporting | absent from gnomAD or AF ≤ 1e-5 (consider when ≤ 1e-4) |
| PVS1 | stop/frameshift/canonical splice/start-loss in a LoF-intolerant gene (gnomAD LOEUF < 0.6 or pLI ≥ 0.9); last exon → Strong; start-loss → Moderate; tolerant gene → consider |
| PS1 / PM5 | same amino-acid change / other missense at the same residue is ClinVar P/LP (amino-acid index) |
| PM4 | in-frame indel or stop-loss |
| PP3 / BP4 | missense REVEL (Pejaver 2022): ≥ 0.932 Strong, ≥ 0.773 Moderate, ≥ 0.644 Supporting; ≤ 0.290 / 0.183 / 0.016 / 0.003 BP4 Supporting / Moderate / Strong / Very strong; AlphaMissense class when REVEL is absent; SpliceAI ≥ 0.2 PP3, ≤ 0.1 BP4 (non-missense) |
| PP2 | missense in a gene with missense Z ≥ 3.09 (consider) |
| BP7 | synonymous outside splice region with SpliceAI ≤ 0.1 |
| PM6 / PM3 | de novo (parentage assumed) / in trans with a P/LP variant (supporting if the partner is not P/LP) |
Points (Tavtigian 2020): Very strong 8, Strong 4, Moderate 2, Supporting 1 (benign negative); ≥ 10 P, 6–9 LP, 0–5 VUS,
−1…−6 LB, ≤ −7 B.

**Phenotype score** (`afla_hpo.py`): information content IC(t) = −log(fraction of annotated genes with t or a descendant);
score = ½·mean over patient terms of max IC of a shared ancestor with the gene's terms (normalised by the patient terms' IC)
+ ½·the same from the gene's side; restricted to "Phenotypic abnormality". 0–1.

**Somatic.** Mutect2 (`--max-reads-per-alignment-start 0`, optional germline resource and PoN; optional chunks balanced by
bases × depth) → FilterMutectCalls → tumour sample, norm, LowSupport (VAF < `min_vaf`, alt reads < `min_alt_reads`, depth
< `min_dp`); amplicon mode drops the strand_bias and position labels. TMB = PASS coding non-synonymous variants with VAF ≥
`tmb_min_vaf`, depth ≥ `min_dp`, population AF < 0.1% / coding Mb in targets (refFlat CDS ∩ targets, else target Mb).
MSI: msisensor-pro `msi` (paired) or `pro` (tumour-only, threshold or baseline) on microsatellites inside targets;
interpretation shown with the MSK-IMPACT MSIsensor convention (< 3 stable, 3–10 indeterminate, ≥ 10 high; < 50 sites unreliable).
Tiers: see USER_MANUAL §5. CIViC matching: exact protein change, codon, exon-level indels, gene-level (any mutation,
loss of function), amplification/deletion for CNV segments (|log2| ≥ 0.7).

**CNV** (CNVkit, targets only): `target --split --avg-size 267 [--annotate refFlat]` → `coverage` → reference
(user `.cnn`; else leave-one-out from ≥ 2 other samples of the run (germline) or the normals (somatic); else flat) →
`fix --no-edge` → `segment -m cbs` → `call -m threshold` (germline −1.1/−0.4/0.3/0.7; somatic −1.1/−0.25/0.2/0.7) →
`genemetrics`, scatter plot.

**SV** (Manta 1.6, `--exome`, call regions = padded targets): germline `diploidSV`, somatic `tumorSV`/`somaticSV`;
VEP-annotated; BND mates joined, two different genes → fusion candidate.

## Containers (Docker)

fastp 1.3.7; bwa 0.7.17 + samtools 1.16.1 (mulled) for alignment; samtools 1.21; mosdepth 0.3.10; fgbio 4.1.1;
GATK 4.6.2.0; DeepVariant 1.9.0 (-gpu); GLnexus 1.4.1; bcftools 1.23.1 (staphb); Ensembl VEP 115.2; CNVkit 0.9.14;
Manta 1.6.0; msisensor-pro 1.3.0; bedtools 2.31.1; Python 3.12 (report, standard library only).

## Validation so far (development sandbox, chromosome 20 slices of public data)

See `tests/README.md`: GIAB HG002/HG003/HG004 exome trio SNV F1 ≈ 0.997–0.999, indel F1 ≈ 0.87–0.95 (small numbers);
all entry points, trio labels, CNV, SV, ROH, UMI, primer clipping, somatic pair, MSI, TMB and the report exercised.
To do on the full laptop install: whole-exome runs, DeepVariant (GPU), GLnexus, real ClinVar/CIViC/PanelApp downloads,
a real amplicon panel with its manifest, and a DNBSEQ exome.
