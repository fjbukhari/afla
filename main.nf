#!/usr/bin/env nextflow
// AFLA germline workflow: Illumina short reads (panels, exomes) -> QC -> alignment -> coverage
// -> small-variant calling -> annotation -> interactive teaching report.
// Education and research use only, not for clinical use.

include { PREPARE_REF; BWA_INDEX; PREPARE_BED; AUTO_TARGETS } from './modules/reference'
include { FASTP; ALIGN; INDEX_INPUT_ALN; COVERAGE } from './modules/reads'
include { CALL_GATK; CALL_DEEPVARIANT; NORMALISE_FILTER; PREPARE_INPUT_VCF; ANNOTATE_VEP } from './modules/variants'
include { SUMMARISE; REPORT } from './modules/report'

// "NA12877_S8_L001" -> "NA12877": drop Illumina sample-sheet number and lane, so lanes of one sample merge
def sampleFromFastq(String id) {
    return id.replaceAll(/(_S\d+)?(_L\d{3})?$/, '')
}

// Command-line values arrive as text ("false"); EPI2ME sends real true/false. Accept both.
def flag(Object x) {
    if (x instanceof Boolean) return x
    return x != null && x.toString().trim().toLowerCase() in ['true', 'yes', '1', 'on']
}

def jsonString(Object x) {
    if (x == null) return 'null'
    if (x instanceof Boolean || x instanceof Number) return x.toString()
    if (x instanceof Map) return '{' + x.collect { k, v -> jsonString(k.toString()) + ':' + jsonString(v) }.join(',') + '}'
    if (x instanceof Collection) return '[' + x.collect { v -> jsonString(v) }.join(',') + ']'
    return '"' + x.toString().replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
}

workflow {
    // ---------------------------------------------------------------- checks
    def given = [params.fastq, params.bam, params.vcf].findAll { x -> x }
    if (given.size() != 1) {
        error "Give exactly one input: a FASTQ folder, a BAM/CRAM (file or folder), or a VCF file."
    }
    def start = params.vcf ? 'vcf' : (params.bam ? 'bam' : 'fastq')
    if (start != 'vcf' && !params.ref) {
        error "A reference FASTA (ref) is needed when starting from FASTQ or BAM/CRAM."
    }
    if (flag(params.run_annotation) && !params.vep_cache) {
        error "Annotation needs the Ensembl VEP cache folder (vep_cache). Set it, or untick 'Annotate variants'."
    }
    if (!(params.caller in ['gatk', 'deepvariant'])) {
        error "caller must be 'gatk' or 'deepvariant'."
    }
    def steps = []
    def tools = [:]
    def qc = channel.empty()
    def aln = channel.empty()
    def vcf = channel.empty()
    def ref_files = channel.empty()
    def ref_name = ''
    def targets_desc = 'none'

    // ---------------------------------------------------------------- reference
    if (start != 'vcf') {
        def fa = file(params.ref, checkIfExists: true)
        ref_name = fa.name
        def fai = file("${fa}.fai")
        def dict = file("${fa.parent}/${fa.baseName}.dict")
        def core
        if (fai.exists() && dict.exists()) {
            core = channel.value([fa, fai, dict])
        } else {
            PREPARE_REF(fa)
            core = PREPARE_REF.out.fai.combine(PREPARE_REF.out.dict).map { f, d -> [fa, f, d] }
            steps << 'reference index (.fai/.dict)'
        }
        if (start == 'fastq') {
            def idx = ['amb', 'ann', 'bwt', 'pac', 'sa'].collect { e -> file("${fa}.${e}") }
            def bwa_idx
            if (idx.every { f -> f.exists() }) {
                bwa_idx = channel.value(idx)
            } else if (flag(params.build_bwa_index)) {
                bwa_idx = BWA_INDEX(fa).collect()
                steps << 'bwa index'
            } else {
                error "No bwa index found next to ${fa}. Tick 'Build bwa index' (about 1 hour, done once) or choose an indexed reference."
            }
            ref_files = core.combine(bwa_idx).collect()
        } else {
            ref_files = core.collect()
        }
    }

    // ---------------------------------------------------------------- reads -> alignment
    if (start == 'fastq') {
        def d = params.fastq
        def pairs = channel
            .fromFilePairs(["${d}/**_R{1,2}_001.f*q.gz", "${d}/**_R{1,2}.f*q.gz", "${d}/**_{1,2}.f*q.gz"], size: 2, flat: true)
            .map { id, r1, r2 -> [params.sample_name ?: sampleFromFastq(id), r1, r2] }
            .groupTuple()
            .ifEmpty { error "No paired FASTQ files (*_R1/_R2 or *_1/_2, .fastq.gz or .fq.gz) found in ${d}" }
        def reads = pairs
        if (flag(params.run_fastp)) {
            FASTP(pairs)
            reads = FASTP.out.reads
            qc = qc.mix(FASTP.out.json.map { f -> [f.name.replace('.fastp.json', ''), f] })
            steps << 'fastp (trim + read QC)'
            tools.fastp = 'staphb/fastp:1.3.3'
        }
        ALIGN(reads, ref_files, ref_name)
        aln = ALIGN.out.aln
        qc = qc.mix(ALIGN.out.flagstat.map { f -> [f.name.replace('.flagstat.txt', ''), f] })
        steps << (flag(params.mark_duplicates) ? 'bwa mem + samtools markdup' : 'bwa mem (no duplicate marking)')
        tools['bwa + samtools'] = 'biocontainers bwa 0.7.17 / samtools 1.16.1'
    } else if (start == 'bam') {
        def b = file(params.bam, checkIfExists: true)
        def ch = b.isDirectory() ? channel.fromPath("${params.bam}/*.{bam,cram}") : channel.fromPath(params.bam)
        INDEX_INPUT_ALN(ch.map { f -> [(params.sample_name && !b.isDirectory()) ? params.sample_name : f.simpleName, f] }, ref_files, ref_name)
        aln = INDEX_INPUT_ALN.out.aln
        qc = qc.mix(INDEX_INPUT_ALN.out.flagstat.map { f -> [f.name.replace('.flagstat.txt', ''), f] })
        steps << 'existing BAM/CRAM'
    }

    // ---------------------------------------------------------------- targets, coverage, calling
    if (start != 'vcf' && (flag(params.run_coverage) || flag(params.run_calling))) {
        def aln_bed
        if (params.bed) {
            def bed = PREPARE_BED(file(params.bed, checkIfExists: true), ref_files.map { fs -> fs.find { f -> f.name.endsWith('.fai') } })
            aln_bed = aln.combine(bed)
            targets_desc = "${file(params.bed).name}"
        } else {
            AUTO_TARGETS(aln, ref_files, ref_name)
            aln_bed = aln.join(AUTO_TARGETS.out)
            targets_desc = "derived from the reads (depth >= ${params.auto_targets_min_depth}x, no BED given)"
            steps << 'target regions from coverage'
        }
        if (flag(params.run_coverage)) {
            COVERAGE(aln_bed, ref_files, ref_name)
            qc = qc.mix(COVERAGE.out.files.flatMap { s, a, b, c -> [[s, a], [s, b], [s, c]] })
            steps << 'mosdepth coverage'
            tools.mosdepth = 'mosdepth 0.3.10'
        }
        if (flag(params.run_calling)) {
            def raw
            if (params.caller == 'deepvariant') {
                raw = CALL_DEEPVARIANT(aln_bed, ref_files, ref_name)
                steps << "DeepVariant ${params.deepvariant_model}${flag(params.use_gpu) ? ' (GPU)' : ''}"
                tools.deepvariant = "google/deepvariant:${params.deepvariant_version}${flag(params.use_gpu) ? '-gpu' : ''}"
            } else {
                raw = CALL_GATK(aln_bed, ref_files, ref_name)
                steps << 'GATK HaplotypeCaller'
                tools.gatk = 'broadinstitute/gatk:4.6.2.0'
            }
            NORMALISE_FILTER(raw, ref_files, ref_name)
            vcf = NORMALISE_FILTER.out.vcf
            steps << 'bcftools normalise + quality filter'
            tools.bcftools = 'staphb/bcftools:1.23.1'
        }
    }
    if (start == 'vcf') {
        def v = file(params.vcf, checkIfExists: true)
        vcf = PREPARE_INPUT_VCF(channel.of([params.sample_name ?: v.simpleName, v]))
        steps << 'existing VCF'
    }

    // ---------------------------------------------------------------- annotation
    def sources = []
    def vcf_final = vcf.map { s, v, _tbi -> [s, v] }
    if (flag(params.run_annotation)) {
        def extra = []
        def args = []
        if (params.vep_fasta) {
            def f = file(params.vep_fasta, checkIfExists: true)
            extra += [f, file("${f}.fai", checkIfExists: true)]
            args << "--hgvs --fasta ${f.name}"
        }
        def plugins = []
        if (params.revel_file) {
            def f = file(params.revel_file, checkIfExists: true)
            extra += [f, file("${f}.tbi")]
            plugins << "--plugin REVEL,file=${f.name}"
            sources << "REVEL (${f.name})"
        }
        if (params.alphamissense_file) {
            def f = file(params.alphamissense_file, checkIfExists: true)
            extra += [f, file("${f}.tbi")]
            plugins << "--plugin AlphaMissense,file=${f.name}"
            sources << "AlphaMissense (${f.name})"
        }
        if (plugins) {
            def pd = file(params.vep_plugins_dir ?: "${params.vep_cache}/Plugins", checkIfExists: true)
            extra << pd
            args << "--dir_plugins ${pd.name}" << plugins.join(' ')
        }
        if (params.clinvar_vcf) {
            def f = file(params.clinvar_vcf, checkIfExists: true)
            extra += [f, file("${f}.tbi")]
            args << "--custom file=${f.name},short_name=ClinVar,format=vcf,type=exact,coords=0,fields=CLNSIG%CLNREVSTAT%CLNDN"
            sources << "ClinVar (${f.name})"
        }
        if (!extra) {
            extra = [file("${projectDir}/assets/NO_QC")]
        }
        ANNOTATE_VEP(vcf, file(params.vep_cache, checkIfExists: true), extra, args.join(' '))
        vcf_final = ANNOTATE_VEP.out.vcf
        steps << "Ensembl VEP ${params.vep_cache_version} (offline)"
        tools.vep = 'ensemblorg/ensembl-vep:release_115.2'
    }

    // ---------------------------------------------------------------- report
    if (flag(params.run_report)) {
        def per_sample = vcf_final
            .join(qc.groupTuple(), remainder: true)
            .map { s, v, q -> [s, v ?: file("${projectDir}/assets/NO_VCF"), q ?: [file("${projectDir}/assets/NO_QC")]] }
        if (start == 'vcf' || !flag(params.run_calling)) {
            per_sample = (start == 'vcf' ? vcf_final.map { s, v -> [s, v, [file("${projectDir}/assets/NO_QC")]] }
                                         : qc.groupTuple().map { s, q -> [s, file("${projectDir}/assets/NO_VCF"), q] })
        }
        SUMMARISE(per_sample)
        def meta = [
            title: 'AFLA germline report', workflow_version: workflow.manifest.version,
            date: new Date().format('yyyy-MM-dd HH:mm'), reference: params.ref ? file(params.ref).name : 'n/a',
            steps: steps, tools: tools, annotation_sources: sources, targets: targets_desc,
            mark_duplicates: flag(params.mark_duplicates), report_max_pop_af: params.report_max_pop_af, report_min_vaf: params.report_min_vaf,
            params: params.findAll { k, _v -> !(k in ['help', 'version', 'disable_ping']) },
        ]
        REPORT(SUMMARISE.out.collect(), channel.of(jsonString(meta)).collectFile(name: 'afla_meta.json'))
    }
}
