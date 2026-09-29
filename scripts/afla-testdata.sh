#!/usr/bin/env bash
# Downloads a small, REAL test set for AFLA (about 1.5 GB) so every feature can be tried and benchmarked on a laptop:
#  - GIAB Ashkenazi trio exomes (HG002 son, HG003 father, HG004 mother; Illumina NovaSeq, IDT capture), chromosome 20 only,
#    as paired FASTQ files, plus the GIAB v4.2.1 truth sets for scoring (scripts/afla-benchmark.sh)
#  - chr20 of the GRCh38 no-alt reference (bwa-indexed), the capture BED, GATK somatic resources for chr20
#  - an in-silico TUMOUR: HG003 reads with 20% HG002 reads mixed in (HG002-only variants become ~10-15% "somatic" variants),
#    and a matched NORMAL (other HG003 reads); plus a sample sheet for each scenario
# Sources: Google Cloud public buckets of DeepVariant and GATK (GIAB data, public domain / open).
#
#   bash scripts/afla-testdata.sh [FOLDER]      (default: ~/afla-testdata)
# Needs: samtools, bcftools, bwa, python3 (or Docker, used automatically).
set -euo pipefail
D=${1:-$HOME/afla-testdata}
mkdir -p "$D"/{fastq,ref,somatic/fastq,truth}
D=$(cd "$D" && pwd)
cd "$D"
B=https://storage.googleapis.com/deepvariant
G=https://storage.googleapis.com/gatk-best-practices/somatic-hg38
IMG_S=quay.io/biocontainers/samtools:1.21--h96c455f_1
IMG_B=quay.io/biocontainers/bcftools:1.21--h3a4d415_1
IMG_W=quay.io/biocontainers/bwa:0.7.19--h577a1d6_1
t() {  # t IMAGE CMD... : local tool or container
  local img=$1; shift
  if command -v "$1" >/dev/null; then "$@"; else docker run --rm -u "$(id -u):$(id -g)" -v "$D":"$D" -w "$D" "$img" "$@"; fi
}
echo "== reference chr20 (GRCh38 no-alt analysis set)"
[ -s ref/chr20.fa ] || t $IMG_S samtools faidx "$B/case-study-testdata/GCA_000001405.15_GRCh38_no_alt_analysis_set.fa" chr20 > ref/chr20.fa
t $IMG_S samtools faidx ref/chr20.fa; [ -s ref/chr20.dict ] || t $IMG_S samtools dict ref/chr20.fa -o ref/chr20.dict
[ -s ref/chr20.fa.bwt ] || t $IMG_W bwa index ref/chr20.fa
echo "== capture BED (IDT xGen, as used for these exomes)"
curl -fsSL "$B/exome-case-study-testdata/idt_capture_novogene.grch38.no_alt.bed" | awk '$1=="chr20"' > ref/chr20.targets.bed
echo "== GIAB trio exomes (chr20 reads only) and truth sets"
for s in HG002 HG003 HG004; do
  if [ ! -s "fastq/${s}_S1_L001_R1_001.fastq.gz" ]; then
    t $IMG_S samtools view -b -o "$s.chr20.bam" "$B/exome-case-study-testdata/$s.novaseq.wes_idt.100x.dedup.bam" chr20
    t $IMG_S samtools collate -O -u "$s.chr20.bam" "tmp_$s" | t $IMG_S samtools fastq -F 0x900 -1 "fastq/${s}_S1_L001_R1_001.fastq.gz" \
      -2 "fastq/${s}_S1_L001_R2_001.fastq.gz" -0 /dev/null -s /dev/null -n -
    rm -f "$s.chr20.bam" "$s".*.bai
  fi
  [ -s "truth/$s.chr20.vcf.gz" ] || { t $IMG_B bcftools view -r chr20 -Oz -o "truth/$s.chr20.vcf.gz" "$B/case-study-testdata/${s}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz"; t $IMG_B bcftools index -t "truth/$s.chr20.vcf.gz"; }
  curl -fsSL "$B/case-study-testdata/${s}_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed" | awk '$1=="chr20"' > "truth/$s.chr20.bed"
done
rm -f ./*.tbi
echo "== GATK somatic resources (chr20)"
for f in af-only-gnomad.hg38 1000g_pon.hg38; do
  [ -s "ref/$f.chr20.vcf.gz" ] || { curl -fsSL -o "ref/$f.tbi" "$G/$f.vcf.gz.tbi"; t $IMG_B bcftools view -r chr20 -Oz -o "ref/$f.chr20.vcf.gz" "$G/$f.vcf.gz##idx##$D/ref/$f.tbi"; t $IMG_B bcftools index -t "ref/$f.chr20.vcf.gz"; rm -f "ref/$f.tbi"; }
done
echo "== in-silico tumour (HG003 + 20% HG002) and matched normal (other HG003 reads)"
if [ ! -s somatic/fastq/TUMOUR1_S1_L001_R1_001.fastq.gz ]; then
python3 - <<'EOF'
import gzip
def pairs(s):
    a = gzip.open(f'fastq/{s}_S1_L001_R1_001.fastq.gz', 'rt'); b = gzip.open(f'fastq/{s}_S1_L001_R2_001.fastq.gz', 'rt')
    while True:
        r1 = [a.readline() for _ in range(4)]; r2 = [b.readline() for _ in range(4)]
        if not r1[0]:
            break
        yield r1, r2
o = lambda n: gzip.open(n, 'wt', compresslevel=3)
t1, t2 = o('somatic/fastq/TUMOUR1_S1_L001_R1_001.fastq.gz'), o('somatic/fastq/TUMOUR1_S1_L001_R2_001.fastq.gz')
n1, n2 = o('somatic/fastq/NORMAL1_S2_L001_R1_001.fastq.gz'), o('somatic/fastq/NORMAL1_S2_L001_R2_001.fastq.gz')
for i, (r1, r2) in enumerate(pairs('HG003')):
    (t1 if i % 2 else n1).writelines(r1); (t2 if i % 2 else n2).writelines(r2)
for i, (r1, r2) in enumerate(pairs('HG002')):
    if i % 5 == 0:
        t1.writelines(r1); t2.writelines(r2)
for f in (t1, t2, n1, n2):
    f.close()
EOF
fi
t $IMG_B bcftools isec -C -w1 truth/HG002.chr20.vcf.gz truth/HG003.chr20.vcf.gz -Oz -o truth/tumour_spikein.chr20.vcf.gz
cat > trio.csv <<'EOF'
sample,role,sex,family,hpo
HG002,proband,male,AJ,HP:0001250; HP:0001263
HG003,father,male,AJ,
HG004,mother,female,AJ,
EOF
cat > somatic/samples.csv <<'EOF'
sample,role,sex,family,hpo
TUMOUR1,tumour,,P1,
NORMAL1,normal,,P1,
EOF
cat <<EOF

Test data ready in $D ($(du -sh "$D" | cut -f1)).
Try (FASTQ folder / reference / targets in EPI2ME, or on the command line):
  germline trio : --fastq $D/fastq --samplesheet $D/trio.csv --ref $D/ref/chr20.fa --bed $D/ref/chr20.targets.bed --resources_dir <your resources>
  somatic pair  : --mode somatic --fastq $D/somatic/fastq --samplesheet $D/somatic/samples.csv --ref $D/ref/chr20.fa --bed $D/ref/chr20.targets.bed \\
                  --germline_resource $D/ref/af-only-gnomad.hg38.chr20.vcf.gz --panel_of_normals $D/ref/1000g_pon.hg38.chr20.vcf.gz
  score calls   : bash scripts/afla-benchmark.sh --calls <out>/AJ/variants/AJ.vcf.gz --sample HG002 --truth $D/truth/HG002.chr20.vcf.gz \\
                  --truth-bed $D/truth/HG002.chr20.bed --targets $D/ref/chr20.targets.bed --ref $D/ref/chr20.fa
EOF
