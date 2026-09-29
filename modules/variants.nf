// Germline variant calling (single samples and families), normalisation/quality filter, ROH and annotation.

// GATK HaplotypeCaller (CPU): the widely used standard germline caller. gvcf=true for family joint calling.
process CALL_GATK {
    tag "${sample}"
    label "big"
    container "broadinstitute/gatk:4.6.2.0"
    input:
    tuple val(sample), path(aln), path(idx), path(bed)
    path ref_files
    val ref_name
    val gvcf
    output:
    tuple val(sample), path("${sample}.${gvcf ? 'g' : 'raw'}.vcf.gz"), path("${sample}.${gvcf ? 'g' : 'raw'}.vcf.gz.tbi")
    script:
    def erc = gvcf ? "-ERC GVCF" : ""
    """
    gatk --java-options "-Xmx${(int) (task.memory.toGiga() * 0.8)}g" HaplotypeCaller -R ${ref_name} -I ${aln} -L ${bed} \
      --native-pair-hmm-threads ${task.cpus} ${erc} -O ${sample}.${gvcf ? 'g' : 'raw'}.vcf.gz
    """
}

// DeepVariant (Google): deep-learning caller; uses the GPU image when use_gpu is on.
process CALL_DEEPVARIANT {
    tag "${sample}"
    label "big"
    label "gpu"
    container "google/deepvariant:${params.deepvariant_version}${(params.use_gpu.toString() == 'true') ? '-gpu' : ''}"
    input:
    tuple val(sample), path(aln), path(idx), path(bed)
    path ref_files
    val ref_name
    val gvcf
    output:
    tuple val(sample), path("${sample}.${gvcf ? 'g' : 'raw'}.vcf.gz"), path("${sample}.${gvcf ? 'g' : 'raw'}.vcf.gz.tbi")
    script:
    def g = gvcf ? "--output_gvcf=${sample}.g.vcf.gz" : ""
    def out = gvcf ? "dv_calls.vcf.gz" : "${sample}.raw.vcf.gz"
    """
    run_deepvariant --model_type=${params.deepvariant_model} --ref=${ref_name} --reads=${aln} \
      --regions=${bed} --output_vcf=${out} ${g} --num_shards=${task.cpus} \
      --intermediate_results_dir=dv_tmp
    rm -rf dv_tmp
    """
}

// Families (trios): joint genotyping of the members' gVCFs, so every member has a genotype at every site.
process JOINT_GATK {
    tag "${family}"
    label "medium"
    container "broadinstitute/gatk:4.6.2.0"
    input:
    tuple val(family), path(gvcfs), path(tbis)
    path ref_files
    val ref_name
    output:
    tuple val(family), path("${family}.joint.vcf.gz")
    script:
    def v = (gvcfs instanceof List ? gvcfs : [gvcfs]).collect { g -> "-V ${g}" }.join(' ')
    def x = "-Xmx${(int) (task.memory.toGiga() * 0.8)}g"
    """
    gatk --java-options "${x}" CombineGVCFs -R ${ref_name} ${v} -O combined.g.vcf.gz
    gatk --java-options "${x}" GenotypeGVCFs -R ${ref_name} -V combined.g.vcf.gz -O ${family}.joint.vcf.gz
    """
}

process JOINT_GLNEXUS {
    tag "${family}"
    label "medium"
    container "quay.io/biocontainers/glnexus:1.4.1--h17e8430_5"
    input:
    tuple val(family), path(gvcfs), path(tbis)
    path ref_files
    val ref_name
    output:
    tuple val(family), path("${family}.joint.bcf")
    script:
    """
    glnexus_cli --config DeepVariant${params.deepvariant_model == 'WGS' ? 'WGS' : 'WES'} --threads ${task.cpus} \
      --mem-gbytes ${task.memory.toGiga()} ${gvcfs} > ${family}.joint.bcf
    """
}

// Splits multi-allelic sites, left-aligns indels, labels low-quality calls (they are kept, marked LowQual).
// Single samples: QUAL, depth and GQ. Families: QUAL only here; per-member depth/GQ are checked in the report.
process NORMALISE_FILTER {
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
    """
    N=\$(bcftools query -l ${vcf} | wc -l)
    if [ "\$N" -gt 1 ]; then
      EXPR='QUAL<${params.min_qual}'; VAFEXPR='QUAL<0'
    else
      EXPR='QUAL<${params.min_qual} || FMT/DP<${min_dp} || FMT/GQ<${params.min_gq}'
      # heterozygous calls in few reads: typical PCR/homopolymer artefacts (true germline hets are near 50%)
      VAFEXPR='GT="het" && FMT/AD[0:1] / (FMT/AD[0:0] + FMT/AD[0:1]) < ${params.min_het_vaf}'
    fi
    bcftools norm -m -both -f ${ref_name} --check-ref s ${vcf} -Ou \
      | bcftools view -e 'ALT=="*"' -Ou \
      | bcftools filter -m + -s LowQual -e "\$EXPR" -Ou \
      | bcftools filter -m + -s LowVAF -e "\$VAFEXPR" -Oz -o ${sample}.vcf.gz
    bcftools index -t ${sample}.vcf.gz
    """
}

// VCF given as input: sort, split multi-allelic sites, compress and index, so it enters the same path as called variants.
process PREPARE_INPUT_VCF {
    tag "${sample}"
    container "staphb/bcftools:1.23.1"
    input:
    tuple val(sample), path(vcf)
    output:
    tuple val(sample), path("${sample}.input.vcf.gz"), path("${sample}.input.vcf.gz.tbi"), emit: vcf
    script:
    """
    bcftools sort ${vcf} -Ou | bcftools norm -m -both -Oz -o ${sample}.input.vcf.gz
    bcftools index -t ${sample}.input.vcf.gz
    """
}

// Runs of homozygosity (long stretches where both copies are identical): common in consanguineous families,
// and where a recessive disease gene is likely to lie. Exomes give approximate boundaries.
process ROH {
    tag "${sample}"
    container "staphb/bcftools:1.23.1"
    publishDir { "${params.out_dir}/${sample}/variants" }, mode: "copy"
    input:
    tuple val(sample), path(vcf), path(tbi)
    output:
    tuple val(sample), path("${sample}.roh.txt")
    script:
    """
    : > ${sample}.roh.txt
    for m in \$(bcftools query -l ${vcf}); do
      bcftools roh --AF-dflt 0.4 -G 30 -s "\$m" -O r ${vcf} 2>/dev/null | awk '\$1=="RG"' >> ${sample}.roh.txt || true
    done
    """
}

// Ensembl VEP, offline. With the cache (standard): the cache names chromosomes 1,2..MT, so a "chr" VCF is renamed
// for VEP and renamed back afterwards. With a GTF instead of the cache, names are kept as they are.
process ANNOTATE_VEP {
    tag "${sample}${kind ? ' ' + kind : ''}"
    label "big"
    container "ensemblorg/ensembl-vep:release_115.2"
    publishDir { "${params.out_dir}/${sample}/variants" }, mode: "copy"
    input:
    tuple val(sample), path(vcf), path(tbi)
    path vep_cache
    path extra_files
    val extra_args
    val use_cache
    val kind
    output:
    tuple val(sample), path("${sample}${kind ? '.' + kind : ''}.annotated.vcf.gz"), emit: vcf
    path "${sample}${kind ? '.' + kind : ''}.vep_summary.html", optional: true
    script:
    def out = "${sample}${kind ? '.' + kind : ''}"
    def source = use_cache ?
        "--offline --cache --dir_cache ${vep_cache} --cache_version ${params.vep_cache_version} --af --af_gnomade --af_gnomadg --max_af --check_existing --pubmed --gene_phenotype --sift b --polyphen b" :
        ""
    def rename = use_cache ? 1 : 0
    """
    # rename chr1 -> 1 (and chrM -> MT) only with the Ensembl cache and only if this VCF uses "chr" names
    CHR=\$(tabix -H ${vcf} | awk -v r=${rename} '/^##contig=<ID=chr/ {f=1} END {print (r && f) ? 1 : 0}')
    zcat ${vcf} | awk -v chr=\$CHR 'BEGIN{OFS="\\t"}
        !chr { print; next }
        /^##contig=<ID=chr/ { sub(/ID=chrM,/,"ID=MT,"); sub(/ID=chr/,"ID="); print; next }
        /^#/ { print; next }
        { if (\$1=="chrM") \$1="MT"; else sub(/^chr/,"",\$1); print }' > for_vep.vcf
    vep --input_file for_vep.vcf --format vcf --output_file vep_out.vcf --vcf --force_overwrite \
      --stats_file ${out}.vep_summary.html \
      ${source} --assembly GRCh38 --species homo_sapiens --fork ${task.cpus} --buffer_size 5000 \
      --pick --pick_order mane_select,canonical,appris,tsl,biotype,ccds,rank,length \
      --mane --symbol --canonical --biotype --numbers --variant_class \
      --max_sv_size 100000000 \
      ${extra_args}
    # VEP writes no file when there are no variants
    [ -e vep_out.vcf ] || cp for_vep.vcf vep_out.vcf
    awk -v chr=\$CHR 'BEGIN{OFS="\\t"}
        !chr { print; next }
        /^##contig=<ID=MT,/ { sub(/ID=MT,/,"ID=chrM,"); print; next }
        /^##contig=<ID=/ { sub(/ID=/,"ID=chr"); print; next }
        /^#/ { print; next }
        { if (\$1=="MT") \$1="chrM"; else \$1="chr" \$1; print }' vep_out.vcf | bgzip > ${out}.annotated.vcf.gz
    """
}
