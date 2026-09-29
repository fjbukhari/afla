// Somatic small-variant calling (GATK Mutect2): tumour-only, or tumour with a matched normal.

// Splits the target regions into N chunks with similar amounts of work (bases x read depth, measured with
// samtools bedcov), so Mutect2 (mostly single-threaded) can run on several CPU cores at once.
// The heaviest regions are handed out first, each to the chunk with the least work so far.
process SPLIT_TARGETS {
    tag "${sample}"
    container "quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0"
    input:
    tuple val(sample), path(aln), path(idx), path(bed), path(normal_aln), path(normal_idx)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path(aln), path(idx), path("chunk_*.bed"), path(normal_aln), path(normal_idx)
    script:
    """
    if [ ${params.mutect2_shards} -le 1 ]; then cp ${bed} chunk_01.bed; exit 0; fi
    samtools bedcov --reference ${ref_name} ${bed} ${aln} \
      | awk -v OFS='\t' '{ print \$1, \$2, \$3, \$4 + (\$3 - \$2) }' \
      | sort -k4,4nr \
      | awk -v n=${params.mutect2_shards} '
          { best = 1; for (k = 2; k <= n; k++) if (load[k] < load[best]) best = k
            load[best] += \$4; print \$1 "\t" \$2 "\t" \$3 > sprintf("unsorted_%02d.bed", best) }'
    for f in unsorted_*.bed; do sort -k1,1 -k2,2n "\$f" > "chunk_\${f#unsorted_}"; done
    """
}

// Mutect2 on one chunk of the targets. Down-sampling is switched off: panels are deep and amplicon reads
// all start at the same positions, which Mutect2 would otherwise throw away.
process CALL_MUTECT2 {
    tag "${sample} ${chunk.baseName}"
    // one job: all threads and plenty of memory; several parallel chunks: 2 threads and 8 GB each
    cpus { params.mutect2_shards.toString() == '1' ? params.threads : 2 }
    memory { params.mutect2_shards.toString() == '1' ? '20 GB' : '8 GB' }
    container "broadinstitute/gatk:4.6.2.0"
    input:
    tuple val(sample), path(aln), path(idx), path(chunk), path(normal_aln), path(normal_idx)
    path ref_files
    val ref_name
    path resources
    val resource_args
    output:
    tuple val(sample), path("${sample}.${chunk.baseName}.vcf.gz"), path("${sample}.${chunk.baseName}.vcf.gz.stats"), emit: vcf
    script:
    def normal = normal_aln.name.startsWith("NO_NORMAL") ? "" : "-I ${normal_aln} -normal ${params.normal_sample}"
    """
    gatk --java-options "-Xmx${task.memory.toGiga() - 2}g" Mutect2 -R ${ref_name} -I ${aln} ${normal} -L ${chunk} \
      --max-reads-per-alignment-start 0 --native-pair-hmm-threads ${task.cpus} \
      ${resource_args} -O ${sample}.${chunk.baseName}.vcf.gz
    """
}

// Joins the chunks and runs FilterMutectCalls (labels artefacts and likely germline calls).
process MERGE_FILTER_MUTECT2 {
    tag "${sample}"
    cpus 2
    memory "8 GB"
    container "broadinstitute/gatk:4.6.2.0"
    publishDir { "${params.out_dir}/${sample}/variants" }, mode: "copy", pattern: "*.mutect2.vcf.gz*"
    input:
    tuple val(sample), path(vcfs), path(stats)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.mutect2.vcf.gz"), emit: vcf
    path "${sample}.mutect2.vcf.gz.tbi"
    script:
    def vcf_list = (vcfs instanceof List ? vcfs : [vcfs]).collect { v -> "-I ${v}" }.join(' ')
    def stat_list = (stats instanceof List ? stats : [stats]).collect { v -> "--stats ${v}" }.join(' ')
    """
    gatk --java-options "-Xmx4g" MergeVcfs ${vcf_list} -O ${sample}.unfiltered.vcf.gz
    gatk --java-options "-Xmx4g" MergeMutectStats ${stat_list} -O ${sample}.unfiltered.vcf.gz.stats
    gatk --java-options "-Xmx6g" FilterMutectCalls -R ${ref_name} -V ${sample}.unfiltered.vcf.gz \
      -O ${sample}.mutect2.vcf.gz
    """
}

// Keeps the tumour sample, splits multi-allelic sites, left-aligns indels, and labels weak calls
// (kept in the file, labelled LowSupport): VAF, supporting reads and depth below the chosen minimums.
process SOMATIC_FILTER {
    tag "${sample}"
    container "staphb/bcftools:1.23.1"
    publishDir { "${params.out_dir}/${sample}/variants" }, mode: "copy"
    input:
    tuple val(sample), path(vcf)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.vcf.gz"), path("${sample}.vcf.gz.tbi"), emit: vcf
    script:
    // amplicon reads all come from one strand and start at the primers, so Mutect2's strand-bias and
    // read-position filters also hit real variants: keep those labels out in amplicon mode
    def amp = (params.amplicon.toString() == 'true') ? "bcftools annotate -x FILTER/strand_bias,FILTER/position -Ou" : "cat"
    """
    bcftools index -t ${vcf}
    bcftools view -s ${sample} ${vcf} -Ou \
      | ${amp} \
      | bcftools norm -m -both -f ${ref_name} --check-ref s -Ou \
      | bcftools filter -m + -s LowSupport \
          -e 'FMT/AF<${params.min_vaf} || FMT/AD[0:1]<${params.min_alt_reads} || FMT/DP<${params.min_dp}' \
          -Oz -o ${sample}.vcf.gz
    bcftools index -t ${sample}.vcf.gz
    """
}
