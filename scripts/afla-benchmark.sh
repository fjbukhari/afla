#!/usr/bin/env bash
# Benchmarks AFLA variant calls against a truth set (GIAB reference samples) with RTG vcfeval
# (the comparison engine used by hap.py / precisionFDA). Reports precision, recall (sensitivity) and F1 for SNVs and indels.
#
#   bash scripts/afla-benchmark.sh --calls output/HG002/variants/HG002.vcf.gz --truth HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz \
#        --truth-bed HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed --targets kit.bed --ref GRCh38.fa [--sample HG002] [--out bench_HG002]
#
# Truth sets (free): https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/  (also mirrored in
# https://storage.googleapis.com/deepvariant/case-study-testdata/). Test data: GIAB HG002/HG003/HG004 exomes, e.g.
# https://storage.googleapis.com/deepvariant/exome-case-study-testdata/HG002.novaseq.wes_idt.100x.dedup.bam
# Only the intersection of the truth confident regions and your targets is scored. Uses Docker if rtg is not installed.
set -euo pipefail
CALLS=""; TRUTH=""; TBED=""; TARGETS=""; REF=""; SAMPLE=""; OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --calls) CALLS=$2; shift 2 ;; --truth) TRUTH=$2; shift 2 ;; --truth-bed) TBED=$2; shift 2 ;;
    --targets) TARGETS=$2; shift 2 ;; --ref) REF=$2; shift 2 ;; --sample) SAMPLE=$2; shift 2 ;; --out) OUT=$2; shift 2 ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
  esac
done
[ -n "$CALLS" ] && [ -n "$TRUTH" ] && [ -n "$TBED" ] && [ -n "$REF" ] || { sed -n '2,12p' "$0"; exit 1; }
OUT=${OUT:-bench_$(basename "${CALLS%%.*}")}
RTG_IMG=quay.io/biocontainers/rtg-tools:3.13--hdfd78af_0
BT_IMG=quay.io/biocontainers/bedtools:2.31.1--h13024bc_3
run() {  # run IMAGE CMD...
  local img=$1; shift
  if command -v "$1" >/dev/null; then "$@"
  else docker run --rm -u "$(id -u):$(id -g)" -v "$HOME":"$HOME" -v /mnt:/mnt -v /tmp:/tmp -v "$PWD":"$PWD" -w "$PWD" "$img" "$@"; fi
}
mkdir -p "$OUT.work"
SDF="${REF%.*}.sdf"
[ -d "$SDF" ] || run $RTG_IMG rtg format -o "$SDF" "$REF"
EVAL="$OUT.work/eval.bed"
if [ -n "$TARGETS" ]; then
  grep -vE '^(#|track|browser)' "$TARGETS" | cut -f1-3 | sort -k1,1 -k2,2n > "$OUT.work/t.bed"
  sort -k1,1 -k2,2n "$TBED" | cut -f1-3 > "$OUT.work/c.bed"
  run $BT_IMG bedtools intersect -a "$OUT.work/t.bed" -b "$OUT.work/c.bed" > "$EVAL"
else
  cp "$TBED" "$EVAL"
fi
echo "Scored region: $(awk '{s+=$3-$2} END {printf "%.2f Mb", s/1e6}' "$EVAL")"
S=""; [ -n "$SAMPLE" ] && S="--sample $SAMPLE,$SAMPLE"
rm -rf "$OUT"
run $RTG_IMG rtg vcfeval -b "$TRUTH" -c "$CALLS" -t "$SDF" -e "$EVAL" -o "$OUT" $S --all-records --vcf-score-field QUAL --decompose \
  | tee "$OUT.rtg.txt" | tail -n 2
# per-type counts from the annotated output
summ() {  # summ TYPE (snv|indel)
  local sel
  [ "$1" = snv ] && sel='length($4)==1 && length($5)==1' || sel='!(length($4)==1 && length($5)==1)'
  local tp fn fp
  tp=$(zcat "$OUT/tp-baseline.vcf.gz" | awk "!/^#/ && $sel" | wc -l)
  fn=$(zcat "$OUT/fn.vcf.gz" | awk "!/^#/ && $sel" | wc -l)
  fp=$(zcat "$OUT/fp.vcf.gz" | awk "!/^#/ && $sel && (\$7==\"PASS\" || \$7==\".\")" | wc -l)
  awk -v t=$1 -v tp=$tp -v fn=$fn -v fp=$fp 'BEGIN{r=(tp+fn)?tp/(tp+fn):0; p=(tp+fp)?tp/(tp+fp):0; f=(r+p)?2*r*p/(r+p):0;
    printf "%-6s truth %6d  found %6d  missed %5d  false %5d   recall %.4f  precision %.4f  F1 %.4f\n", t, tp+fn, tp, fn, fp, r, p, f}'
}
echo "Type   (PASS calls, inside targets and GIAB confident regions)"
summ snv | tee "$OUT.summary.txt"
summ indel | tee -a "$OUT.summary.txt"
echo "Details: $OUT/ (tp, fp, fn VCFs: open them in IGV to see why a variant was missed or wrongly called)"
