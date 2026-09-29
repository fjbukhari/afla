// Reference genome, target regions, primers and microsatellite list.

// Makes the .fai (position index) and .dict (chromosome list) when they are not next to the FASTA.
process PREPARE_REF {
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
    input:
    path ref
    output:
    path "${ref}.fai", emit: fai
    path "*.dict", emit: dict
    script:
    """
    samtools faidx ${ref}
    samtools dict ${ref} -o ${ref.baseName}.dict
    """
}

// One-time bwa index of the reference (about 1 hour for the human genome).
process BWA_INDEX {
    label "medium"
    container "quay.io/biocontainers/bwa:0.7.19--h577a1d6_1"
    publishDir "${params.out_dir}/reference", mode: "copy"
    input:
    path ref
    output:
    path "${ref}.{amb,ann,bwt,pac,sa}"
    script:
    """
    bwa index ${ref}
    """
}

// Cleans a user BED (headers, chr naming), pads each region and merges overlaps.
process PREPARE_BED {
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
    publishDir "${params.out_dir}/targets", mode: "copy"
    input:
    path bed
    path fai
    output:
    path "targets.padded.bed", emit: padded
    path "targets.clean.bed", emit: clean
    script:
    """
    pad_merge_bed.sh ${bed} ${fai} ${params.bed_padding} > targets.padded.bed
    pad_merge_bed.sh ${bed} ${fai} 0 > targets.clean.bed
    """
}

// Without a BED file: use the regions the reads actually cover (at least N reads deep).
process AUTO_TARGETS {
    tag "${sample}"
    container "quay.io/biocontainers/samtools:1.21--h96c455f_1"
    publishDir "${params.out_dir}/targets", mode: "copy"
    input:
    tuple val(sample), path(aln), path(idx)
    path ref_files
    val ref_name
    output:
    tuple val(sample), path("${sample}.auto_targets.bed")
    script:
    """
    samtools depth --reference ${ref_name} -Q 20 -q 20 ${aln} \
      | awk -v OFS='\\t' -v min=${params.auto_targets_min_depth} '
          \$3>=min { if(\$1==c && \$2==e+1){e=\$2} else { if(c!="") print c,s-1,e; c=\$1; s=\$2; e=\$2 } }
          END { if(c!="") print c,s-1,e }' > covered.bed
    pad_merge_bed.sh covered.bed ${ref_name}.fai ${params.bed_padding} > ${sample}.auto_targets.bed
    """
}

// Primer positions for amplicon panels: given directly (primer BED), or worked out as
// "whole amplicon minus insert" from an amplicon BED plus the insert/target BED.
process PREPARE_PRIMERS {
    container "quay.io/biocontainers/bedtools:2.31.1--h13024bc_3"
    publishDir "${params.out_dir}/targets", mode: "copy"
    input:
    path primer_or_amplicon_bed
    path insert_bed
    path fai
    val derive
    output:
    path "primers.bed"
    script:
    if (derive)
    """
    grep -vE '^(#|track|browser)' ${primer_or_amplicon_bed} | cut -f1-3 | sort -k1,1 -k2,2n > amplicons.bed
    grep -vE '^(#|track|browser)' ${insert_bed} | cut -f1-3 | sort -k1,1 -k2,2n > inserts.bed
    bedtools subtract -a amplicons.bed -b inserts.bed | awk -v OFS='\\t' '\$3>\$2 {print \$1,\$2,\$3,"primer_"NR}' > raw.bed
    match_chr_names.sh raw.bed ${fai} > primers.bed
    [ -s primers.bed ] || { echo "No primer regions found: amplicons and inserts do not overlap as expected." >&2; exit 1; }
    """
    else
    """
    grep -vE '^(#|track|browser)' ${primer_or_amplicon_bed} | awk 'NF>=3' > raw.bed
    match_chr_names.sh raw.bed ${fai} > primers.bed
    [ -s primers.bed ] || { echo "The primer BED has no usable lines for this reference." >&2; exit 1; }
    """
}

// Microsatellite list for MSI analysis, made once from the reference and restricted to the target regions.
process MSI_SCAN {
    label "medium"
    container "quay.io/biocontainers/msisensor-pro:1.3.0--hd979922_1"
    storeDir { params.resources_dir ? "${params.resources_dir}/msi" : "${params.out_dir}/reference" }
    input:
    path ref_files
    val ref_name
    output:
    path "${ref_name}.microsatellites.list"
    script:
    """
    msisensor-pro scan -d ${ref_name} -o ${ref_name}.microsatellites.list
    """
}
