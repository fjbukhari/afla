// Per-sample summary (QC + variants as JSON), then one interactive HTML report for all samples.

process SUMMARISE {
    tag "${sample}"
    container "quay.io/biocontainers/python:3.12"
    input:
    tuple val(sample), path(vcf), path(qc_files)
    output:
    path "${sample}.summary.json"
    script:
    def v = vcf.name.startsWith("NO_VCF") ? "" : "--vcf ${vcf}"
    """
    afla_report.py summarise --sample ${sample} ${v} --qc ${qc_files} --out ${sample}.summary.json
    """
}

process REPORT {
    container "quay.io/biocontainers/python:3.12"
    publishDir "${params.out_dir}", mode: "copy"
    input:
    path summaries
    path meta
    output:
    path "${params.report_name}"
    script:
    """
    afla_report.py html --summaries ${summaries} --meta ${meta} --out ${params.report_name}
    """
}
