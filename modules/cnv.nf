// Copy-number variants from panel/exome read depth (CNVkit, target regions only).
// Depth in each target is compared with a reference made from other samples sequenced with the same kit:
//  - a CNVkit reference given by the user (best: 10+ normal samples of the same kit), or
//  - the other samples of this run (leave-one-out; needs 3+ samples), or
//  - a flat reference (no normals): only large, strong changes are believable.

// Split targets into ~bins and add gene names (refFlat), done once per run.
process CNV_TARGETS {
    container "quay.io/biocontainers/cnvkit:0.9.14--pyhdfd78af_0"
    input:
    path bed
    path annotation
    output:
    path "cnv_targets.bed"
    script:
    def ann = annotation.name.startsWith("NO_RESOURCE") ? "" : "--annotate ${annotation}"
    """
    cnvkit.py target ${bed} ${ann} --split --avg-size 267 -o cnv_targets.bed
    """
}

process CNV_COVERAGE {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/cnvkit:0.9.14--pyhdfd78af_0"
    input:
    tuple val(sample), path(aln), path(idx)
    path targets
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.targetcoverage.cnn")
    script:
    """
    cnvkit.py coverage -p ${task.cpus} -f ${ref_name} ${aln} ${targets} -o ${sample}.targetcoverage.cnn
    """
}

// Reference for one sample: the given .cnn, or the other samples' coverage, or flat.
process CNV_REFERENCE {
    tag "${sample}"
    container "quay.io/biocontainers/cnvkit:0.9.14--pyhdfd78af_0"
    input:
    tuple val(sample), path(own), path(others), val(kind)
    path targets
    path user_ref
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.reference.cnn"), val(kind)
    script:
    if (kind == 'user')
    """
    cp ${user_ref} ${sample}.reference.cnn
    """
    else if (kind == 'pooled')
    """
    cnvkit.py reference ${others} -f ${ref_name} -o ${sample}.reference.cnn
    """
    else
    """
    cnvkit.py reference -t ${targets} -f ${ref_name} -o ${sample}.reference.cnn
    """
}

process CNV_CALL {
    tag "${sample}"
    label "medium"
    container "quay.io/biocontainers/cnvkit:0.9.14--pyhdfd78af_0"
    publishDir { "${params.out_dir}/${sample}/cnv" }, mode: "copy"
    input:
    tuple val(sample), path(cov), path(reference), val(kind)
    val somatic
    output:
    tuple val(sample), path("${sample}.cnr"), path("${sample}.call.cns"), path("${sample}.genemetrics.tsv"), path("${sample}.cnv_scatter.png"), path("${sample}.cnv_info.txt"), emit: files
    script:
    // germline: whole copies (0,1,2,3,4...); somatic: tumour purity unknown, so thresholds on log2 ratio
    def call = somatic ? "--method threshold --thresholds=-1.1,-0.25,0.2,0.7" : "--method threshold --thresholds=-1.1,-0.4,0.3,0.7"
    """
    printf 'chromosome\\tstart\\tend\\tgene\\tlog2\\n' > empty.antitargetcoverage.cnn
    cnvkit.py fix ${cov} empty.antitargetcoverage.cnn ${reference} --no-edge -o ${sample}.cnr
    cnvkit.py segment ${sample}.cnr -m cbs -p ${task.cpus} -o ${sample}.cns
    cnvkit.py call ${sample}.cns ${call} -o ${sample}.call.cns
    cnvkit.py genemetrics ${sample}.cnr -s ${sample}.cns -t 0.2 -m 3 -o ${sample}.genemetrics.tsv || printf 'gene\\n' > ${sample}.genemetrics.tsv
    cnvkit.py scatter ${sample}.cnr -s ${sample}.call.cns -o ${sample}.cnv_scatter.png --title "${sample} (reference: ${kind})"
    echo "reference=${kind}" > ${sample}.cnv_info.txt
    """
}
