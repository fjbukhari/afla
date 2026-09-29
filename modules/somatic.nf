// Somatic analysis: GATK Mutect2 small variants (tumour-only or tumour/normal), microsatellite instability,
// and structural variants / DNA-level fusions (Manta; also used for germline SVs).

// Splits the target regions into N chunks with similar amounts of work (bases x read depth, measured with
// samtools bedcov), so Mutect2 (mostly single-threaded) can run on several CPU cores at once.
// The heaviest regions are handed out first, each to the chunk with the least work so far.
process SPLIT_TARGETS {
    tag "${sample}"
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
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
    cpus { params.mutect2_shards.toString() == '1' ? Math.min((params.threads ?: params.max_cpus) as int, params.max_cpus as int) : Math.min(2, params.max_cpus as int) }
    memory { [MemoryUnit.of(params.mutect2_shards.toString() == '1' ? '20 GB' : '8 GB'), MemoryUnit.of(params.max_memory.toString())].min() }
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
    def paired = !normal_aln.name.startsWith("NO_NORMAL")
    def normal = paired ? "-I ${normal_aln} -normal \$(cat normal_name.txt)" : ""
    """
    ${paired ? "gatk GetSampleName -R ${ref_name} -I ${normal_aln} -O normal_name.txt" : ""}
    gatk --java-options "-Xmx${Math.max(1, (int) (task.memory.toGiga() * 0.8))}g" Mutect2 -R ${ref_name} -I ${aln} ${normal} -L ${chunk} \
      --max-reads-per-alignment-start 0 --native-pair-hmm-threads ${task.cpus} \
      ${resource_args} -O ${sample}.${chunk.baseName}.vcf.gz
    """
}

// Joins the chunks and runs FilterMutectCalls (labels artefacts and likely germline calls).
process MERGE_FILTER_MUTECT2 {
    tag "${sample}"
    label "medium"
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
    def x = "-Xmx${Math.max(1, (int) (task.memory.toGiga() * 0.8))}g"
    """
    gatk --java-options "${x}" MergeVcfs ${vcf_list} -O ${sample}.unfiltered.vcf.gz
    gatk --java-options "${x}" MergeMutectStats ${stat_list} -O ${sample}.unfiltered.vcf.gz.stats
    gatk --java-options "${x}" FilterMutectCalls -R ${ref_name} -V ${sample}.unfiltered.vcf.gz \
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
    val min_dp
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
          -e 'FMT/AF<${params.min_vaf} || FMT/AD[0:1]<${params.min_alt_reads} || FMT/DP<${min_dp}' \
          -Oz -o ${sample}.vcf.gz
    bcftools index -t ${sample}.vcf.gz
    """
}

// Microsatellite instability (msisensor-pro): tumour vs normal when a normal is given; otherwise tumour-only
// with a baseline built from normals (if provided) or the default instability threshold.
process MSI {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/msisensor-pro:1.3.0--hd979922_1"
    publishDir { "${params.out_dir}/${sample}/msi" }, mode: "copy"
    input:
    tuple val(sample), path(aln), path(idx), path(bed), path(normal_aln), path(normal_idx)
    path ms_list
    path baseline
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.msi.txt"), emit: result
    script:
    def paired = !normal_aln.name.startsWith("NO_NORMAL")
    def has_baseline = !baseline.name.startsWith("NO_RESOURCE")
    """
    # microsatellites inside the target regions only
    # (both files are sorted by position, so one pass with a moving pointer per chromosome is enough)
    sort -k1,1 -k2,2n ${bed} > t.bed
    awk 'NR==FNR { k=++n[\$1]; S[\$1,k]=\$2; E[\$1,k]=\$3; next }
        FNR==1 { print; next }
        { if (\$1 != cur) { cur=\$1; i=1 } while (i <= n[\$1] && E[\$1,i] < \$2) i++
          if (i <= n[\$1] && S[\$1,i] < \$2) print }' \
        t.bed ${has_baseline ? baseline : ms_list} > targets.list
    if [ \$(wc -l < targets.list) -lt 2 ]; then
      printf 'Total_Number_of_Sites\\tNumber_of_Unstable_Sites\\t%%\\n0\\t0\\t0\\n' > ${sample}.msi.txt; exit 0
    fi
    ${paired ?
      "msisensor-pro msi -d targets.list -n ${normal_aln} -t ${aln} -g ${ref_name} -b ${task.cpus} -o ${sample}.msi" :
      "msisensor-pro pro -d targets.list -t ${aln} -g ${ref_name} -b ${task.cpus} -c 20 -o ${sample}.msi"}
    mv ${sample}.msi ${sample}.msi.txt
    """
}

// Manta: structural variants (deletions, duplications, inversions, translocations = DNA-level fusions).
// germline: diploid SVs of each sample; somatic: tumour-only or tumour/normal. --exome for panels/exomes.
process MANTA {
    tag "${sample}"
    label "big"
    container "quay.io/biocontainers/manta:1.6.0--h9ee0642_2"
    publishDir { "${params.out_dir}/${sample}/sv" }, mode: "copy"
    input:
    tuple val(sample), path(aln), path(idx), path(bed), path(normal_aln), path(normal_idx)
    path ref_files
    val ref_name
    val somatic
    output:
    tuple val(sample), path("${sample}.sv.vcf.gz"), path("${sample}.sv.vcf.gz.tbi"), emit: vcf
    script:
    def paired = !normal_aln.name.startsWith("NO_NORMAL")
    def bams = somatic ? (paired ? "--normalBam ${normal_aln} --tumorBam ${aln}" : "--tumorBam ${aln}") : "--bam ${aln}"
    def result = somatic ? (paired ? "somaticSV" : "tumorSV") : "diploidSV"
    """
    sort -k1,1 -k2,2n ${bed} | bgzip > regions.bed.gz && tabix -p bed regions.bed.gz
    configManta.py ${bams} --referenceFasta ${ref_name} --exome --callRegions regions.bed.gz --runDir manta
    manta/runWorkflow.py -j ${task.cpus} -g ${task.memory.toGiga()}
    cp manta/results/variants/${result}.vcf.gz ${sample}.sv.vcf.gz
    cp manta/results/variants/${result}.vcf.gz.tbi ${sample}.sv.vcf.gz.tbi
    """
}
