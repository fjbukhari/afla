# Gene Panel Designer review notes

## Structure
15 steps: 1 gene list, 2 scope/size, 3 summary, 4 QC settings, 5 design primers (+multiplex),
6 long-range, 7 cross-check (alg B), 8 reference check, 9 literature, 10 hybrid capture,
11 NGS amplicon log+index, 12 Sanger log, 13 export, 14 HRM, 15 ARMS.

## Observations (to verify by test)
- O1 No qPCR/probe design anywhere (user asked for qPCR). HRM is the only real-time path.
- O2 Tm model has no Mg2+/dNTP correction (only monovalent). Primer3/Primer-BLAST default
  Mg 1.5-3 mM; Tm differs several degrees -> annealing temp advice off.
- O3 Specificity = exact-match search in a 50 kb window only (localSpecificityCheck,
  DESIGN_SPEC_WINDOW). No mismatch tolerance, no genome-wide, no pseudogene check.
- O4 No common-SNP check under primer sites (allele dropout risk) though Ensembl variation
  API is already used by HRM/ARMS.
- O5 hairpin/dimer are string-match heuristics, not thermodynamic (no dG).
- O6 threePrimeDimerCheck offset max 2, tail 4 -> only end-anchored dimers caught.

## CONFIRMED FAULTS (evidence in gpd/*.json)

F1 CRITICAL - Step 4 "Tm min/max" and "GC min/max" are scoring preferences, not limits.
   scoreCandidate() returns null only for: length<minLen, unknown Tm, homopolymer>=6.
   Tm/GC outside the user's band add +8/+6 penalty and remain selectable.
   Probe (user band Tm 59-61, GC 45-55): accepted 0% GC Tm 33.6C; 100% GC Tm 79.7C;
   pure CTG repeat (penalty 36.5); CA-dinucleotide repeat (penalty 13.2 vs 1.6 for a good primer).
   Real consequence, HRM step: AT-rich target -> offered ATTTATATTAAATATTTAA, 0% GC, Tm 30.1C;
   GC-rich target -> CGGCGCCGGCGGCCGCGG, 100% GC, Tm 74.1C. Both presented as finished designs.

F2 CRITICAL - specificity is advisory only, computed AFTER the pair is chosen.
   localSpecificityCheck runs in logAndRenderPair, never in choosePair/pickBestPairs.
   TP53 exon 2-3: chose CTGCTGCTGCTGCTGCTG = 262 binding sites in the 50kb window,
   homodimer dG -10.5 kcal/mol; labelled "Ambiguous in local window" but still the chosen pair.

F3 IMPORTANT - no sequence-complexity filter: di/tri-nucleotide repeat primers are selectable.

F4 IMPORTANT - hairpin/dimer checks are string matching, not thermodynamics.
   3 of 12 TP53 pairs had primer3 hairpin Tm > 50C (max 67.6C) with no warning;
   one homodimer dG -10.5. threePrimeDimerCheck only sees 4-base end matches within offset 2.

F5 IMPORTANT - primer Tm has no divalent/dNTP correction. Measured vs primer3 with
   PCR-typical 1.5 mM Mg / 0.6 mM dNTP: tool reads 5.75-6.17C LOW (mean 5.95C, n=30).
   Primer3/Primer-BLAST include it, so the tool's annealing-temperature advice is ~6C too low.

F6 IMPORTANT - HRM amplicon melting temperature uses the short-oligo two-state NN model
   with 250 nM strand concentration on a 80-200 bp amplicon. vs the long-duplex (Wetmur)
   formula it over-predicts by +3.7 to +5.0C across GC 35-75%, length 80-200.

F7 IMPORTANT - HRM ranks candidates by homoduplex ref-vs-alt dTm, which is ~0 for
   SNP class 3/4 (A/T, G/C swaps): observed +0.00, +0.19, +0.07, -0.04C.
   Heteroduplex formation - the actual basis of HRM heterozygote detection - is never
   modelled or mentioned, and no SNP class is reported.

F8 GAP - no qPCR/probe (TaqMan) design anywhere, though the user asked for qPCR.

F9 GAP - specificity window is a 50kb exact-match scan only: no mismatch tolerance,
   no genome-wide/pseudogene check. An engineered duplicate 9kb away was detected
   (2 sites, correctly flagged) but a true pseudogene elsewhere would be missed.

F10 GAP - no common-SNP check under primer binding sites (allele-dropout risk),
   although the Ensembl variation API is already wired up for HRM/ARMS.

## VERIFIED CORRECT (no fault)
- Primer coordinates, product sizes, exon containment: 12/12 TP53 pairs exact.
- Promised minimum intronic flank honoured in every checkable pair.
- Primer Tm matches primer3 to <1C under the same (monovalent-only) conditions.
- Exon numbering strand-aware; merged-exon amplicons correct.
- Honest failure reporting when a target cannot be designed ("needs manual attention").
- ARMS engineered-mismatch transition rule: could NOT establish a fault. Duplex-thermodynamic
  probes were inconclusive (differences between mismatch choices 4.9-6.3 kcal/mol, and the
  model is not a validated predictor of allele discrimination). Reported as an
  unvalidated simplification, not a bug.
