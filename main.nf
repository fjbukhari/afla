#!/usr/bin/env nextflow
// AFLA workflow: short reads (Illumina/DNBSEQ panels, exomes) -> QC -> alignment (optional UMI consensus,
// primer clipping) -> coverage -> small variants (germline: GATK/DeepVariant, families jointly; somatic: Mutect2)
// -> CNV (CNVkit), SV/fusions (Manta), MSI (msisensor-pro), ROH -> annotation (VEP) -> interactive teaching report
// with ACMG/AMP evidence suggestions. Education and research use only, not for clinical use.

include { PREPARE_REF; BWA_INDEX; PREPARE_BED; AUTO_TARGETS; PREPARE_PRIMERS; MSI_SCAN } from './modules/reference'
include { FASTP; ALIGN; PRIMER_CLIP; INDEX_INPUT_ALN; COVERAGE; UMI_FASTQ_TO_BAM; BWA_UBAM as BWA_UBAM_RAW;
          BWA_UBAM as BWA_UBAM_CONS; UMI_CONSENSUS; UMI_FINALISE; SORT_INDEX } from './modules/reads'
include { CALL_GATK; CALL_GATK as CALL_GATK_FAMILY; CALL_DEEPVARIANT; CALL_DEEPVARIANT as CALL_DEEPVARIANT_FAMILY;
          JOINT_GATK; JOINT_GLNEXUS; NORMALISE_FILTER; PREPARE_INPUT_VCF; ROH;
          ANNOTATE_VEP; ANNOTATE_VEP as ANNOTATE_VEP_SV } from './modules/variants'
include { SPLIT_TARGETS; CALL_MUTECT2; MERGE_FILTER_MUTECT2; SOMATIC_FILTER; MSI; MANTA } from './modules/somatic'
include { CNV_TARGETS; CNV_COVERAGE; CNV_REFERENCE; CNV_CALL } from './modules/cnv'
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

// value, or a default when empty (0 and false are real values)
def orDefault(Object x, Object dflt) {
    return (x == null || x.toString().trim() == '' || x.toString() == 'null') ? dflt : x
}

// File pickers make it easy to choose the index (.fai/.tbi/.bai/.crai) instead of the file itself:
// accept that and use the main file next to it.
def mainFile(String name, Object p) {
    if (!p) return null
    def s = p.toString()
    def fixed = s.replaceAll(/\.(fai|tbi|csi|bai|crai|gzi)$/, '')
    if (fixed != s) {
        log.warn "${name}: '${s}' is an index file; using '${fixed}' instead."
    }
    return file(fixed, checkIfExists: true)
}

// A resource: the form value if given, otherwise the first match inside the resources folder
// (layout made by scripts/afla-setup.sh; older layouts such as afla-data/annotation/... are also recognised).
def resource(Object given, List<String> patterns, boolean dir = false) {
    if (given) return given.toString()
    if (!params.resources_dir) return null
    def root = params.resources_dir.toString().replaceAll(/\/+$/, '')
    return patterns.findResult { pat ->
        def hits = file("${root}/${pat}", type: dir ? 'dir' : 'file')
        def found = (hits instanceof List ? hits : [hits]).findAll { f -> f.exists() && !f.name.endsWith('.fai') }
        found ? found.sort { f -> f.toString() }[0].toString() : null
    }
}

// sample-sheet helpers
def familyOf(Map info, String s) {
    return info[s]?.family ?: ''
}

def roleOf(Map info, String s) {
    return info[s]?.role ?: ''
}

// germline family members are analysed together under the family name; everything else per sample
def unitOf(Map info, Map families, boolean somatic, String s) {
    def fam = familyOf(info, s)
    return (!somatic && fam && families[fam]) ? fam : s
}

def isNormal(Map info, boolean somatic, String s) {
    return somatic && (roleOf(info, s) == 'normal' || s == params.normal_sample)
}

// the normal sample of the same patient (sample sheet: role 'normal', same 'family')
def normalOf(Map info, String s) {
    def fam = familyOf(info, s)
    return fam ? info.find { _n, m -> m.role == 'normal' && m.family == fam }?.key : null
}

// Error text when no FASTQ pairs are found: say what IS in the chosen folder, to spot a wrong pick.
def fastqHelp(Object d) {
    def names = file(d.toString()).listFiles()?.collect { f -> f.name } ?: []
    def hint = ''
    if (names.any { n -> n ==~ /.*\.(fa|fasta|fna)(\.gz)?$/ }) {
        hint = ' This looks like the REFERENCE folder: choose the folder with your sequencing reads in "FASTQ folder", and the .fa file in "Reference genome".'
    } else if (names.any { n -> n ==~ /.*\.(bam|cram|vcf|vcf\.gz)$/ }) {
        hint = ' This folder has BAM/CRAM or VCF files: use the "BAM / CRAM" or "VCF file" input instead.'
    }
    def shown = names.take(8).join(', ') + (names.size() > 8 ? ', ...' : '')
    return "No paired FASTQ files (*_R1/_R2 or *_1/_2; .fastq, .fq, .fastq.gz or .fq.gz) found in ${d}.${hint} Files there: ${shown ?: 'none'}"
}

// Sample sheet (CSV: sample,role,sex,family,hpo) or PED file -> [sample: [role, sex, family, hpo, father, mother]]
def readSamples(Object sheet, Object ped) {
    def info = [:]
    if (sheet) {
        def lines = file(sheet.toString(), checkIfExists: true).readLines().findAll { l -> l.trim() && !l.startsWith('#') }
        def head = lines[0].split(',', -1)*.trim()*.toLowerCase()
        if (!('sample' in head)) error "Sample sheet ${sheet}: the first line must be a header with at least a 'sample' column (sample,role,sex,family,hpo)."
        lines.drop(1).each { l ->
            def f = l.split(',', -1)*.trim()
            def row = [head, f].transpose().collectEntries { k, v -> [k, v] }
            info[row.sample] = [role: (row.role ?: '').toLowerCase(), sex: (row.sex ?: '').toLowerCase(),
                                family: row.family ?: '', hpo: row.hpo ?: '', father: row.father ?: '', mother: row.mother ?: '']
        }
    }
    if (ped) {
        file(ped.toString(), checkIfExists: true).readLines().findAll { l -> l.trim() && !l.startsWith('#') }.each { l ->
            def f = l.trim().split(/\s+/)
            if (f.size() < 6) return
            def cur = info[f[1]] ?: [role: '', sex: '', family: '', hpo: '', father: '', mother: '']
            cur.family = cur.family ?: f[0]
            cur.father = f[2] == '0' ? '' : f[2]
            cur.mother = f[3] == '0' ? '' : f[3]
            cur.sex = cur.sex ?: (f[4] == '1' ? 'male' : f[4] == '2' ? 'female' : '')
            if (!cur.role) cur.role = f[5] == '2' ? 'affected' : 'unaffected'
            info[f[1]] = cur
        }
        // parents named in the PED get their role
        info.each { _s, m -> if (m.father && info[m.father] && info[m.father].role in ['', 'unaffected']) info[m.father].role = 'father'
                            if (m.mother && info[m.mother] && info[m.mother].role in ['', 'unaffected']) info[m.mother].role = 'mother' }
        info.each { _s, m -> if (m.father || m.mother) { if (m.role in ['affected', '']) m.role = 'proband' } }
    }
    return info
}

def jsonString(Object x) {
    if (x == null) return 'null'
    if (x instanceof Boolean || x instanceof Number) return x.toString()
    if (x instanceof Map) return '{' + x.collect { k, v -> jsonString(k.toString()) + ':' + jsonString(v) }.join(',') + '}'
    if (x instanceof Collection) return '[' + x.collect { v -> jsonString(v) }.join(',') + ']'
    return '"' + x.toString().replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
}

workflow {
    // ---------------------------------------------------------------- mode and defaults
    if (!(params.mode in ['germline', 'somatic'])) {
        error "mode must be 'germline' or 'somatic'."
    }
    def somatic = params.mode == 'somatic'
    def min_dp = orDefault(params.min_dp, somatic ? 50 : 10)
    def report_min_vaf = orDefault(params.report_min_vaf, somatic ? 0.02 : 0.2)
    def report_max_pop_af = orDefault(params.report_max_pop_af, somatic ? 0.001 : 0.01)
    def report_name = orDefault(params.report_name, somatic ? 'afla-somatic-report.html' : 'afla-report.html')
    def umi = orDefault(params.umi_mode, 'none').toString()
    def umi_min_reads = orDefault(params.umi_min_reads, somatic ? 2 : 1)
    if (!(umi in ['none', 'inline', 'read_name'])) error "umi_mode must be none, inline or read_name."
    if (!(params.caller in ['gatk', 'deepvariant'])) error "caller must be 'gatk' or 'deepvariant'."

    // ---------------------------------------------------------------- resources (form value, else resources folder)
    if (params.resources_dir && !file(params.resources_dir.toString()).isDirectory()) {
        error "Resources folder '${params.resources_dir}' does not exist. Run scripts/afla-setup.sh first, or leave the field empty."
    }
    def P = [
        ref               : resource(params.ref, ['reference/*.fa', 'reference/*.fasta', 'reference/*.fna']),
        vep_cache         : resource(params.vep_cache, ['vep/cache', 'annotation/vep_cache', 'vep_cache'], true),
        vep_gtf           : resource(params.vep_gtf, ['vep/gtf/*.gtf.gz']),
        vep_fasta         : resource(params.vep_fasta, ['vep/fasta/*.fa', 'vep/fasta/*.fa.gz', 'annotation/fasta/*.fa']),
        vep_plugins_dir   : resource(params.vep_plugins_dir, ['vep/Plugins', 'vep/cache/Plugins', 'annotation/vep_cache/Plugins'], true),
        clinvar_vcf       : resource(params.clinvar_vcf, ['clinvar/clinvar*.vcf.gz', 'annotation/clinvar/clinvar*.vcf.gz']),
        revel_file        : resource(params.revel_file, ['revel/*.tsv.gz', 'annotation/revel/*.tsv.gz']),
        alphamissense_file: resource(params.alphamissense_file, ['alphamissense/AlphaMissense*.tsv.gz', 'annotation/alphamissense/AlphaMissense*.tsv.gz']),
        spliceai_snv      : resource(params.spliceai_snv, ['spliceai/*snv*.vcf.gz']),
        spliceai_indel    : resource(params.spliceai_indel, ['spliceai/*indel*.vcf.gz']),
        gnomad_vcf        : resource(params.gnomad_vcf, []),
        gnomad_constraint : resource(params.gnomad_constraint, ['constraint/*constraint*.tsv', 'annotation/constraint/*constraint*.tsv']),
        clinvar_protein_index: resource(params.clinvar_protein_index, ['clinvar/clinvar_protein_index.tsv.gz', 'annotation/clinvar/clinvar_protein_index.tsv.gz']),
        hpo_dir           : resource(params.hpo_dir, ['hpo'], true),
        panelapp_dir      : resource(params.panelapp_dir, ['panelapp'], true),
        germline_resource : resource(params.germline_resource, somatic ? ['somatic/af-only-gnomad*.vcf.gz'] : []),
        panel_of_normals  : resource(params.panel_of_normals, somatic ? ['somatic/*pon*.vcf.gz'] : []),
        civic_dir         : resource(params.civic_dir, ['civic'], true),
        cosmic_file       : resource(params.cosmic_file, ['cosmic/*.tsv.gz', 'cosmic/*.tsv', 'cosmic/*.vcf.gz']),
        msi_list          : resource(params.msi_list, ['msi/*.list']),
        cnv_annotation    : resource(params.refflat, ['annotation/refFlat*.txt', 'annotation/refFlat*.txt.gz', 'refflat/refFlat*.txt', 'cnv/refFlat*.txt']),
        cnv_reference     : resource(params.cnv_reference, []),
    ]

    // ---------------------------------------------------------------- input checks
    def given = [params.fastq, params.bam, params.vcf].findAll { x -> x }
    if (given.size() != 1) {
        error "Give exactly one input: a FASTQ folder, a BAM/CRAM (file or folder), or a VCF file."
    }
    def start = params.vcf ? 'vcf' : (params.bam ? 'bam' : 'fastq')
    if (start != 'vcf' && !P.ref) {
        error "A reference FASTA is needed when starting from FASTQ or BAM/CRAM (set 'Reference genome' or 'Resources folder')."
    }
    def annotate = flag(params.run_annotation)
    if (annotate && !P.vep_cache && !P.vep_gtf) {
        error "Annotation needs the Ensembl VEP cache folder (set 'VEP cache folder' or 'Resources folder'), or untick 'Annotate variants'."
    }
    def amplicon = flag(params.amplicon)
    def clip = amplicon && (params.primer_bed || params.amplicon_bed)
    if (params.amplicon_bed && !params.bed) error "An amplicon BED needs the insert/target BED ('Target regions') too, to work out the primers."
    def dedup = flag(params.mark_duplicates) && !amplicon && umi == 'none'

    def samples_info = readSamples(params.samplesheet, params.ped)
    if (params.normal_sample && !samples_info[params.normal_sample]) {
        samples_info[params.normal_sample] = [role: 'normal', sex: '', family: '', hpo: '', father: '', mother: '']
    }
    // germline families: 2+ members sharing a family id are called jointly and reported together
    def families = somatic ? [:] : samples_info.findAll { _s, m -> m.family }.groupBy { _s, m -> m.family }
        .collectEntries { fam, ms -> [fam, ms.keySet().toList()] }.findAll { _fam, ms -> ms.size() > 1 }
    def I = samples_info

    def steps = []
    def tools = [:]
    def qc = channel.empty()
    def aln = channel.empty()
    def vcf = channel.empty()
    def extra = channel.empty()      // [unit, file] extra results for the report (CNV, SV, MSI, ROH, UMI, primers)
    def ref_files = channel.empty()
    def ref_name = ''
    def targets_desc = 'none'

    // ---------------------------------------------------------------- reference
    if (start != 'vcf') {
        def fa = mainFile('Reference genome', P.ref)
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
    def fai_ch = ref_files.map { fs -> fs.find { f -> f.name.endsWith('.fai') } }

    // ---------------------------------------------------------------- primers (amplicon panels)
    def primers = channel.empty()
    if (start != 'vcf' && clip) {
        def derive = !params.primer_bed
        def src = mainFile(derive ? 'Amplicon BED' : 'Primer BED', derive ? params.amplicon_bed : params.primer_bed)
        def ins = derive ? mainFile('Target regions', params.bed) : file("${projectDir}/assets/NO_RESOURCE")
        primers = PREPARE_PRIMERS(src, ins, fai_ch, derive).collect()
    }

    // ---------------------------------------------------------------- reads -> alignment
    if (start == 'fastq') {
        def d = params.fastq
        def pairs = channel
            .fromFilePairs(["${d}/**_R{1,2}_001.f*q.gz", "${d}/**_R{1,2}.f*q.gz", "${d}/**_{1,2}.f*q.gz",
                            "${d}/**_R{1,2}_001.f*q", "${d}/**_R{1,2}.f*q", "${d}/**_{1,2}.f*q"], size: 2, flat: true)
            // the same reads saved both compressed and uncompressed: use the .gz copy once
            .map { id, r1, r2 -> [r1.name.replaceAll(/\.gz$/, ''), id, r1, r2] }
            .groupTuple()
            .map { _stem, ids, r1s, r2s ->
                def i = Math.max(0, r1s.findIndexOf { f -> f.name.endsWith('.gz') })
                if (r1s.size() > 1) {
                    log.warn "Same reads found ${r1s.size()} times (${r1s*.name.join(', ')}); using ${r1s[i]} only."
                }
                [ids[i], r1s[i], r2s[i]]
            }
            .map { id, r1, r2 -> [params.sample_name ?: sampleFromFastq(id), r1, r2] }
            .groupTuple()
            .ifEmpty { error fastqHelp(d) }
        def reads = pairs
        if (flag(params.run_fastp)) {
            FASTP(pairs, umi != 'none')
            if (umi == 'none') {
                reads = FASTP.out.reads
            }
            qc = qc.mix(FASTP.out.json.map { f -> [f.name.replace('.fastp.json', ''), f] })
            steps << (umi == 'none' ? 'fastp (trim + read QC)' : 'fastp (read QC only; reads kept intact for UMIs)')
            tools.fastp = 'fastp 1.3.7'
        }
        def raw_aln
        if (umi != 'none') {
            UMI_FASTQ_TO_BAM(reads)
            BWA_UBAM_RAW(UMI_FASTQ_TO_BAM.out, ref_files, ref_name, 'raw')
            UMI_CONSENSUS(BWA_UBAM_RAW.out, ref_files, ref_name, umi_min_reads)
            BWA_UBAM_CONS(UMI_CONSENSUS.out.ubam, ref_files, ref_name, 'consensus')
            UMI_FINALISE(BWA_UBAM_CONS.out, ref_files, ref_name)
            SORT_INDEX(UMI_FINALISE.out, ref_files, ref_name, clip)
            raw_aln = SORT_INDEX.out.aln
            if (!clip) qc = qc.mix(SORT_INDEX.out.flagstat.map { f -> [f.name.replace('.flagstat.txt', ''), f] })
            qc = qc.mix(UMI_CONSENSUS.out.families.map { f -> [f.name.replace('.umi_family_sizes.txt', ''), f] })
            steps << "UMI consensus (fgbio; UMIs ${umi == 'inline' ? 'in reads: ' + params.umi_read_structure : 'in read names'}; ≥${umi_min_reads} reads per family)"
            tools.fgbio = 'fgbio 4.1.1'
        } else {
            ALIGN(reads, ref_files, ref_name, dedup, clip)
            raw_aln = ALIGN.out.aln
            if (!clip) qc = qc.mix(ALIGN.out.flagstat.map { f -> [f.name.replace('.flagstat.txt', ''), f] })
            steps << (dedup ? 'bwa mem + samtools markdup' : 'bwa mem (no duplicate marking)')
        }
        tools['bwa + samtools'] = 'bwa 0.7.17 / samtools 1.16–1.21'
        if (clip) {
            PRIMER_CLIP(raw_aln, primers, ref_files, ref_name)
            aln = PRIMER_CLIP.out.aln
            qc = qc.mix(PRIMER_CLIP.out.flagstat.map { f -> [f.name.replace('.flagstat.txt', ''), f] })
            qc = qc.mix(PRIMER_CLIP.out.stats.map { f -> [f.name.replace('.primerclip.txt', ''), f] })
            qc = qc.mix(PRIMER_CLIP.out.counts.map { f -> [f.name.replace('.primer_counts.bedgraph', ''), f] })
            steps << 'primer clipping (samtools ampliconclip)'
        } else {
            aln = raw_aln
        }
    } else if (start == 'bam') {
        def b = mainFile('BAM/CRAM', params.bam)
        def ch = b.isDirectory() ? channel.fromPath("${b}/*.{bam,cram}") : channel.fromPath(b.toString())
        INDEX_INPUT_ALN(ch.map { f -> [(params.sample_name && !b.isDirectory()) ? params.sample_name : f.simpleName, f] }, ref_files, ref_name)
        aln = INDEX_INPUT_ALN.out.aln
        qc = qc.mix(INDEX_INPUT_ALN.out.flagstat.map { f -> [f.name.replace('.flagstat.txt', ''), f] })
        steps << 'existing BAM/CRAM'
        if (clip) {
            PRIMER_CLIP(aln, primers, ref_files, ref_name)
            aln = PRIMER_CLIP.out.aln
            qc = qc.mix(PRIMER_CLIP.out.stats.map { f -> [f.name.replace('.primerclip.txt', ''), f] })
            qc = qc.mix(PRIMER_CLIP.out.counts.map { f -> [f.name.replace('.primer_counts.bedgraph', ''), f] })
            steps << 'primer clipping (samtools ampliconclip)'
        }
    }

    // ---------------------------------------------------------------- targets, coverage
    def aln_bed = channel.empty()        // padded targets (calling)
    def aln_cov = channel.empty()        // unpadded targets (coverage)
    def clean_bed = channel.empty()
    if (start != 'vcf') {
        if (params.bed) {
            PREPARE_BED(mainFile('Target regions', params.bed), fai_ch)
            aln_bed = aln.combine(PREPARE_BED.out.padded)
            aln_cov = aln.combine(PREPARE_BED.out.clean)
            clean_bed = PREPARE_BED.out.clean
            targets_desc = "${file(params.bed).name}"
        } else {
            AUTO_TARGETS(aln, ref_files, ref_name)
            aln_bed = aln.join(AUTO_TARGETS.out)
            aln_cov = aln_bed
            targets_desc = "derived from the reads (depth >= ${params.auto_targets_min_depth}x, no BED given)"
            steps << 'target regions from coverage'
        }
        if (flag(params.run_coverage)) {
            COVERAGE(aln_cov, ref_files, ref_name)
            qc = qc.mix(COVERAGE.out.files.flatMap { s, a, b, c -> [[s, a], [s, b], [s, c]] })
            steps << 'mosdepth coverage'
            tools.mosdepth = 'mosdepth 0.3.10'
        }
    }

    // tumour/normal pairing (somatic): [tumour, aln, idx, bed, normal_aln, normal_idx]
    def no_normal = [file("${projectDir}/assets/NO_NORMAL"), file("${projectDir}/assets/NO_NORMAL_IDX")]
    def normals = aln.filter { s, _a, _i -> isNormal(I, somatic, s) }
    def paired = channel.empty()
    if (somatic && start != 'vcf') {
        def tum = aln_bed.filter { s, _a, _i, _b -> !isNormal(I, somatic, s) }
        if (params.normal_sample) {
            def one = normals.filter { s, _a, _i -> s == params.normal_sample }
                .ifEmpty { error "Matched normal '${params.normal_sample}' is not among the input samples." }
                .map { _s, a, i -> [a, i] }
            paired = tum.combine(one)
        } else {
            // the normal of the same patient (sample sheet: role 'normal', same 'family'), else tumour-only
            def with_n = tum.filter { s, _a, _i, _b -> normalOf(I, s) }
                .map { s, a, i, b -> [normalOf(I, s), s, a, i, b] }
                .combine(normals, by: 0)
                .map { _n, s, a, i, b, na, ni -> [s, a, i, b, na, ni] }
            def without = tum.filter { s, _a, _i, _b -> !normalOf(I, s) }.map { s, a, i, b -> [s, a, i, b] + no_normal }
            paired = with_n.mix(without)
        }
    }

    // ---------------------------------------------------------------- small variants
    if (start != 'vcf' && flag(params.run_calling) && somatic) {
        def res = []
        def res_args = []
        if (P.germline_resource) {
            def f = mainFile('Germline resource', P.germline_resource)
            res += [f, file("${f}.tbi")]
            res_args << "--germline-resource ${f.name}"
        }
        if (P.panel_of_normals) {
            def f = mainFile('Panel of normals', P.panel_of_normals)
            res += [f, file("${f}.tbi")]
            res_args << "--panel-of-normals ${f.name}"
        }
        if (!res) {
            res = [file("${projectDir}/assets/NO_RESOURCE")]
        }
        // run Mutect2 on chunks of the targets in parallel, then merge and filter per sample
        def chunks = SPLIT_TARGETS(paired, ref_files, ref_name)
            .map { s, a, i, c, na, ni -> [s, a, i, (c instanceof List ? c : [c]), na, ni] }
            .transpose(by: 3)
        CALL_MUTECT2(chunks, ref_files, ref_name, res, res_args.join(' '))
        MERGE_FILTER_MUTECT2(CALL_MUTECT2.out.vcf.groupTuple(), ref_files, ref_name)
        SOMATIC_FILTER(MERGE_FILTER_MUTECT2.out.vcf, ref_files, ref_name, min_dp)
        vcf = SOMATIC_FILTER.out.vcf
        steps << 'GATK Mutect2 (tumour-only, or tumour vs matched normal where given)'
        if (P.germline_resource) steps << 'germline resource: ' + file(P.germline_resource).name
        if (P.panel_of_normals) steps << 'panel of normals: ' + file(P.panel_of_normals).name
        steps << "bcftools normalise + support filter (VAF >= ${params.min_vaf}, alt reads >= ${params.min_alt_reads}, depth >= ${min_dp})"
        if (amplicon) {
            steps << 'amplicon mode: Mutect2 strand_bias/position labels not applied'
        }
        tools.gatk = 'broadinstitute/gatk:4.6.2.0'
        tools.bcftools = 'staphb/bcftools:1.23.1'
    } else if (start != 'vcf' && flag(params.run_calling)) {
        def dv = params.caller == 'deepvariant'
        def in_family = aln_bed.branch { s, _a, _i, _b -> fam: unitOf(I, families, somatic, s) != s
                                                          single: true }
        def single_raw = dv ? CALL_DEEPVARIANT(in_family.single, ref_files, ref_name, false) : CALL_GATK(in_family.single, ref_files, ref_name, false)
        def raw = single_raw.map { s, v, _t -> [s, v] }
        if (families) {
            def gv = dv ? CALL_DEEPVARIANT_FAMILY(in_family.fam, ref_files, ref_name, true) : CALL_GATK_FAMILY(in_family.fam, ref_files, ref_name, true)
            def grouped = gv.map { s, v, t -> [unitOf(I, families, somatic, s), v, t] }.groupTuple()
            def joint = dv ? JOINT_GLNEXUS(grouped, ref_files, ref_name) : JOINT_GATK(grouped, ref_files, ref_name)
            raw = raw.mix(joint)
            steps << "family joint genotyping (${dv ? 'GLnexus' : 'GATK CombineGVCFs + GenotypeGVCFs'}): ${families.collect { f, m -> f + ' = ' + m.join('+') }.join('; ')}"
        }
        vcf = NORMALISE_FILTER(raw, ref_files, ref_name, min_dp).vcf
        steps << (dv ? "DeepVariant ${params.deepvariant_model}${flag(params.use_gpu) ? ' (GPU)' : ''}" : 'GATK HaplotypeCaller')
        steps << "bcftools normalise + quality filter (QUAL >= ${params.min_qual}, depth >= ${min_dp}, GQ >= ${params.min_gq}; heterozygous VAF >= ${params.min_het_vaf})"
        tools[dv ? 'deepvariant' : 'gatk'] = dv ? "google/deepvariant:${params.deepvariant_version}${flag(params.use_gpu) ? '-gpu' : ''}" : 'broadinstitute/gatk:4.6.2.0'
        tools.bcftools = 'staphb/bcftools:1.23.1'
    }
    if (start == 'vcf') {
        def v = mainFile('VCF', params.vcf)
        vcf = PREPARE_INPUT_VCF(channel.of([params.sample_name ?: v.simpleName.replaceAll(/\.vcf$/, ''), v]))
        steps << 'existing VCF (sorted, multi-allelic sites split)'
    }

    // ---------------------------------------------------------------- runs of homozygosity (germline)
    if (!somatic && flag(params.run_roh)) {
        def roh_in = vcf
        ROH(roh_in)
        extra = extra.mix(ROH.out)
        steps << 'runs of homozygosity (bcftools roh)'
    }

    // ---------------------------------------------------------------- CNV (needs a target BED shared by all samples)
    if (start != 'vcf' && flag(params.run_cnv)) {
        if (!params.bed) {
            log.warn "CNV analysis skipped: it needs the capture-kit/panel BED ('Target regions')."
        } else {
            def ann = P.cnv_annotation ? file(P.cnv_annotation) : file("${projectDir}/assets/NO_RESOURCE")
            def tg = CNV_TARGETS(clean_bed, ann).collect()
            def cov = CNV_COVERAGE(aln, tg, ref_files, ref_name)
            def user_ref = P.cnv_reference ? file(P.cnv_reference, checkIfExists: true) : file("${projectDir}/assets/NO_RESOURCE")
            // leave-one-out pools (germline) or the normals (somatic)
            def all_cov = cov.collect(flat: false).map { l -> [l] }
            def refs_in = cov.combine(all_cov).map { s, c, all ->
                def others = somatic ? all.findAll { o -> isNormal(I, somatic, o[0]) }.collect { o -> o[1] }
                                     : all.findAll { o -> o[0] != s }.collect { o -> o[1] }
                def kind = P.cnv_reference ? 'user' : (others.size() >= (somatic ? 1 : 2) ? 'pooled' : 'flat')
                [s, c, kind == 'pooled' ? others : [file("${projectDir}/assets/NO_QC")], kind]
            }.filter { s, _c, _o, _k -> !isNormal(I, somatic, s) }
            def refs = CNV_REFERENCE(refs_in.map { s, c, o, k -> [s, c, o, k] }, tg, user_ref, ref_files, ref_name)
            def call_in = cov.join(refs).map { s, c, r, k -> [s, c, r, k] }
            CNV_CALL(call_in, somatic)
            extra = extra.mix(CNV_CALL.out.files.flatMap { s, a, b, c, d, e -> [[s, a], [s, b], [s, c], [s, d], [s, e]] }
                                                    .map { s, f -> [unitOf(I, families, somatic, s), f] })
            steps << "copy-number analysis (CNVkit, targets only; reference: ${P.cnv_reference ? 'user-provided' : 'other samples of this run, or flat if too few'})"
            tools.cnvkit = 'cnvkit 0.9.14'
        }
    }

    // ---------------------------------------------------------------- SV / fusions (Manta)
    def sv_vcf = channel.empty()
    if (start != 'vcf' && flag(params.run_sv)) {
        def manta_in = somatic ? paired : aln_bed.map { s, a, i, b -> [s, a, i, b] + no_normal }
        MANTA(manta_in, ref_files, ref_name, somatic)
        sv_vcf = MANTA.out.vcf
        steps << "structural variants / DNA fusions (Manta ${somatic ? 'somatic' : 'germline'}, exome mode)"
        tools.manta = 'manta 1.6.0'
    }

    // ---------------------------------------------------------------- MSI (somatic)
    if (somatic && start != 'vcf' && flag(params.run_msi)) {
        def ms_list = P.msi_list ? channel.value(file(P.msi_list, checkIfExists: true)) : MSI_SCAN(ref_files, ref_name).collect()
        def baseline = params.msi_baseline ? file(params.msi_baseline, checkIfExists: true) : file("${projectDir}/assets/NO_RESOURCE")
        MSI(paired, ms_list, baseline, ref_files, ref_name)
        extra = extra.mix(MSI.out.result)
        steps << 'microsatellite instability (msisensor-pro; tumour/normal, or tumour-only with ' + (params.msi_baseline ? 'baseline)' : 'default threshold)')
        tools['msisensor-pro'] = 'msisensor-pro 1.3.0'
    }

    // ---------------------------------------------------------------- annotation
    def sources = []
    def vcf_final = vcf.map { s, v, _tbi -> [s, v] }
    def sv_final = sv_vcf.map { s, v, _t -> [s, v] }
    if (annotate) {
        def extra_files = []
        def args = []
        def use_cache = P.vep_cache != null
        if (P.vep_fasta) {
            def f = mainFile('Ensembl FASTA', P.vep_fasta)
            def fi = file("${f}.fai")
            if (!fi.exists()) {
                error "Ensembl FASTA: the index ${fi.name} must be next to ${f.name}."
            }
            extra_files += [f, fi]
            if (file("${f}.gzi").exists()) extra_files << file("${f}.gzi")
            args << "--hgvs --shift_hgvs 1 --fasta ${f.name}"
        }
        if (!use_cache) {
            def g = mainFile('VEP GTF', P.vep_gtf)
            extra_files += [g, file("${g}.tbi")]
            args << "--gtf ${g.name}"
            if (!P.vep_fasta) {
                // lean install: the GTF uses the reference's own chromosome names, so the reference serves as FASTA
                if (!P.ref) error "VEP without a cache (GTF mode) needs a FASTA ('Ensembl FASTA' or 'Reference genome')."
                def f = mainFile('Reference genome', P.ref)
                extra_files += [f, file("${f}.fai")]
                args << "--hgvs --shift_hgvs 1 --fasta ${f.name}"
            }
            sources << "gene models from ${g.name}"
        }
        def plugins = []
        if (P.revel_file) {
            def f = mainFile('REVEL scores', P.revel_file)
            extra_files += [f, file("${f}.tbi")]
            plugins << "--plugin REVEL,file=${f.name}"
            sources << "REVEL (${f.name})"
        }
        if (P.alphamissense_file) {
            def f = mainFile('AlphaMissense scores', P.alphamissense_file)
            extra_files += [f, file("${f}.tbi")]
            plugins << "--plugin AlphaMissense,file=${f.name}"
            sources << "AlphaMissense (${f.name})"
        }
        if (P.spliceai_snv && P.spliceai_indel) {
            def a = mainFile('SpliceAI SNV scores', P.spliceai_snv)
            def b = mainFile('SpliceAI indel scores', P.spliceai_indel)
            extra_files += [a, file("${a}.tbi"), b, file("${b}.tbi")]
            plugins << "--plugin SpliceAI,snv=${a.name},indel=${b.name}"
            sources << "SpliceAI (${a.name})"
        }
        if (plugins) {
            def pd = file(P.vep_plugins_dir ?: "${P.vep_cache}/Plugins", checkIfExists: true)
            extra_files << pd
            args << "--dir_plugins ${pd.name}" << plugins.join(' ')
        }
        if (P.clinvar_vcf) {
            def f = mainFile('ClinVar VCF', P.clinvar_vcf)
            extra_files += [f, file("${f}.tbi")]
            args << "--custom file=${f.name},short_name=ClinVar,format=vcf,type=exact,coords=0,fields=CLNSIG%CLNREVSTAT%CLNDN%CLNSIGCONF%ONC%ONCDN%ONCREVSTAT%SCI%SCIDN"
            sources << "ClinVar (${f.name})"
        }
        if (P.gnomad_vcf) {
            def f = mainFile('gnomAD VCF', P.gnomad_vcf)
            extra_files += [f, file("${f}.tbi")]
            args << "--custom file=${f.name},short_name=gnomAD,format=vcf,type=exact,coords=0,fields=AF%AF_grpmax%nhomalt"
            sources << "gnomAD (${f.name})"
        }
        if (P.cosmic_file && P.cosmic_file.endsWith('.vcf.gz')) {
            def f = mainFile('COSMIC VCF', P.cosmic_file)
            extra_files += [f, file("${f}.tbi")]
            args << "--custom file=${f.name},short_name=COSMIC,format=vcf,type=exact,coords=0,fields=GENE%CNT%LEGACY_ID"
            sources << "COSMIC (${f.name})"
        }
        if (!extra_files) {
            extra_files = [file("${projectDir}/assets/NO_QC")]
        }
        def cache_dir = use_cache ? file(P.vep_cache, checkIfExists: true) : file("${projectDir}/assets/NO_RESOURCE")
        ANNOTATE_VEP(vcf, cache_dir, extra_files, args.join(' '), use_cache, '')
        vcf_final = ANNOTATE_VEP.out.vcf
        if (flag(params.run_sv)) {
            ANNOTATE_VEP_SV(sv_vcf, cache_dir, extra_files, args.findAll { a -> !a.startsWith('--custom') }.join(' '), use_cache, 'sv')
            sv_final = ANNOTATE_VEP_SV.out.vcf
        }
        steps << (use_cache ? "Ensembl VEP ${params.vep_cache_version} (offline cache, includes gnomAD v4.1 frequencies)" : 'Ensembl VEP (offline, GTF gene models)')
        tools.vep = 'ensemblorg/ensembl-vep:release_115.2'
    }
    extra = extra.mix(sv_final.map { s, v -> [unitOf(I, families, somatic, s), v] })

    // ---------------------------------------------------------------- report
    if (flag(params.run_report)) {
        def qc_unit = qc.map { s, f -> [unitOf(I, families, somatic, s), f] }.groupTuple()
        def ex_unit = extra.groupTuple()
        def units = vcf_final
            .join(qc_unit, remainder: true)
            .map { row -> row.size() == 3 ? row : [row[0], null, row[1]] }
            .map { u, v, q -> [u, v ?: file("${projectDir}/assets/NO_VCF"), q ?: [file("${projectDir}/assets/NO_QC")]] }
            .join(ex_unit, remainder: true)
            .filter { row -> row[1] != null }
            .map { u, v, q, e -> [u, v, q, e ?: []] }

        // knowledge files for tertiary analysis
        def kn_pairs = [
            ['--constraint', P.gnomad_constraint], ['--clinvar-index', P.clinvar_protein_index], ['--hpo-dir', P.hpo_dir],
            ['--civic-dir', P.civic_dir], ['--panelapp-dir', P.panelapp_dir], ['--refflat', P.cnv_annotation],
            ['--cosmic', (P.cosmic_file && !P.cosmic_file.endsWith('.vcf.gz')) ? P.cosmic_file : null],
            ['--gene-list-file', (params.gene_list && file(params.gene_list.toString()).exists()) ? params.gene_list : null],
        ].findAll { _o, path -> path }
        def kn = kn_pairs.collect { _o, path -> file(path.toString(), checkIfExists: true) }
        def kn_args = kn_pairs.collect { o, path -> "${o} ${file(path.toString()).name}" }
        if (!kn) kn = [file("${projectDir}/assets/NO_RESOURCE")]

        def case_info = [
            case_id: params.case_id, hpo_terms: params.hpo_terms, tumour_type: params.tumour_type,
            gene_list: (params.gene_list && !file(params.gene_list.toString()).exists()) ? params.gene_list : null,
            samples: samples_info, families: families, normal_sample: params.normal_sample,
            min_dp: min_dp, min_gq: params.min_gq, min_het_vaf: params.min_het_vaf, tmb_min_vaf: params.tmb_min_vaf, mode: params.mode,
            oncokb_token_value: params.oncokb_token ?: null,
        ]
        def case_json = channel.of(jsonString(case_info)).collectFile(name: 'afla_case.json')
        def targets_file = clean_bed.ifEmpty(file("${projectDir}/assets/NO_RESOURCE")).collect()
        SUMMARISE(units, kn, kn_args.join(' '), case_json.collect(), targets_file)
        def meta = [
            title: somatic ? 'AFLA somatic report' : 'AFLA germline report', mode: params.mode,
            normal_sample: params.normal_sample, workflow_version: workflow.manifest.version,
            date: new Date().format('yyyy-MM-dd HH:mm'), reference: P.ref ? file(P.ref).name : 'n/a',
            steps: steps, tools: tools, annotation_sources: sources, targets: targets_desc,
            mark_duplicates: dedup, amplicon: amplicon, primer_clipping: clip, umi: umi,
            report_max_pop_af: report_max_pop_af, report_min_vaf: report_min_vaf, min_dp: min_dp,
            case_id: params.case_id, hpo_terms: params.hpo_terms, tumour_type: params.tumour_type,
            params: params.findAll { k, _v -> !(k in ['help', 'version', 'disable_ping', 'oncokb_token']) },
            resources: P.findAll { _k, v -> v }.collectEntries { k, v -> [k, file(v).name] },
        ]
        REPORT(SUMMARISE.out.collect(), channel.of(jsonString(meta)).collectFile(name: 'afla_meta.json'), report_name)
    }
}
