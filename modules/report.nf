// Per case (sample, family or tumour): QC, variants with ACMG/AMP evidence, CNV, SV, MSI, ROH as JSON;
// then one interactive HTML report for all cases.

process SUMMARISE {
    tag "${unit}"
    label "medium"
    container "quay.io/biocontainers/python:3.12"
    input:
    tuple val(unit), path(vcf), path(qc_files, stageAs: "qc/*"), path(extra_files, stageAs: "extra/*")
    path knowledge, stageAs: "knowledge/*"
    val knowledge_args
    path case_json
    path targets, stageAs: "targets/*"
    output:
    path "${unit}.summary.json"
    script:
    def v = vcf.name.startsWith("NO_VCF") ? "" : "--vcf ${vcf}"
    def t = targets instanceof List ? targets[0] : targets
    def tg = t.name.startsWith("NO_RESOURCE") ? "" : "--targets ${t}"
    def kargs = knowledge_args.split(' ').collect { a -> a.startsWith('--') || !a ? a : "knowledge/${a}" }.join(' ')
    """
    afla_report.py summarise --sample ${unit} ${v} --qc qc/* --extra extra/* --case ${case_json} ${tg} ${kargs} \
      --out ${unit}.summary.json
    """
}

process REPORT {
    container "quay.io/biocontainers/python:3.12"
    publishDir "${params.out_dir}", mode: "copy"
    input:
    path summaries
    path meta
    val report_name
    output:
    path "${report_name}"
    script:
    """
    afla_report.py html --summaries ${summaries} --meta ${meta} --out ${report_name}
    """
}
