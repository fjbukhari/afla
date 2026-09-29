#!/usr/bin/env bash
# AFLA resources installer: downloads and prepares everything the workflows need into ONE folder,
# which you then choose as "Resources folder" in EPI2ME (or --resources_dir on the command line).
#
#   bash scripts/afla-setup.sh [--dir FOLDER] [--only a,b,c] [--skip a,b] [--lean] [--yes] [--list]
#
# Components (default: all except spliceai, which needs a manual download):
#   reference   GRCh38 no-alt analysis set + bwa index (+ .fai/.dict)               ~ 9 GB
#   vep         Ensembl VEP 115 offline cache + Ensembl FASTA + plugins             ~ 30 GB  (--lean: GTF only, ~0.1 GB)
#   clinvar     ClinVar GRCh38 VCF (+ amino-acid index for ACMG PS1/PM5)           ~ 0.2 GB
#   constraint  gnomAD v4.1 gene constraint (LOEUF, missense Z)                     ~ 0.1 GB
#   hpo         Human Phenotype Ontology (hp.obo, genes_to_phenotype)               ~ 0.1 GB
#   panelapp    Genomics England + Australia PanelApp gene panels (green genes)      < 0.1 GB
#   revel       REVEL missense scores (free for non-commercial use)                 ~ 0.7 GB (7 GB temporary)
#   alphamissense  AlphaMissense predictions (CC BY-NC-SA 4.0)                      ~ 0.7 GB
#   somatic     GATK gnomAD af-only germline resource + 1000 Genomes panel of normals ~ 3.5 GB
#   civic       CIViC clinical evidence (CC0)                                        < 0.1 GB
#   refflat     UCSC refFlat gene models (CNV gene names, TMB coding size)           ~ 0.02 GB
#   targets     example exome capture BED (IDT xGen, GRCh38)                         < 0.01 GB
#   msi         msisensor-pro microsatellite list of the reference (1 hour)          ~ 1 GB
#   spliceai    (manual) SpliceAI precomputed scores: instructions only
#
# Files that already exist are kept (delete a folder to re-download it). Nothing is uploaded anywhere.
# Licences: several sources are free for NON-COMMERCIAL / academic use only; by downloading you accept them.
# Education and research use only.
set -uo pipefail

DIR=""
ONLY=""
SKIP=""
LEAN=0
YES=0
ENSEMBL=115
for a in "$@"; do :; done
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR=$2; shift 2 ;;
    --only) ONLY=$2; shift 2 ;;
    --skip) SKIP=$2; shift 2 ;;
    --lean) LEAN=1; shift ;;
    --yes|-y) YES=1; shift ;;
    --list) sed -n '2,31p' "$0"; exit 0 ;;
    -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
    *) echo "Unknown option $1 (see --help)"; exit 1 ;;
  esac
done

# default folder: on Windows/WSL a folder EPI2ME can see (C:\Users\<you>\afla-resources), else ~/afla-resources
if [ -z "$DIR" ]; then
  WINUSER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r' || true)
  if [ -n "$WINUSER" ] && [ -d "/mnt/c/Users/$WINUSER" ]; then DIR="/mnt/c/Users/$WINUSER/afla-resources"; else DIR="$HOME/afla-resources"; fi
fi
mkdir -p "$DIR" || { echo "Cannot create $DIR"; exit 1; }
DIR=$(cd "$DIR" && pwd)
LOG="$DIR/setup.log"
echo "== AFLA setup $(date) into $DIR" | tee -a "$LOG"

want() {  # is component $1 selected?
  local c=$1
  [ -n "$SKIP" ] && [[ ",$SKIP," == *",$c,"* ]] && return 1
  [ -z "$ONLY" ] && { [ "$c" = "spliceai" ] && return 1; return 0; }
  [[ ",$ONLY," == *",$c,"* ]]
}
ask() {  # ask "question" -> 0 yes
  [ $YES -eq 1 ] && return 0
  read -r -p "$1 [y/N] " r; [[ "$r" =~ ^[Yy] ]]
}
free_gb() { df -Pk "$DIR" | awk 'NR==2 {printf "%d", $4/1048576}'; }
need_space() {  # need_space GB what
  local f; f=$(free_gb)
  if [ "$f" -lt "$1" ]; then echo "  ! Only ${f} GB free in $DIR; $2 needs about $1 GB. Skipping." | tee -a "$LOG"; return 1; fi
}
dl() {  # dl URL FILE  (resumes partial downloads)
  local url=$1 out=$2
  [ -s "$out" ] && return 0
  echo "  downloading $(basename "$out") ..." | tee -a "$LOG"
  mkdir -p "$(dirname "$out")"
  if command -v curl >/dev/null; then curl -fL --retry 5 --retry-delay 5 -C - -o "$out.part" "$url" || return 1
  else wget -c -O "$out.part" "$url" || return 1; fi
  mv "$out.part" "$out"
}
# run a bioinformatics tool: local if installed, else in its container (Docker Desktop must be running)
tool() {  # tool IMAGE COMMAND...
  local img=$1; shift
  if command -v "$1" >/dev/null 2>&1; then "$@"; return; fi
  command -v docker >/dev/null || { echo "  ! '$1' not installed and Docker not available." | tee -a "$LOG"; return 1; }
  docker run --rm -u "$(id -u):$(id -g)" -v "$DIR":"$DIR" -w "$PWD" "$img" "$@"
}
SAMTOOLS=quay.io/biocontainers/samtools:1.21--h96c455f_1
HTSLIB=quay.io/biocontainers/htslib:1.21--h566b1c6_1
BWA=quay.io/biocontainers/bwa:0.7.19--h577a1d6_1
VEP=ensemblorg/ensembl-vep:release_115.2
MSI=quay.io/biocontainers/msisensor-pro:1.3.0--hd979922_1
status=()
done_msg() { status+=("$1"); echo "  -> $1" | tee -a "$LOG"; }

echo "Free space now: $(free_gb) GB"

# ---------------------------------------------------------------- reference
if want reference; then
  echo "== reference: GRCh38 no-alt analysis set (NCBI) + bwa index"
  R="$DIR/reference"; FA="$R/GRCh38_no_alt_analysis_set.fa"; mkdir -p "$R"
  existing=$(ls "$R"/*.fa "$R"/*.fasta "$R"/*.fna 2>/dev/null | head -n1)
  if [ -n "$existing" ] && [ -s "$existing.bwt" ]; then done_msg "reference: kept existing $(basename "$existing") (bwa index present)"
  elif need_space 12 "the reference" && ask "Download GRCh38 no-alt reference and bwa index (~9 GB)?"; then
    B=https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids
    if [ ! -s "$FA" ]; then dl "$B/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz" "$R/ref.fna.gz" && gzip -dc "$R/ref.fna.gz" > "$FA" && rm -f "$R/ref.fna.gz"; fi
    tool $SAMTOOLS samtools faidx "$FA" && tool $SAMTOOLS samtools dict "$FA" -o "${FA%.fa}.dict"
    if [ ! -s "$FA.bwt" ]; then
      if dl "$B/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.bwa_index.tar.gz" "$R/bwa_index.tar.gz"; then
        tar -xzf "$R/bwa_index.tar.gz" -C "$R" && for e in amb ann bwt pac sa; do f=$(ls "$R"/*.fna.$e 2>/dev/null | head -n1); [ -n "$f" ] && mv "$f" "$FA.$e"; done; rm -f "$R/bwa_index.tar.gz"
      else
        echo "  bwa index download failed: building it (about 1 hour, ~5 GB RAM)"; tool $BWA bwa index "$FA"
      fi
    fi
    [ -s "$FA.bwt" ] && done_msg "reference: $FA" || done_msg "reference: FAILED (see $LOG)"
  fi
fi

# ---------------------------------------------------------------- VEP
if want vep; then
  V="$DIR/vep"; mkdir -p "$V/Plugins"
  for p in REVEL AlphaMissense SpliceAI; do dl "https://raw.githubusercontent.com/Ensembl/VEP_plugins/release/$ENSEMBL/$p.pm" "$V/Plugins/$p.pm"; done
  if [ $LEAN -eq 1 ]; then
    echo "== vep (lean): Ensembl GTF gene models, no cache"
    if ls "$V"/gtf/*.gtf.gz >/dev/null 2>&1; then done_msg "vep (lean): kept existing GTF"
    else
      mkdir -p "$V/gtf"
      dl "https://ftp.ensembl.org/pub/release-$ENSEMBL/gtf/homo_sapiens/Homo_sapiens.GRCh38.$ENSEMBL.gtf.gz" "$V/gtf/raw.gtf.gz" && \
      zcat "$V/gtf/raw.gtf.gz" | grep -v '^#' | awk 'BEGIN{OFS="\t"} {if($1=="MT")$1="chrM"; else $1="chr"$1; print}' \
        | sort -k1,1 -k4,4n -k5,5n -t$'\t' > "$V/gtf/genes.gtf" && tool $HTSLIB bgzip -f "$V/gtf/genes.gtf" && \
        tool $HTSLIB tabix -f -p gff "$V/gtf/genes.gtf.gz" && rm -f "$V/gtf/raw.gtf.gz"
      done_msg "vep (lean): $V/gtf/genes.gtf.gz (gnomAD frequencies then need --gnomad_vcf; the full cache is recommended)"
    fi
  else
    echo "== vep: Ensembl VEP $ENSEMBL offline cache (GRCh38, indexed) + Ensembl FASTA"
    if [ -d "$V/cache/homo_sapiens/${ENSEMBL}_GRCh38" ]; then done_msg "vep: kept existing cache"
    elif need_space 45 "the VEP cache (download + unpack)" && ask "Download the VEP cache (~26 GB download, ~30 GB unpacked)?"; then
      mkdir -p "$V/cache"
      dl "https://ftp.ensembl.org/pub/release-$ENSEMBL/variation/indexed_vep_cache/homo_sapiens_vep_${ENSEMBL}_GRCh38.tar.gz" "$V/cache.tar.gz" && \
        tar -xzf "$V/cache.tar.gz" -C "$V/cache" && rm -f "$V/cache.tar.gz"
      [ -d "$V/cache/homo_sapiens/${ENSEMBL}_GRCh38" ] && done_msg "vep: cache in $V/cache" || done_msg "vep: cache FAILED"
    fi
    if ls "$V"/fasta/*.fa >/dev/null 2>&1; then :
    elif need_space 4 "the Ensembl FASTA"; then
      mkdir -p "$V/fasta"
      dl "https://ftp.ensembl.org/pub/release-$ENSEMBL/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz" "$V/fasta/ens.fa.gz" && \
        gzip -dc "$V/fasta/ens.fa.gz" > "$V/fasta/Homo_sapiens.GRCh38.dna.primary_assembly.fa" && rm -f "$V/fasta/ens.fa.gz" && \
        tool $SAMTOOLS samtools faidx "$V/fasta/Homo_sapiens.GRCh38.dna.primary_assembly.fa" && done_msg "vep: Ensembl FASTA for HGVS"
    fi
  fi
fi
# chromosome naming used by the annotation files: the VEP cache works with 1,2,..,MT; the lean GTF with chr1..chrM
CHRSTYLE=ensembl; [ $LEAN -eq 1 ] && CHRSTYLE=ucsc

# ---------------------------------------------------------------- ClinVar
if want clinvar; then
  echo "== clinvar: NCBI ClinVar GRCh38 VCF (weekly release)"
  C="$DIR/clinvar"; mkdir -p "$C"
  if [ -s "$C/clinvar.vcf.gz.tbi" ] && [ -z "$(find "$C/clinvar.vcf.gz" -mtime +60 2>/dev/null)" ]; then done_msg "clinvar: kept existing (less than 60 days old)"
  else
    rm -f "$C/clinvar.vcf.gz" "$C/clinvar.vcf.gz.tbi"
    dl https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz "$C/clinvar.vcf.gz" && \
    dl https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi "$C/clinvar.vcf.gz.tbi"
    if [ "$CHRSTYLE" = ucsc ] && [ -s "$C/clinvar.vcf.gz" ]; then
      zcat "$C/clinvar.vcf.gz" | awk 'BEGIN{OFS="\t"} /^##contig=<ID=MT/{sub(/ID=MT/,"ID=chrM")} /^##contig=<ID=[0-9XY]/{sub(/ID=/,"ID=chr")} /^#/{print;next} {if($1=="MT")$1="chrM"; else $1="chr"$1; print}' \
        | tool $HTSLIB bgzip > "$C/clinvar.chr.vcf.gz" && mv "$C/clinvar.chr.vcf.gz" "$C/clinvar.vcf.gz" && tool $HTSLIB tabix -f -p vcf "$C/clinvar.vcf.gz"
    fi
    done_msg "clinvar: $(zcat "$C/clinvar.vcf.gz" 2>/dev/null | head -n 20 | grep -m1 fileDate || echo downloaded)"
  fi
  # amino-acid index for PS1/PM5: pathogenic/likely pathogenic missense variants, annotated once with VEP
  if [ ! -s "$C/clinvar_protein_index.tsv.gz" ] && [ -d "$DIR/vep/cache/homo_sapiens" ] && [ -s "$C/clinvar.vcf.gz" ]; then
    echo "  building the ClinVar amino-acid index (VEP, ~10 minutes)"
    zcat "$C/clinvar.vcf.gz" | awk '/^#/ || (/CLNSIG=(Pathogenic|Likely_pathogenic|Pathogenic\/Likely_pathogenic)[;|,]/ && /missense_variant/)' > "$C/plp_missense.vcf"
    docker run --rm -u "$(id -u):$(id -g)" -v "$DIR":"$DIR" $VEP vep --input_file "$C/plp_missense.vcf" --format vcf \
      --output_file "$C/plp_missense.vep.vcf" --vcf --force_overwrite --offline --cache --dir_cache "$DIR/vep/cache" \
      --cache_version $ENSEMBL --assembly GRCh38 --pick --symbol --hgvs --fasta "$(ls "$DIR"/vep/fasta/*.fa | head -n1)" --fork 4 --no_stats \
      && python3 "$(dirname "$0")/../bin/build_clinvar_protein_index.py" "$C/plp_missense.vep.vcf" "$C/clinvar_protein_index.tsv.gz" \
      && rm -f "$C/plp_missense.vcf" "$C/plp_missense.vep.vcf" && done_msg "clinvar: amino-acid index for PS1/PM5"
  fi
fi

# ---------------------------------------------------------------- gnomAD constraint
if want constraint; then
  echo "== constraint: gnomAD v4.1 gene constraint"
  dl https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/constraint/gnomad.v4.1.constraint_metrics.tsv "$DIR/constraint/gnomad.v4.1.constraint_metrics.tsv" \
    && done_msg "constraint: gnomAD v4.1"
fi

# ---------------------------------------------------------------- HPO
if want hpo; then
  echo "== hpo: Human Phenotype Ontology (latest release)"
  for f in hp.obo genes_to_phenotype.txt phenotype_to_genes.txt; do
    dl "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/$f" "$DIR/hpo/$f"
  done
  done_msg "hpo: $(grep -m1 '^data-version' "$DIR/hpo/hp.obo" 2>/dev/null || echo downloaded)"
fi

# ---------------------------------------------------------------- PanelApp
if want panelapp; then
  echo "== panelapp: Genomics England and Australian Genomics gene panels"
  if [ -s "$DIR/panelapp/panelapp_england.tsv" ] && [ -z "$(find "$DIR/panelapp/panelapp_england.tsv" -mtime +90 2>/dev/null)" ]; then done_msg "panelapp: kept existing"
  else python3 "$(dirname "$0")/panelapp_download.py" "$DIR/panelapp" && done_msg "panelapp: $(ls "$DIR"/panelapp/*.tsv | wc -l) files"; fi
fi

# ---------------------------------------------------------------- REVEL
if want revel; then
  echo "== revel: REVEL v1.3 (free for non-commercial use)"
  RV="$DIR/revel"; mkdir -p "$RV"
  if ls "$RV"/*.tsv.gz.tbi >/dev/null 2>&1; then done_msg "revel: kept existing"
  elif need_space 9 "REVEL preparation" && ask "Download and prepare REVEL (~0.7 GB final, 7 GB temporary)?"; then
    dl https://rothsj06.dmz.hpc.mssm.edu/revel-v1.3_all_chromosomes.zip "$RV/revel.zip"
    # VEP plugin recipe: GRCh38 positions are in column 3
    unzip -p "$RV/revel.zip" | tr "," "\t" | sed '1s/.*/#&/' \
      | awk -v s=$CHRSTYLE 'BEGIN{OFS="\t"} NR==1{print;next} $3!="." { if(s=="ucsc") $1="chr"$1; print }' > "$RV/revel_raw.tsv"
    (head -n1 "$RV/revel_raw.tsv"; tail -n +2 "$RV/revel_raw.tsv" | sort -k1,1 -k3,3n -T "$RV") | tool $HTSLIB bgzip -c > "$RV/new_tabbed_revel_grch38.tsv.gz" \
      && tool $HTSLIB tabix -f -s 1 -b 3 -e 3 "$RV/new_tabbed_revel_grch38.tsv.gz" && rm -f "$RV/revel_raw.tsv" "$RV/revel.zip" \
      && done_msg "revel: $RV/new_tabbed_revel_grch38.tsv.gz"
  fi
fi

# ---------------------------------------------------------------- AlphaMissense
if want alphamissense; then
  echo "== alphamissense: AlphaMissense hg38 (CC BY-NC-SA 4.0)"
  AM="$DIR/alphamissense"; mkdir -p "$AM"
  if ls "$AM"/*.tsv.gz.tbi >/dev/null 2>&1; then done_msg "alphamissense: kept existing"
  elif need_space 2 "AlphaMissense"; then
    dl https://storage.googleapis.com/dm_alphamissense/AlphaMissense_hg38.tsv.gz "$AM/raw.tsv.gz" && \
    zcat "$AM/raw.tsv.gz" | awk -v s=$CHRSTYLE 'BEGIN{OFS="\t"} /^#/{print;next} {if(s=="ensembl"){sub(/^chr/,"",$1); if($1=="M")$1="MT"} print}' \
      | tool $HTSLIB bgzip -c > "$AM/AlphaMissense_hg38.tsv.gz" && tool $HTSLIB tabix -f -s 1 -b 2 -e 2 -c '#' "$AM/AlphaMissense_hg38.tsv.gz" \
      && rm -f "$AM/raw.tsv.gz" && done_msg "alphamissense: $AM/AlphaMissense_hg38.tsv.gz"
  fi
fi

# ---------------------------------------------------------------- somatic resources
if want somatic; then
  echo "== somatic: GATK best-practice resources for Mutect2"
  S="$DIR/somatic"; G=https://storage.googleapis.com/gatk-best-practices/somatic-hg38
  if need_space 5 "somatic resources"; then
    for f in af-only-gnomad.hg38.vcf.gz af-only-gnomad.hg38.vcf.gz.tbi 1000g_pon.hg38.vcf.gz 1000g_pon.hg38.vcf.gz.tbi; do dl "$G/$f" "$S/$f"; done
    done_msg "somatic: af-only gnomAD + 1000g panel of normals (use your own PoN when you have 10+ normals of the assay)"
  fi
fi

# ---------------------------------------------------------------- CIViC
if want civic; then
  echo "== civic: CIViC nightly clinical evidence (CC0)"
  dl https://civicdb.org/downloads/nightly/nightly-ClinicalEvidenceSummaries.tsv "$DIR/civic/nightly-ClinicalEvidenceSummaries.tsv" \
    && dl https://civicdb.org/downloads/nightly/nightly-VariantSummaries.tsv "$DIR/civic/nightly-VariantSummaries.tsv" && done_msg "civic: nightly TSVs"
fi

# ---------------------------------------------------------------- refFlat
if want refflat; then
  echo "== refflat: UCSC hg38 refFlat gene models"
  if [ ! -s "$DIR/annotation/refFlat.txt" ]; then
    dl https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/refFlat.txt.gz "$DIR/annotation/refFlat.txt.gz" && gzip -df "$DIR/annotation/refFlat.txt.gz"
  fi
  [ -s "$DIR/annotation/refFlat.txt" ] && done_msg "refflat: $DIR/annotation/refFlat.txt"
fi

# ---------------------------------------------------------------- example targets
if want targets; then
  dl https://storage.googleapis.com/deepvariant/exome-case-study-testdata/idt_capture_novogene.grch38.bed "$DIR/targets/idt_xgen_exome_v1.grch38.bed" \
    && done_msg "targets: example IDT xGen exome BED (get your own kit's BED from the vendor: Agilent SureDesign, Twist, IDT, Illumina)"
fi

# ---------------------------------------------------------------- MSI list
if want msi; then
  FA=$(ls "$DIR"/reference/*.fa 2>/dev/null | head -n1)
  if [ -n "$FA" ] && ! ls "$DIR"/msi/*.list >/dev/null 2>&1; then
    echo "== msi: scanning the reference for microsatellites (about 1 hour; done once)"
    mkdir -p "$DIR/msi" && tool $MSI msisensor-pro scan -d "$FA" -o "$DIR/msi/$(basename "$FA").microsatellites.list" && done_msg "msi: microsatellite list"
  fi
fi

# ---------------------------------------------------------------- SpliceAI (manual)
if want spliceai; then
  cat <<EOF
== spliceai: precomputed SpliceAI scores cannot be downloaded automatically (Illumina BaseSpace login; free for
   non-commercial use). Download "spliceai_scores.masked.snv.hg38.vcf.gz" and "spliceai_scores.masked.indel.hg38.vcf.gz"
   (+ .tbi) from https://basespace.illumina.com/s/otSPW8hnhaZR into: $DIR/spliceai/
   They are large (~30 GB and ~60 GB); without them, SpliceAI is simply not shown.
EOF
fi

echo
echo "== Summary ($(free_gb) GB free now)"; printf '  %s\n' "${status[@]}"
cat <<EOF

Use this folder in EPI2ME as "Resources folder":  $DIR
(Windows path: $(wslpath -w "$DIR" 2>/dev/null || echo "$DIR"))
Log: $LOG
EOF
