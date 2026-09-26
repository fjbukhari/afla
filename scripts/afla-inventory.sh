#!/usr/bin/env bash
# AFLA inventory: read-only survey of a WSL/Linux machine's bioinformatics setup
# (tools, containers, references, annotation databases, free space).
# It never modifies, uploads or deletes anything. Paths under $HOME are shown as "~".
#
# Usage:  bash afla-inventory.sh [extra_dir ...]
#   e.g.  bash afla-inventory.sh /mnt/d/genomics      # also scan a Windows drive folder (slower)
# Output: printed and saved to ./afla-inventory-<date>.txt

set -u
ROOTS=("$HOME" /opt /data /srv /media /usr/local/share "$@")
OUT="afla-inventory-$(date +%Y%m%d-%H%M).txt"
TMO=15   # seconds allowed per version command

exec > >(sed "s#${HOME}#~#g" | tee "$OUT") 2>&1

hr()  { printf '\n==== %s ====\n' "$1"; }
have(){ command -v "$1" >/dev/null 2>&1; }
hsize(){ du -sh "$1" 2>/dev/null | cut -f1; }
existing_roots() { for r in "${ROOTS[@]}"; do [ -d "$r" ] && echo "$r"; done | sort -u; }
# find limited to real WSL filesystems (-xdev) except explicitly passed extra dirs
ffind() { local r; for r in $(existing_roots); do find "$r" -xdev \( -path '*/proc' -o -path '*/.cache/pip' -o -path '*/node_modules' -o -path '*/.git' \) -prune -o "$@" 2>/dev/null; done; }
peek_vcf() { # header lines worth knowing (date, source, reference, version)
  { case "$1" in *.gz|*.bgz) gzip -cd "$1" ;; *) cat "$1" ;; esac; } 2>/dev/null | head -n 400 |
    grep -E '^##(fileDate|source|reference|VEP|gnomad|dbSNP_BUILD_ID|assembly)|^##contig=<ID=(chr)?1,' | head -n 6 | sed 's/^/      /'
}

hr "AFLA inventory $(date -Iseconds)"
echo "Scanned roots: $(existing_roots | tr '\n' ' ')"

hr "System"
grep -E '^PRETTY_NAME' /etc/os-release 2>/dev/null
uname -r
echo "CPUs: $(nproc)"; free -g | sed -n '1,2p'
grep -qi microsoft /proc/version 2>/dev/null && echo "Running under WSL"
for f in /mnt/c/Users/*/.wslconfig; do [ -f "$f" ] && { echo "--- $f"; cat "$f"; }; done

hr "Disk space"
df -h "$HOME" / /tmp 2>/dev/null | awk '!seen[$0]++'
for r in "$@"; do df -h "$r" 2>/dev/null | tail -n1; done

hr "GPU"
if have nvidia-smi; then nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; else echo "nvidia-smi not found"; fi

hr "Docker"
if have docker && docker info >/dev/null 2>&1; then
  docker version --format 'Docker {{.Server.Version}}'
  docker info 2>/dev/null | grep -iE 'Runtimes|Docker Root Dir|Total Memory|CPUs'
  echo "--- images (repository:tag  size  created)"
  docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}' | sort
  echo "--- space"; docker system df
else echo "Docker not available from WSL (not installed, not running, or WSL integration off)"; fi

hr "Singularity / Apptainer"
for t in apptainer singularity; do have $t && echo "$t: $($t --version 2>/dev/null)"; done
ffind -type f \( -name '*.sif' -o -name '*.simg' \) -size +10M -printf '%s\t%p\n' | awk -F'\t' '{printf "%7.1f GB  %s\n",$1/1e9,$2}' | sort -k3

hr "Nextflow / Java / EPI2ME"
have java && java -version 2>&1 | grep -m1 -i version
have nextflow && timeout $TMO nextflow -version 2>/dev/null | grep -i version
[ -d "$HOME/.nextflow" ] && echo "~/.nextflow present ($(hsize "$HOME/.nextflow"))"
for d in "$HOME"/epi2melabs* "$HOME"/.epi2me* /mnt/c/Users/*/epi2melabs*; do
  [ -d "$d" ] || continue; echo "EPI2ME dir: $d ($(hsize "$d"))"
  ls -1 "$d"/workflows/*/* 2>/dev/null | sed -n '1,40p' | sed 's/^/   /'
done

hr "Conda / mamba environments"
CONDA=""; for c in mamba micromamba conda; do have $c && { CONDA=$c; break; }; done
if [ -n "$CONDA" ]; then $CONDA env list 2>/dev/null | grep -v '^#'; else echo "no conda/mamba on PATH"; fi
for base in "$HOME"/miniconda3 "$HOME"/miniforge3 "$HOME"/mambaforge "$HOME"/anaconda3 "$HOME"/micromamba /opt/conda; do
  [ -d "$base" ] && echo "conda base: $base ($(hsize "$base"))"
done

hr "Bioinformatics tools (PATH and conda envs)"
TOOLS="fastp fastqc multiqc bwa bwa-mem2 minimap2 samtools bcftools bgzip tabix bedtools mosdepth picard gatk \
run_deepvariant freebayes strelka2 configureStrelkaGermlineWorkflow.py configManta.py vep filter_vep snpEff \
cnvkit.py slivar somalier hap.py kraken2 bracken metaphlan spades.py shovill quast.py mlst amrfinder abricate \
exomiser-cli nextflow hostile"
ENV_BINS=$(ls -d "$HOME"/*conda*/envs/*/bin "$HOME"/*forge*/envs/*/bin "$HOME"/micromamba/envs/*/bin /opt/conda/envs/*/bin "$HOME"/*conda*/bin "$HOME"/*forge*/bin 2>/dev/null)
for t in $TOOLS; do
  locs=""; have "$t" && locs="$(command -v "$t")"
  for b in $ENV_BINS; do [ -x "$b/$t" ] && locs="$locs $b/$t"; done
  [ -z "$locs" ] && continue
  for l in $locs; do
    v=$( (timeout $TMO "$l" --version 2>&1 || timeout $TMO "$l" version 2>&1 || timeout $TMO "$l" 2>&1) | grep -m1 -iE 'version|v[0-9]+\.[0-9]|[0-9]+\.[0-9]+' | cut -c1-90)
    printf '%-22s %s  [%s]\n' "$t" "${v:-?}" "$l"
  done
done

hr "Reference genomes (FASTA > 300 MB) and their indexes"
ffind -type f \( -name '*.fa' -o -name '*.fasta' -o -name '*.fna' -o -name '*.fa.gz' -o -name '*.fasta.gz' -o -name '*.fna.gz' \) -size +300M -print |
while read -r fa; do
  echo "* $fa  ($(hsize "$fa"))"
  fai="$fa.fai"
  if [ -f "$fai" ]; then
    n=$(wc -l < "$fai"); c1=$(awk '$1=="chr1"||$1=="1"{print $1":"$2; exit}' "$fai")
    case "$c1" in *:248956422) b="GRCh38";; *:249250621) b="GRCh37/hg19";; *) b="unknown";; esac
    alt=$(grep -c '_alt' "$fai"); dec=$(grep -c -E 'decoy|chrEBV|hs38d1|_decoy' "$fai"); hla=$(grep -c '^HLA' "$fai")
    echo "    build=$b  contigs=$n  chr1=$c1  alt=$alt  decoy/EBV=$dec  HLA=$hla"
  else echo "    no .fai index"; fi
  idx=""
  for e in .fai .gzi; do [ -f "$fa$e" ] && idx="$idx $e"; done
  d="${fa%.gz}"; d="${d%.*}.dict"; [ -f "$d" ] && idx="$idx .dict"
  [ -f "$fa.bwt" ] && idx="$idx bwa($(du -ch "$fa".{amb,ann,bwt,pac,sa} 2>/dev/null | tail -n1 | cut -f1))"
  [ -f "$fa.bwt.2bit.64" ] && idx="$idx bwa-mem2($(du -ch "$fa".{0123,bwt.2bit.64} 2>/dev/null | tail -n1 | cut -f1))"
  ls "${fa%.gz}"*.mmi >/dev/null 2>&1 && idx="$idx minimap2"
  echo "    indexes:${idx:- none}"
done

hr "Ensembl VEP caches and plugins"
ffind -type d -regex '.*/homo_sapiens\(_refseq\|_merged\)?/[0-9]+_GRCh3[78]' -print | while read -r d; do echo "  $d  ($(hsize "$d"))"; done
ffind -type d -name Plugins -path '*vep*' -print | while read -r d; do echo "  plugins dir: $d ($(ls "$d" | wc -l) files)"; done

hr "Annotation / known-sites resources"
ffind -type f \( -iname '*clinvar*' -o -iname '*gnomad*' -o -iname '*revel*' -o -iname '*alphamissense*' -o -iname '*spliceai*' \
  -o -iname 'whole_genome_SNVs*' -o -iname '*cadd*' -o -iname 'dbNSFP*' -o -iname '*dbsnp*' -o -iname '*Mills*' -o -iname '*1000G*' \
  -o -iname '*hapmap*' -o -iname '*af-only*' -o -iname '*panel_of_normals*' -o -iname '*pon*.vcf*' -o -iname '*intervar*' \
  -o -iname 'hp.obo' -o -iname '*phenotype_to_genes*' -o -iname '*genes_to_phenotype*' -o -iname '*panelapp*' -o -iname '*gnomad*constraint*' \) \
  \( -name '*.vcf' -o -name '*.vcf.gz' -o -name '*.bgz' -o -name '*.tsv*' -o -name '*.txt*' -o -name '*.zip' -o -name '*.obo' -o -name '*.csv*' \) \
  -printf '%s\t%p\n' | sort -t$'\t' -k2 | while IFS=$'\t' read -r s p; do
    ix=""; for e in .tbi .csi .idx; do [ -f "$p$e" ] && ix="$ix$e"; done
    printf '  %8.2f GB  %s  %s\n' "$(awk -v s="$s" 'BEGIN{print s/1e9}')" "$p" "${ix:+[index $ix]}"
    case "$p" in *.vcf|*.vcf.gz|*.bgz) peek_vcf "$p";; esac
  done

hr "Capture kit / target BED files"
ffind -type f \( -iname '*.bed' -o -iname '*.bed.gz' -o -iname '*.interval_list' \) -size +20k -printf '%s\t%p\n' |
  awk -F'\t' '{printf "  %7.1f MB  %s\n",$1/1e6,$2}' | sort -k3 | head -n 60

hr "Kraken2 / metagenomics / Exomiser databases"
ffind -type f -name 'hash.k2d' -printf '%h\n' | while read -r d; do echo "  Kraken2 DB: $d ($(hsize "$d"))"; done
ffind -maxdepth 6 -type d -iname '*exomiser*' -print | while read -r d; do echo "  Exomiser: $d ($(hsize "$d"))"; ls "$d" | head -n 10 | sed 's/^/     /'; done
ffind -maxdepth 6 -type d \( -iname '*metaphlan*' -o -iname '*amrfinder*' -o -iname '*card*db*' \) -print | while read -r d; do echo "  $d ($(hsize "$d"))"; done

hr "Sequencing data (FASTQ/BAM/CRAM/VCF) summary by folder"
ffind -type f \( -name '*.fastq.gz' -o -name '*.fq.gz' -o -name '*.fastq' -o -name '*.bam' -o -name '*.cram' -o -name '*.g.vcf.gz' \) -printf '%h\t%s\n' |
  awk -F'\t' '{n[$1]++; s[$1]+=$2} END{for(d in n) printf "  %6.1f GB  %4d files  %s\n", s[d]/1e9, n[d], d}' | sort -k5
fq=$(ffind -type f \( -name '*.fastq.gz' -o -name '*.fq.gz' \) -print -quit)
if [ -n "$fq" ]; then
  echo "  First read header of one FASTQ (platform/read-length check, no sample data):"
  gzip -cd "$fq" 2>/dev/null | head -n 2 | awk 'NR==1{print "    "$0} NR==2{print "    read length: " length($0)}'
fi

hr "Largest files (> 1 GB), for cleanup decisions"
ffind -type f -size +1G -printf '%s\t%p\n' | sort -rn | head -n 40 | awk -F'\t' '{printf "  %6.1f GB  %s\n",$1/1e9,$2}'

hr "Done"
echo "Saved to $(pwd)/$OUT. Review it (it lists file paths) before sharing."
