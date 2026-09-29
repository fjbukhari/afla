#!/usr/bin/env sh
# Usage: match_chr_names.sh <in.bed> <ref.fa.fai>
# Keeps all BED columns, renames chromosomes to the reference style ("chr1" or "1", chrM/MT),
# drops lines on contigs the reference does not have, and sorts.
set -eu
awk -v OFS='\t' '
  NR==FNR { len[$1]=1; next }
  /^(#|track|browser)/ || NF<3 { next }
  {
    c=$1
    if (!(c in len)) { if (("chr" c) in len) c="chr" c; else { d=c; sub(/^chr/,"",d); if (d in len) c=d; else if ((c=="chrM"||c=="M") && ("MT" in len)) c="MT"; else if ((c=="MT") && ("chrM" in len)) c="chrM"; else next } }
    $1=c; print
  }' "$2" "$1" | sort -k1,1 -k2,2n
