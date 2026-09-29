// Read clean-up, alignment, UMI consensus, primer clipping and coverage.

// fastp: removes adapters and low-quality ends, writes a QC report. Several lanes are joined first.
// With UMIs the reads must keep their structure for fgbio, so fastp then only reports (no trimming).
process FASTP {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/fastp:1.3.7--h43da1c4_0"
    publishDir { "${params.out_dir}/${sample}/qc" }, mode: "copy", pattern: "*.{html,json}"
    input:
    tuple val(sample), path(r1), path(r2)
    val qc_only
    output:
    tuple val(sample), path("${sample}.R1.trim.fq.gz"), path("${sample}.R2.trim.fq.gz"), emit: reads
    path "${sample}.fastp.json", emit: json
    path "${sample}.fastp.html"
    script:
    def r1s = r1 instanceof List ? r1 : [r1]
    def r2s = r2 instanceof List ? r2 : [r2]
    def in1 = r1s.size() > 1 ? "lanes_R1.fq.gz" : r1s[0]
    def in2 = r2s.size() > 1 ? "lanes_R2.fq.gz" : r2s[0]
    def join = r1s.size() > 1 ? "cat ${r1s.join(' ')} > lanes_R1.fq.gz; cat ${r2s.join(' ')} > lanes_R2.fq.gz" : ""
    def mode = qc_only ? "--disable_adapter_trimming --disable_quality_filtering --disable_length_filtering --disable_trim_poly_g" : "--detect_adapter_for_pe"
    """
    ${join}
    fastp -i ${in1} -I ${in2} \
      -o ${sample}.R1.trim.fq.gz -O ${sample}.R2.trim.fq.gz \
      ${mode} -w ${task.cpus} \
      -j ${sample}.fastp.json -h ${sample}.fastp.html -R "${sample} fastp report"
    """
}

// bwa mem -> (duplicate marking) -> sorted, indexed CRAM or BAM. Streamed: no large temporary SAM file.
process ALIGN {
    tag "${sample}"
    label "big"
    container "quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0"
    publishDir { "${params.out_dir}/${sample}/alignment" }, mode: "copy", saveAs: { f -> keep_for_clip ? null : f }
    input:
    tuple val(sample), path(r1), path(r2)
    path ref_files
    val ref_name
    val dedup
    val keep_for_clip
    output:
    tuple val(sample), path("${sample}.${params.output_format}"), path("${sample}.${params.output_format}.{crai,bai}"), emit: aln
    path "${sample}.flagstat.txt", emit: flagstat
    path "${sample}.markdup.txt", optional: true, emit: markdup
    script:
    def r1s = r1 instanceof List ? r1 : [r1]
    def r2s = r2 instanceof List ? r2 : [r2]
    def fmt = params.output_format == "bam" ? "BAM" : "CRAM"
    def t = task.cpus
    def rg = "@RG\\tID:${sample}\\tSM:${sample}\\tLB:${sample}\\tPL:ILLUMINA"
    def sort_mem = Math.max(256, (int) (task.memory.toMega() * 0.5 / t))
    def tail = dedup ?
        "samtools fixmate -m - - | samtools sort -@ ${t} -m ${sort_mem}M -T tmp_sort - | samtools markdup -@ ${t} -s -f ${sample}.markdup.txt --reference ${ref_name} -O ${fmt} - ${sample}.${params.output_format}" :
        "samtools sort -@ ${t} -m ${sort_mem}M -T tmp_sort --reference ${ref_name} -O ${fmt} -o ${sample}.${params.output_format} -"
    """
    bwa mem -t ${t} -Y -R '${rg}' ${ref_name} <(cat ${r1s.join(' ')}) <(cat ${r2s.join(' ')}) \
      | ${tail}
    samtools index -@ ${t} ${sample}.${params.output_format}
    samtools flagstat -@ ${t} --input-fmt-option reference=${ref_name} ${sample}.${params.output_format} > ${sample}.flagstat.txt
    """
}

// Amplicon panels: soft-clip the primer sequences, so primer bases (which copy the primer, not the patient's
// DNA) cannot hide or fake variants at amplicon ends. Reads are re-sorted because clipping moves start positions.
process PRIMER_CLIP {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
    publishDir { "${params.out_dir}/${sample}/alignment" }, mode: "copy"
    input:
    tuple val(sample), path(aln), path(idx)
    path primers
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.${params.output_format}", includeInputs: true), path("${sample}.${params.output_format}.{crai,bai}", includeInputs: true), emit: aln
    path "${sample}.flagstat.txt", emit: flagstat
    path "${sample}.primerclip.txt", emit: stats
    path "${sample}.primer_counts.bedgraph", emit: counts
    script:
    def fmt = params.output_format == "bam" ? "BAM" : "CRAM"
    // strand-aware clipping when the primer BED says which strand each primer is on
    """
    STRAND=\$(awk 'NF>=6 && (\$6=="+"||\$6=="-"){n++} END{print (n>0 && n==NR) ? "--strand" : ""}' ${primers})
    mv ${aln} input.${aln.extension}; mv ${idx} input.${aln.extension}.${idx.extension}
    samtools ampliconclip -@ ${task.cpus} --reference ${ref_name} --soft-clip --both-ends \$STRAND --tolerance 5 \
      --filter-len 30 -b ${primers} -f ${sample}.primerclip.txt --primer-counts ${sample}.primer_counts.bedgraph \
      -u input.${aln.extension} \
      | samtools sort -@ ${task.cpus} -T tmp_sort --reference ${ref_name} -O ${fmt} -o ${sample}.${params.output_format} -
    samtools index -@ ${task.cpus} ${sample}.${params.output_format}
    samtools flagstat -@ ${task.cpus} --input-fmt-option reference=${ref_name} ${sample}.${params.output_format} > ${sample}.flagstat.txt
    """
}

// Existing BAM/CRAM given as input: make sure it has an index, and collect alignment statistics.
process INDEX_INPUT_ALN {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
    input:
    tuple val(sample), path(aln)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path(aln), path("${aln}.{crai,bai}"), emit: aln
    path "${sample}.flagstat.txt", emit: flagstat
    script:
    def ext = aln.name.endsWith(".cram") ? "crai" : "bai"
    """
    samtools index -@ ${task.cpus} ${aln} ${aln}.${ext}
    samtools flagstat -@ ${task.cpus} --input-fmt-option reference=${ref_name} ${aln} > ${sample}.flagstat.txt
    """
}

// mosdepth: depth over the target regions, and the share of target bases reaching 10x/20x/30x/50x/100x/500x.
process COVERAGE {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/mosdepth:0.3.10--h4e814b3_1"
    publishDir { "${params.out_dir}/${sample}/qc" }, mode: "copy"
    input:
    tuple val(sample), path(aln), path(idx), path(bed)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.mosdepth.summary.txt"), path("${sample}.thresholds.bed.gz"), path("${sample}.regions.bed.gz"), emit: files
    script:
    """
    mosdepth -t ${task.cpus} -n --fasta ${ref_name} --by ${bed} --thresholds 10,20,30,50,100,500 ${sample} ${aln}
    """
}

// ---------------------------------------------------------------- UMI consensus (fgbio best-practice outline)
// 1) FASTQ -> unmapped BAM with the UMI stored in the RX tag (from the read itself, or from the read name)
process UMI_FASTQ_TO_BAM {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/fgbio:4.1.1--hdfd78af_0"
    input:
    tuple val(sample), path(r1), path(r2)
    output:
    tuple val(sample), path("${sample}.unmapped.bam")
    script:
    def r1s = r1 instanceof List ? r1 : [r1]
    def r2s = r2 instanceof List ? r2 : [r2]
    def rs = params.umi_mode == "read_name" ? "+T +T" : params.umi_read_structure
    def from_name = params.umi_mode == "read_name" ? "--extract-umis-from-read-names true" : ""
    """
    cat ${r1s.join(' ')} > R1.fq.gz; cat ${r2s.join(' ')} > R2.fq.gz
    fgbio -Xmx${task.memory.toGiga() - 1}g --compression 1 FastqToBam --input R1.fq.gz R2.fq.gz \
      --read-structures ${rs} ${from_name} --sample ${sample} --library ${sample} \
      --platform ILLUMINA --read-group-id ${sample} --output ${sample}.unmapped.bam
    rm R1.fq.gz R2.fq.gz
    """
}

// 2) align an unmapped BAM (raw reads, or later the consensus reads); output keeps the input order
process BWA_UBAM {
    tag "${sample} ${stage}"
    label "big"
    container "quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0"
    input:
    tuple val(sample), path(ubam)
    path ref_files
    val ref_name
    val stage
    output:
    tuple val(sample), path(ubam), path("${sample}.${stage}.mapped.bam")
    script:
    """
    samtools fastq -@ 2 ${ubam} | bwa mem -t ${task.cpus} -p -K 150000000 -Y ${ref_name} - \
      | samtools view -@ 2 -b -o ${sample}.${stage}.mapped.bam -
    """
}

// 3) join mapped + unmapped (keeps the UMI tags), group reads by UMI, make one consensus read per family, filter
process UMI_CONSENSUS {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/fgbio:4.1.1--hdfd78af_0"
    publishDir { "${params.out_dir}/${sample}/qc" }, mode: "copy", pattern: "*.umi_family_sizes.txt"
    input:
    tuple val(sample), path(ubam), path(mapped)
    path ref_files
    val ref_name
    val min_reads
    output:
    tuple val(sample), path("${sample}.consensus.unmapped.bam"), emit: ubam
    path "${sample}.umi_family_sizes.txt", emit: families
    script:
    def x = "-Xmx${task.memory.toGiga() - 1}g --compression 1"
    """
    fgbio ${x} ZipperBams --input ${mapped} --unmapped ${ubam} --ref ${ref_name} --output zipped.bam
    fgbio ${x} SortBam --input zipped.bam --sort-order TemplateCoordinate --output tc.bam
    rm zipped.bam
    fgbio ${x} GroupReadsByUmi --input tc.bam --strategy Adjacency --edits 1 --min-map-q 20 \
      --family-size-histogram ${sample}.umi_family_sizes.txt --output grouped.bam
    rm tc.bam
    fgbio ${x} CallMolecularConsensusReads --input grouped.bam --min-reads ${min_reads} \
      --read-name-prefix ${sample} --output consensus.bam
    rm grouped.bam
    fgbio ${x} FilterConsensusReads --input consensus.bam --ref ${ref_name} --min-reads ${min_reads} \
      --max-read-error-rate 0.05 --min-base-quality 20 --max-base-error-rate 0.1 --max-no-calls 0.2 \
      --output ${sample}.consensus.unmapped.bam
    """
}

// 4) after re-aligning the consensus reads: join tags back, then coordinate-sort to CRAM/BAM
process UMI_FINALISE {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/fgbio:4.1.1--hdfd78af_0"
    input:
    tuple val(sample), path(ubam), path(mapped)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.consensus.zipped.bam")
    script:
    """
    fgbio -Xmx${task.memory.toGiga() - 1}g --compression 1 ZipperBams --input ${mapped} --unmapped ${ubam} \
      --ref ${ref_name} --tags-to-reverse Consensus --tags-to-revcomp Consensus --output ${sample}.consensus.zipped.bam
    """
}

process SORT_INDEX {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
    publishDir { "${params.out_dir}/${sample}/alignment" }, mode: "copy", saveAs: { f -> keep_for_clip ? null : f }
    input:
    tuple val(sample), path(bam)
    path ref_files
    val ref_name
    val keep_for_clip
    output:
    tuple val(sample), path("${sample}.${params.output_format}"), path("${sample}.${params.output_format}.{crai,bai}"), emit: aln
    path "${sample}.flagstat.txt", emit: flagstat
    script:
    def fmt = params.output_format == "bam" ? "BAM" : "CRAM"
    """
    samtools sort -@ ${task.cpus} -T tmp_sort --reference ${ref_name} -O ${fmt} -o ${sample}.${params.output_format} ${bam}
    samtools index -@ ${task.cpus} ${sample}.${params.output_format}
    samtools flagstat -@ ${task.cpus} --input-fmt-option reference=${ref_name} ${sample}.${params.output_format} > ${sample}.flagstat.txt
    """
}
