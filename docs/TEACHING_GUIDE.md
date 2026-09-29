# AFLA teaching guide

A practical course for students (clinicians, scientists, bioinformatics beginners) using only free, public data.
Each exercise lists the **learning goals**, **what to do**, **questions**, and **instructor notes** (expected answers
from our own test runs; your numbers may differ slightly with other versions).

Before the course: install AFLA (`docs/INSTALL.md`), run `scripts/afla-setup.sh`, and download the practice data:
```bash
bash scripts/afla-testdata.sh /mnt/c/Users/<you>/afla-testdata
```
Practice data = the Genome in a Bottle (GIAB) **Ashkenazi trio** exomes (HG002 son, HG003 father, HG004 mother;
Illumina NovaSeq, IDT capture), chromosome 20 only, with the GIAB **truth sets**; plus an **in-silico tumour**
(HG003 reads with 20% HG002 reads mixed in) and its matched normal. These are consented public reference samples.

Suggested plan: 5 sessions of 2–3 hours.

| Session | Exercises |
|---|---|
| 1. From reads to variants | 1 (QC), 2 (accuracy vs truth) |
| 2. Families | 3 (trio inheritance, artefacts), 4 (ROH) |
| 3. Interpretation | 5 (ACMG practice in exercise mode), 6 (phenotype-driven analysis) |
| 4. Copy number and structure | 7 (CNV), 8 (SV) |
| 5. Cancer | 9 (somatic tumour/normal), 10 (amplicon and UMI concepts), 11 (VCF from elsewhere) |

---

## Exercise 1. Is the sequencing good enough?

**Goals**: read QC metrics; relate them to what can be detected.
**Do**: run AFLA germline on the trio (FASTQ folder `fastq`, sample sheet `trio.csv`, reference `ref/chr20.fa`,
targets `ref/chr20.targets.bed`, Resources folder). Open the report → **Quality**.
**Questions**
1. What are the mean target depth and % of target bases ≥ 20× for each family member?
2. What fraction of reads are duplicates, and why must duplicates be marked in a capture exome but not in an amplicon panel?
3. Open "poorly covered regions". Could a pathogenic variant hide there? What would you do clinically?
**Instructor notes**: mean depth ≈ 110× (HG002), > 95% of targets ≥ 20×; reads mapped ≈ 99.9%. Low-coverage regions are
typically GC-rich first exons: a negative result there is not informative (orthogonal testing / Sanger).

## Exercise 2. How accurate is the pipeline? (benchmarking)

**Goals**: sensitivity, precision, F1; why truth sets matter.
**Do** (Ubuntu terminal):
```bash
bash ~/afla/scripts/afla-benchmark.sh --calls <output>/AJ/variants/AJ.vcf.gz --sample HG002 \
  --truth ~/afla-testdata/truth/HG002.chr20.vcf.gz --truth-bed ~/afla-testdata/truth/HG002.chr20.bed \
  --targets ~/afla-testdata/ref/chr20.targets.bed --ref ~/afla-testdata/ref/chr20.fa
```
**Questions**
1. Recall and precision for SNVs and for indels: which are harder, and why?
2. Open one false-positive indel from `bench_*/fp.vcf.gz` in IGV (load the CRAM). What do you see around it?
3. Re-run with `--min_het_vaf 0` and compare. What does the LowVAF label trade off?
**Instructor notes** (development run, GATK): SNV recall 0.996–0.997, precision 0.999–1.000; indels recall 0.91–0.97,
precision 0.83–0.93 (about 30 indels per sample, so small numbers). False indels sit in homopolymers with 8–24% of reads:
PCR slippage. Without the LowVAF label indel precision drops to about 0.76. Mosaic variants would also sit at low VAF:
that is the trade-off.

## Exercise 3. Inheritance in a trio (and why "de novo" needs care)

**Goals**: Mendelian patterns; de novo calling pitfalls.
**Do**: Variants tab → preset **De novo (trio)**, then **Recessive**. Open a few variants and look at *Genotypes in the family*.
**Questions**
1. How many variants are labelled "de novo" vs "possible de novo (low allele fraction)"? Look at the son's VAF: what does a
   true constitutional de novo variant look like?
2. The expected number of true de novo coding variants in one exome is about 1–2 genome-wide. What does that tell you about chr20?
3. Find a "compound heterozygous (in trans)" gene if present, or explain why phase matters for recessive disease.
**Instructor notes**: on chr20 the development run found 0 confident de novo and 5 "possible de novo" calls, all at
8–17% VAF: sequencing/PCR artefacts in the child (the GIAB truth has none there). Teaching point: require VAF ≈ 50% and
good parental depth; confirm by Sanger.

## Exercise 4. Runs of homozygosity

**Goals**: ROH, consanguinity, autozygosity mapping.
**Do**: Quality tab → Runs of homozygosity. Variants tab → Inheritance = "homozygous inside ROH".
**Questions**: How long are the runs in HG002? Would you expect more in a child of first cousins (theoretically 1/16 of the genome
≈ 180 Mb)? Why does exome data give only approximate boundaries?
**Instructor notes**: ≈ 2 Mb on chr20 for HG002 (outbred population background). Consanguineous families (common in many
teaching settings) show many long runs; recessive candidates inside them move up.

## Exercise 5. Classify variants with ACMG/AMP (exercise mode)

**Goals**: apply ACMG/AMP 2015 criteria and ClinGen SVI refinements; points system.
**Do**: tick **Exercise mode** (ClinVar and automatic ticks are hidden). Pick 5 variants from the *Rare, protein-affecting*
preset (include a missense, a frameshift/stop, a synonymous, a splice-region variant). For each: tick the criteria you think
apply, choose strengths, write a note. Then untick Exercise mode and compare with the suggestions and ClinVar.
**Questions**
1. Why is PM2 only "supporting" (ClinGen SVI)? When is PVS1 not appropriate?
2. Which REVEL scores give PP3 at supporting/moderate/strong (Pejaver 2022)?
3. Which criteria can a computer never apply (PS3, PS4, PP1, PP4, BS3, BS4, BP5, ...), and why?
**Instructor notes**: the suggestions show their reasons (e.g. "REVEL 0.95 ≥ 0.932"). Discuss disagreements: they are the
point of the exercise. Classification = Tavtigian 2020 points (≥10 P, 6–9 LP, 0–5 VUS, −1…−6 LB, ≤ −7 B).

## Exercise 6. Phenotype-driven analysis (HPO)

**Goals**: HPO terms; gene prioritisation; virtual panels.
**Do**: re-run the report step with HPO terms, e.g. seizures + developmental delay (`HP:0001250, HP:0001263`) — already in
`trio.csv` for HG002 — then choose a PanelApp panel (if downloaded) or type a gene list.
**Questions**: which genes on chr20 rank highest for this phenotype and why (see "HPO match")? What happens to the
*Prioritised* preset when you change the phenotype? Why is a virtual panel useful for exomes (incidental findings)?
**Instructor notes**: epilepsy genes on chr20 (e.g. SLC12A5, KCNB1, KCNQ2, EEF1A2) rank top. HG002 is a healthy reference
sample: nothing should be convincingly causal — a good discussion of false leads.

## Exercise 7. Copy-number variants from depth

**Goals**: log2 ratio; references; limits of exome CNV.
**Do**: Copy number tab for all three.
**Questions**: find the segment near the start of chr20 with a very negative log2 in two family members. Which parent did
the son inherit it from? Why does a "pooled" reference (other samples of the run) work better than "flat"?
**Instructor notes**: a homozygous deletion (log2 ≈ −26 = no reads) around SIRPB1 in HG002 and HG004 but not HG003: a known
common deletion polymorphism inherited from the mother. Small ±0.3–0.6 segments with few targets are noise/GC effects.

## Exercise 8. Structural variants

**Goals**: breakpoints, read pairs and split reads; limits of short reads and capture.
**Do**: re-run with *Structural variants* ticked; open the Structural variants tab.
**Questions**: what supports each call? Why do capture panels detect only breakpoints near targets (fusion panels bait introns)?

## Exercise 9. Cancer: tumour vs normal

**Goals**: somatic calling, VAF, germline filtering, tiers, TMB, MSI.
**Do**: AFLA somatic with `somatic/fastq` and `somatic/samples.csv` (tumour/normal pair), tumour type e.g. "colorectal cancer".
**Questions**
1. The "tumour" contains 20% of another person's cells. What VAF do you expect for their heterozygous variants? Check the VAF column.
2. Why are most of the other person's variants NOT reported as somatic? (Hint: gnomAD germline resource, panel of normals, the normal sample.)
3. Look at TMB and MSI. Why is TMB from a 1 Mb target region imprecise?
4. Explain tiers I–IV for one variant each. What changes if you remove the tumour type?
**Instructor notes**: expected VAF ≈ 10–15% (0.5 × ~25% of reads); true rare "somatic" variants were found with precision ≈ 0.96;
common polymorphisms are (correctly) rejected as germline by Mutect2. MSI: stable. TMB is low and imprecise (< 1 Mb).

## Exercise 10. Amplicon panels and UMIs (concepts, optional hands-on)

**Goals**: primer clipping; duplicate marking; UMI consensus.
**Do**: discuss with a real amplicon run if available (e.g. a TruSight Myeloid demo from BaseSpace): tick *Amplicon panel*,
give the primer BED (`scripts/manifest_to_primers.py`), compare with an unclipped run. For UMIs: look at the UMI tiles
(families, single-read families).
**Questions**: what artefact does an unclipped primer cause? Why can UMIs rescue 1% variants while duplicates marking cannot?

## Exercise 11. A VCF from somewhere else

**Goals**: interoperability; re-annotation.
**Do**: take any VCF (e.g. the GIAB truth VCF `truth/HG002.chr20.vcf.gz`, a Galaxy result, an EPI2ME wf-human-variation
nanopore VCF) → AFLA germline → *VCF file* input. Compare with the FASTQ run.
**Questions**: what is lost when starting from a VCF (no QC, no CNV, no coverage)? Why must the reference build match?

---

### Assessment ideas
- Give each student a different chr20 gene set as a "virtual panel"; they produce a printed case report (Case report tab →
  Print) and a saved work file (`Save my work`) for marking.
- Blind classification: exercise mode on, 10 preselected variants; compare students' classes with ClinVar expert-panel records.
- Critique exercise: find one false positive and one false negative from the benchmark and explain them with IGV screenshots.

All practice data are public reference materials. Never use real patient data in class without ethics approval,
consent and pseudonymisation.
