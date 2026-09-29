// Read clean-up, alignment and coverage.

// fastp: removes adapters and low-quality ends, writes a QC report. Several lanes are joined first.
process FASTP {
    tag "${sample}"
    container "staphb/fastp:1.3.3"
    cpus 8
    publishDir { "${params.out_dir}/${sample}/qc" }, mode: "copy", pattern: "*.{html,json}"
    input:
    tuple val(sample), path(r1), path(r2)
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
    """
    ${join}
    fastp -i ${in1} -I ${in2} \
      -o ${sample}.R1.trim.fq.gz -O ${sample}.R2.trim.fq.gz \
      --detect_adapter_for_pe -w ${task.cpus} \
      -j ${sample}.fastp.json -h ${sample}.fastp.html -R "${sample} fastp report"
    """
}

// bwa mem -> (duplicate marking) -> sorted, indexed CRAM or BAM. Streamed: no large temporary SAM file.
process ALIGN {
    tag "${sample}"
    label "big"
    container "quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0"
    publishDir { "${params.out_dir}/${sample}/alignment" }, mode: "copy"
    input:
    tuple val(sample), path(r1), path(r2)
    path ref_files
    val ref_name
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
    def dedup = (params.mark_duplicates.toString() == 'true') ?
        "samtools fixmate -m - - | samtools sort -@ ${t} -m 1G -T tmp_sort - | samtools markdup -@ ${t} -s -f ${sample}.markdup.txt --reference ${ref_name} -O ${fmt} - ${sample}.${params.output_format}" :
        "samtools sort -@ ${t} -m 1G -T tmp_sort --reference ${ref_name} -O ${fmt} -o ${sample}.${params.output_format} -"
    """
    bwa mem -t ${t} -Y -R '${rg}' ${ref_name} <(cat ${r1s.join(' ')}) <(cat ${r2s.join(' ')}) \
      | ${dedup}
    samtools index -@ ${t} ${sample}.${params.output_format}
    samtools flagstat -@ ${t} ${sample}.${params.output_format} > ${sample}.flagstat.txt
    """
}

// Existing BAM/CRAM given as input: make sure it has an index, and collect alignment statistics.
process INDEX_INPUT_ALN {
    tag "${sample}"
    container "quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0"
    cpus 4
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
    samtools flagstat -@ ${task.cpus} --reference ${ref_name} ${aln} > ${sample}.flagstat.txt
    """
}

// mosdepth: depth over the target regions, and the share of target bases reaching 10x/20x/30x/50x/100x.
process COVERAGE {
    tag "${sample}"
    container "quay.io/biocontainers/mosdepth:0.3.10--h4e814b3_1"
    cpus 4
    publishDir { "${params.out_dir}/${sample}/qc" }, mode: "copy"
    input:
    tuple val(sample), path(aln), path(idx), path(bed)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.mosdepth.summary.txt"), path("${sample}.thresholds.bed.gz"), path("${sample}.regions.bed.gz"), emit: files
    script:
    """
    mosdepth -t ${task.cpus} -n --fasta ${ref_name} --by ${bed} --thresholds 10,20,30,50,100 ${sample} ${aln}
    """
}
