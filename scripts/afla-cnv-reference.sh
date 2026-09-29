#!/usr/bin/env bash
# Builds a CNVkit reference (.cnn) from NORMAL samples sequenced with the same capture kit/panel.
# Use it as "CNV reference" in the form: CNV calls become far more reliable than with a flat reference.
#
#   bash scripts/afla-cnv-reference.sh --bams "normals/*.cram" --bed kit.bed --ref GRCh38.fa --out kit_reference.cnn \
#        [--refflat refFlat.txt] [--threads 8]
# 10 or more normals are recommended (same kit, similar DNA quality, same lab process). Uses Docker if CNVkit is not installed.
set -euo pipefail
BAMS=""; BED=""; REF=""; OUT=""; REFFLAT=""; T=4
while [ $# -gt 0 ]; do
  case "$1" in
    --bams) BAMS=$2; shift 2 ;; --bed) BED=$2; shift 2 ;; --ref) REF=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;; --refflat) REFFLAT=$2; shift 2 ;; --threads) T=$2; shift 2 ;;
    *) sed -n '2,9p' "$0"; exit 1 ;;
  esac
done
[ -n "$BAMS" ] && [ -n "$BED" ] && [ -n "$REF" ] && [ -n "$OUT" ] || { sed -n '2,9p' "$0"; exit 1; }
IMG=quay.io/biocontainers/cnvkit:0.9.14--pyhdfd78af_0
cnvkit() {
  if command -v cnvkit.py >/dev/null; then cnvkit.py "$@"
  # files must be under your home folder or /mnt (Windows drives), which are shared with the container
  else docker run --rm -u "$(id -u):$(id -g)" -v "$HOME":"$HOME" -v /mnt:/mnt -v /tmp:/tmp -w "$PWD" $IMG cnvkit.py "$@"; fi
}
W=$(mktemp -d "${OUT%.cnn}.tmp.XXXX")
ANN=""; [ -n "$REFFLAT" ] && ANN="--annotate $REFFLAT"
grep -vE '^(#|track|browser)' "$BED" | cut -f1-3 | sort -k1,1 -k2,2n > "$W/targets.bed"
cnvkit target "$W/targets.bed" $ANN --split --avg-size 267 -o "$W/cnv_targets.bed"
n=0
for b in $BAMS; do
  s=$(basename "$b"); s=${s%%.*}
  cnvkit coverage -p "$T" -f "$REF" "$b" "$W/cnv_targets.bed" -o "$W/$s.targetcoverage.cnn"
  n=$((n+1))
done
[ $n -ge 3 ] || echo "Warning: only $n normals; 10+ are recommended."
cnvkit reference "$W"/*.targetcoverage.cnn -f "$REF" -o "$OUT"
rm -rf "$W"
echo "CNV reference from $n normals: $OUT"
