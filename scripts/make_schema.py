#!/usr/bin/env python3
"""Writes the EPI2ME/Nextflow forms from one definition:
   nextflow_schema.json          (AFLA germline; "Analysis mode" can switch to somatic)
   somatic/nextflow_schema.json  (AFLA somatic copy made by scripts/install-epi2me.sh)
Run after changing parameters:  python3 scripts/make_schema.py
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def P(title, typ, desc, default=None, help_text=None, fmt=None, enum=None, minimum=None, maximum=None, hidden=False):
    d = {"title": title, "type": typ, "description": desc}
    if fmt:
        d["format"] = fmt
    if default is not None:
        d["default"] = default
    if enum:
        d["enum"] = enum
    if minimum is not None:
        d["minimum"] = minimum
    if maximum is not None:
        d["maximum"] = maximum
    if help_text:
        d["help_text"] = help_text
    if hidden:
        d["hidden"] = True
    return d


SECTIONS = [
    ("analysis", "Analysis", "fas fa-microscope", "What kind of analysis to run.", {
        "mode": P("Analysis mode", "string", "germline = inherited variants (rare disease, carrier, panels/exomes). somatic = tumour samples (Mutect2, low-frequency variants, TMB, MSI, tiers).",
                  "germline", enum=["germline", "somatic"],
                  help_text="Both modes share the same steps for reads, alignment, coverage and CNV. Germline adds ACMG/AMP evidence, phenotype (HPO) ranking, family analysis and runs of homozygosity; somatic adds Mutect2, MSI, TMB and AMP/ASCO/CAP tier suggestions."),
    }),
    ("input", "Input", "fas fa-arrow-right", "Give ONE input. This also decides where the workflow starts: FASTQ = full analysis, BAM/CRAM = skip alignment, VCF = annotation and report only.", {
        "fastq": P("FASTQ folder", "string", "Folder with paired FASTQ files (*_R1_001 / *_R2_001, or *_1 / *_2; .fastq, .fq, .fastq.gz or .fq.gz). Sub-folders are searched too.", fmt="directory-path",
                   help_text="Each sample needs an R1 and an R2 file. Several lanes of the same sample (_L001, _L002, ...) are joined automatically. Illumina and DNBSEQ (BGI/MGI) reads both work. Files are read where they are; nothing is copied. Avoid spaces and '+' in folder names."),
        "bam": P("BAM / CRAM (file or folder)", "string", "Already-aligned reads (GRCh38). Alignment is skipped.", fmt="path",
                 help_text="Must be aligned to the same reference chosen below."),
        "vcf": P("VCF file", "string", "Existing variant file (GRCh38, from any pipeline: this workflow, Galaxy, DRAGEN, GATK, EPI2ME wf-human-variation, a sequencing provider...). Only annotation and the report are run.", fmt="file-path"),
        "sample_name": P("Sample name (optional)", "string", "Overrides the name taken from the file names. With a FASTQ folder, ALL files are then treated as one sample."),
        "samplesheet": P("Sample sheet (optional CSV)", "string", "Describes samples: columns sample,role,sex,family,hpo. Roles: proband, mother, father, affected, unaffected (germline); tumour, normal (somatic).", fmt="file-path",
                         help_text="Germline: samples sharing a 'family' value are genotyped together and inheritance (de novo, compound heterozygous, homozygous, X-linked) is worked out for the proband. Somatic: a tumour and a normal with the same 'family' (patient) value are analysed as a pair. 'hpo' can hold the proband's HPO terms, e.g. HP:0001250; HP:0001263."),
        "ped": P("PED file (optional)", "string", "Classic pedigree file (family, sample, father, mother, sex, phenotype) as an alternative to the sample sheet.", fmt="file-path"),
    }),
    ("resources", "Reference and resources", "fas fa-dna", "Easiest: set 'Resources folder' to the folder made by scripts/afla-setup.sh; every file below is then found automatically. Set individual files only to override.", {
        "resources_dir": P("Resources folder", "string", "Folder made by scripts/afla-setup.sh (reference, VEP cache, ClinVar, REVEL, AlphaMissense, gnomAD constraint, HPO, PanelApp, CIViC, somatic resources...).", fmt="directory-path"),
        "ref": P("Reference genome (FASTA)", "string", "GRCh38 FASTA, uncompressed (recommended: GRCh38 no-alt analysis set). Not needed when starting from a VCF.", fmt="file-path",
                 help_text="bwa index files (.amb .ann .bwt .pac .sa) should sit next to it. The .fai and .dict files are made automatically if missing. If you pick the .fai by mistake, the file next to it is used."),
        "build_bwa_index": P("Build bwa index if missing", "boolean", "Builds the aligner index for the reference (about 1 hour and ~5 GB, once). Saved in the output folder under reference/; copy it next to the FASTA to reuse it.", False),
        "bed": P("Target regions (BED)", "string", "Capture kit or panel regions (hg38). Needed for CNV analysis and TMB; if empty, regions covered by the reads are used for calling.", fmt="file-path",
                 help_text="Chromosome names with or without 'chr' are both accepted. For amplicon panels give the INSERT (target) regions here."),
        "bed_padding": P("Padding around targets (bp)", "integer", "Extra bases added on each side of every target region for variant calling (splice sites).", 100, minimum=0),
        "auto_targets_min_depth": P("Minimum depth for automatic targets", "integer", "Only without a BED: positions with at least this many reads are treated as targets.", 20, minimum=1),
    }),
    ("library", "Library type (amplicon, UMI)", "fas fa-vial", "Hybrid-capture, tagmentation and ligation libraries need no settings here. Amplicon (PCR) panels and UMI libraries do.", {
        "amplicon": P("Amplicon panel", "boolean", "Tick for amplicon (PCR) panels: AmpliSeq, TruSight/TSCA, QIAseq, CleanPlex... Duplicate marking is switched off (amplicon reads start at the same place by design).", False),
        "primer_bed": P("Primer BED (amplicon)", "string", "Primer positions, one line per primer (strand in column 6 if known). Primer bases are soft-clipped so they cannot hide or fake variants at amplicon ends.", fmt="file-path",
                        help_text="Get it from the panel vendor (e.g. AmpliSeq 'primers' BED), or convert an Illumina TruSeq/TSCA manifest with scripts/manifest_to_primers.py."),
        "amplicon_bed": P("Amplicon BED (alternative)", "string", "Whole amplicons including primers. Together with 'Target regions' (the inserts) the primers are worked out as amplicon minus insert.", fmt="file-path"),
        "umi_mode": P("UMIs (unique molecular identifiers)", "string", "none = no UMIs. inline = UMI bases at the start of the reads (give the read structure). read_name = UMI already in the read names (bcl-convert/BCL Convert 'UMI in read header').",
                      "none", enum=["none", "inline", "read_name"],
                      help_text="With UMIs, reads from the same original DNA molecule are merged into one consensus read (fgbio), which removes PCR and sequencing errors: important for low-frequency somatic variants. Duplicate marking is not used."),
        "umi_read_structure": P("UMI read structure (inline)", "string", "fgbio read structures for R1 and R2, e.g. '12M11S+T +T' (QIAseq: 12-base UMI + 11-base spacer at the start of read 2 is written '+T 12M11S+T'), '8M+T 8M+T' (8-base UMI on both reads). M = UMI, S = skip, T = template.", "+T +T"),
        "umi_min_reads": P("Minimum reads per UMI family", "integer", "Consensus reads need at least this many raw reads. Default: germline 1, somatic 2.", minimum=1),
    }),
    ("steps", "Steps to run", "fas fa-list-check", "Tick or untick steps. Steps that do not apply to your input are skipped automatically.", {
        "run_fastp": P("Read QC and trimming (fastp)", "boolean", "Removes adapters and low-quality ends, writes a read-quality report.", True),
        "mark_duplicates": P("Mark duplicate reads", "boolean", "Keep ON for exomes and hybrid-capture panels. Ignored for amplicon panels and UMI libraries.", True),
        "run_coverage": P("Coverage QC (mosdepth)", "boolean", "Mean depth, % of target bases at 10–500x, poorly covered regions.", True),
        "run_calling": P("Small-variant calling", "boolean", "SNVs and small indels. Turn off to stop after alignment and coverage.", True),
        "caller": P("Germline variant caller", "string", "gatk = GATK HaplotypeCaller (CPU). deepvariant = Google DeepVariant (uses the GPU; first use downloads a large container). Somatic mode always uses Mutect2.",
                    "gatk", enum=["gatk", "deepvariant"]),
        "deepvariant_version": P("DeepVariant version", "string", "Container version of google/deepvariant.", "1.9.0", hidden=True),
        "deepvariant_model": P("DeepVariant model", "string", "WES for exomes and panels, WGS for genomes.", "WES", enum=["WES", "WGS"]),
        "use_gpu": P("Use the GPU (DeepVariant)", "boolean", "Needs an NVIDIA GPU visible to Docker (see scripts/afla-gpu-check.sh).", True),
        "run_cnv": P("Copy-number variants (CNVkit)", "boolean", "Gains and losses from read depth. Needs the target BED. Best with 3+ samples of the same kit in one run, or a CNV reference.", True),
        "cnv_reference": P("CNV reference (.cnn, optional)", "string", "CNVkit reference built from normal samples of the same kit (scripts/afla-cnv-reference.sh). Much more reliable than a flat reference.", fmt="file-path"),
        "run_sv": P("Structural variants / DNA fusions (Manta)", "boolean", "Deletions, duplications, inversions and translocations with breakpoints near targeted regions. Slower; off by default.", False),
        "run_roh": P("Runs of homozygosity (germline)", "boolean", "Long homozygous stretches: consanguinity and recessive disease genes.", True),
        "run_msi": P("Microsatellite instability (somatic)", "boolean", "msisensor-pro, tumour/normal or tumour-only. The microsatellite list is made from the reference once.", True),
        "msi_baseline": P("MSI tumour-only baseline (optional)", "string", "msisensor-pro baseline built from normal samples of the same assay; improves tumour-only MSI.", fmt="file-path"),
        "run_annotation": P("Annotate variants (VEP)", "boolean", "Genes, consequences, population frequencies and scores. Needs the VEP cache (or resources folder).", True),
        "run_report": P("Interactive report", "boolean", "One HTML report for all samples, with a printable case report.", True),
    }),
    ("case", "Case information (germline)", "fas fa-user-doctor", "Optional details that make the report smarter.", {
        "case_id": P("Case ID", "string", "Pseudonymous identifier shown in the report. Never use real names."),
        "hpo_terms": P("HPO terms", "string", "Patient phenotype as HPO IDs, e.g. 'HP:0001250, HP:0001263'. Genes are ranked by how well their known phenotypes match (find terms at hpo.jax.org).",
                       help_text="With a sample sheet, the 'hpo' column can hold per-proband terms instead."),
        "gene_list": P("Gene list / virtual panel", "string", "Genes of interest: comma-separated symbols, or a file (one gene per line, or a PanelApp TSV). Variants in these genes are highlighted and filterable."),
    }),
    ("somatic", "Somatic settings", "fas fa-disease", "Used in somatic mode only.", {
        "normal_sample": P("Matched normal sample name", "string", "If the input has the patient's normal (blood) sample, enter its name; every other sample is called against it. With a sample sheet, use role 'normal' instead."),
        "tumour_type": P("Tumour type", "string", "Free text, e.g. 'acute myeloid leukaemia', 'lung adenocarcinoma'. Evidence in the same tumour type supports tier I; other tumour types tier II."),
        "min_vaf": P("Minimum VAF", "number", "Calls below this variant allele fraction are labelled LowSupport.", 0.02, minimum=0, maximum=1),
        "min_alt_reads": P("Minimum supporting reads", "integer", "Calls with fewer variant reads are labelled LowSupport.", 5, minimum=1),
        "germline_resource": P("Germline resource (gnomAD af-only)", "string", "GATK af-only-gnomad.hg38.vcf.gz: helps Mutect2 recognise common inherited variants.", fmt="file-path"),
        "panel_of_normals": P("Panel of normals", "string", "Mutect2 PoN (GATK 1000g_pon.hg38.vcf.gz, or better one made from your own assay) to remove recurrent artefacts.", fmt="file-path"),
        "mutect2_shards": P("Mutect2 parallel chunks", "integer", "Split targets into chunks run in parallel. 1 is best for panels; 4–8 can speed up exomes.", 1, minimum=1),
        "tmb_min_vaf": P("TMB minimum VAF", "number", "Coding variants counted for tumour mutational burden must reach this VAF.", 0.05, minimum=0, maximum=1),
        "cosmic_file": P("COSMIC file (optional)", "string", "COSMIC Cancer Mutation Census TSV or CosmicCodingMuts VCF (free for academic use after registration; not redistributed).", fmt="file-path"),
        "oncokb_token": P("OncoKB API token (optional)", "string", "Free academic token from oncokb.org. Needs internet during the run. Leave empty to skip."),
    }),
    ("variant_filter", "Variant quality filters", "fas fa-filter", "Calls failing these are kept but labelled (LowQual/LowSupport). Empty = mode default.", {
        "min_qual": P("Minimum QUAL (germline)", "integer", "Variant quality score.", 30, minimum=0),
        "min_dp": P("Minimum read depth", "integer", "Default: germline 10, somatic 50.", minimum=0),
        "min_gq": P("Minimum genotype quality (germline)", "integer", "Confidence in the genotype.", 20, minimum=0),
        "min_het_vaf": P("Minimum heterozygous VAF (germline)", "number", "Heterozygous calls in fewer reads are labelled LowVAF: usually PCR/homopolymer artefacts (in GIAB exome tests this raised indel precision from ~76% to ~88% without losing true variants). Lower it to look for mosaic variants.", 0.2, minimum=0, maximum=1),
    }),
    ("annotation", "Annotation sources (optional overrides)", "fas fa-book-medical", "Normally found in the resources folder. Set here to use other files.", {
        "vep_cache": P("VEP cache folder", "string", "Folder that contains homo_sapiens/<version>_GRCh38 (Ensembl VEP offline cache; includes gnomAD v4.1 frequencies).", fmt="directory-path"),
        "vep_cache_version": P("VEP cache version", "integer", "Must match the cache folder.", 115),
        "vep_gtf": P("VEP GTF (instead of cache)", "string", "Bgzipped, tabix-indexed GTF gene models for a lean install without the cache (needs the FASTA below; gnomAD then comes from 'gnomAD VCF').", fmt="file-path"),
        "vep_fasta": P("Ensembl FASTA (for HGVS)", "string", "Homo_sapiens.GRCh38.dna.primary_assembly.fa with .fai, used for HGVS notation.", fmt="file-path"),
        "vep_plugins_dir": P("VEP plugins folder", "string", "Folder with REVEL.pm, AlphaMissense.pm, SpliceAI.pm (default: Plugins inside the cache).", fmt="directory-path"),
        "clinvar_vcf": P("ClinVar VCF", "string", "clinvar.vcf.gz (GRCh38) with its .tbi.", fmt="file-path"),
        "revel_file": P("REVEL scores", "string", "Tabix-indexed REVEL file prepared for the VEP plugin (free for non-commercial use).", fmt="file-path"),
        "alphamissense_file": P("AlphaMissense scores", "string", "AlphaMissense_hg38.tsv.gz prepared for the VEP plugin (tabix-indexed).", fmt="file-path"),
        "spliceai_snv": P("SpliceAI SNV scores", "string", "Precomputed SpliceAI SNV VCF (Illumina; free for non-commercial use after registration).", fmt="file-path"),
        "spliceai_indel": P("SpliceAI indel scores", "string", "Precomputed SpliceAI indel VCF.", fmt="file-path"),
        "gnomad_vcf": P("gnomAD VCF (optional)", "string", "Extra gnomAD sites VCF (AF, AF_grpmax, nhomalt). Not needed with the VEP cache.", fmt="file-path"),
        "gnomad_constraint": P("gnomAD constraint table", "string", "gnomad.v4.1.constraint_metrics.tsv: gene loss-of-function intolerance (ACMG PVS1) and missense constraint (PP2).", fmt="file-path"),
        "clinvar_protein_index": P("ClinVar amino-acid index", "string", "Made by scripts/afla-setup.sh: ClinVar pathogenic missense changes (ACMG PS1/PM5).", fmt="file-path"),
        "hpo_dir": P("HPO folder", "string", "Folder with hp.obo and genes_to_phenotype.txt.", fmt="directory-path"),
        "panelapp_dir": P("PanelApp folder", "string", "Gene panels downloaded by scripts/afla-setup.sh (selectable in the report).", fmt="directory-path"),
        "civic_dir": P("CIViC folder", "string", "CIViC nightly TSVs (somatic evidence, CC0).", fmt="directory-path"),
        "refflat": P("Gene models (refFlat)", "string", "Gene names for CNV regions and coding size for TMB.", fmt="file-path"),
        "msi_list": P("Microsatellite list", "string", "msisensor-pro scan of the reference (made automatically if empty).", fmt="file-path"),
    }),
    ("output", "Output and report", "fas fa-file-export", "", {
        "output_format": P("Alignment format", "string", "cram is ~50% smaller than bam.", "cram", enum=["cram", "bam"]),
        "report_max_pop_af": P("Report: default max population AF", "number", "Starting filter in the report (changeable there). Default: germline 0.01, somatic 0.001.", minimum=0, maximum=1),
        "report_min_vaf": P("Report: default min VAF", "number", "Starting filter in the report. Default: germline 0.2, somatic 0.02.", minimum=0, maximum=1),
        "report_name": P("Report file name", "string", "Default: afla-report.html (germline) or afla-somatic-report.html."),
    }),
    ("machine", "Computer resources", "fas fa-microchip", "Detected automatically; only change to leave room for other work.", {
        "max_cpus": P("Maximum CPUs", "integer", "Default: all CPUs of this computer.", minimum=1),
        "max_memory": P("Maximum memory", "string", "e.g. '24 GB'. Default: 85% of this computer's memory (inside WSL: what .wslconfig allows)."),
        "threads": P("Threads for the heaviest steps", "integer", "Default: maximum CPUs.", minimum=1),
    }),
    ("misc", "Miscellaneous", "fas fa-cog", "", {
        "disable_ping": P("Disable ping", "boolean", "Not used.", True, hidden=True),
        "help": P("Help", "boolean", "Not used.", False, hidden=True),
        "version": P("Version", "boolean", "Not used.", False, hidden=True),
    }),
]


def schema(somatic):
    defs = {}
    for key, title, icon, desc, props in SECTIONS:
        props = copy.deepcopy(props)
        if somatic and key == "analysis":
            props["mode"]["default"] = "somatic"
        if somatic and key == "case":
            continue
        defs[key] = {"title": title, "type": "object", "fa_icon": icon, "description": desc, "properties": props}
    order = list(defs)
    if somatic:
        order.remove("somatic")
        order.insert(order.index("library") + 1, "somatic")
    return {
        "$schema": "http://json-schema.org/draft-07/schema",
        "$id": "https://raw.githubusercontent.com/fjbukhari/afla/main/nextflow_schema.json",
        "title": "fjbukhari/afla-somatic" if somatic else "fjbukhari/afla",
        "workflow_title": "AFLA somatic (short reads)" if somatic else "AFLA germline (short reads)",
        "description": ("Somatic analysis of short-read (Illumina/DNBSEQ) tumour panels and exomes: Mutect2 (tumour-only or tumour/normal), UMI consensus, primer clipping, CNV, SV/fusions, MSI, TMB, CIViC/OncoKB evidence and AMP/ASCO/CAP tier suggestions, with an interactive teaching report. Education and research use only, not for clinical use."
                        if somatic else
                        "Germline analysis of short-read (Illumina/DNBSEQ) panels and exomes, from FASTQ, BAM or VCF: QC, alignment, GATK/DeepVariant calling (families jointly), CNV, SV, ROH, VEP annotation, ACMG/AMP evidence suggestions, HPO gene ranking and a printable teaching case report. Switch 'Analysis mode' to somatic for tumours. Education and research use only, not for clinical use."),
        "url": "https://github.com/fjbukhari/afla",
        "type": "object",
        "definitions": {k: defs[k] for k in order},
        "allOf": [{"$ref": f"#/definitions/{k}"} for k in order],
        "properties": {"out_dir": {"type": "string", "default": "output", "hidden": True}},
        "resources": {
            "recommended": {"cpus": 12, "memory": "32GB"},
            "minimum": {"cpus": 4, "memory": "12GB"},
            "run_time": "Panel: 10-30 minutes. Exome: about 2-4 hours on a 16-core laptop.",
            "arm_support": False,
        },
    }


if __name__ == "__main__":
    (ROOT / "nextflow_schema.json").write_text(json.dumps(schema(False), indent=4, ensure_ascii=False) + "\n")
    (ROOT / "somatic" / "nextflow_schema.json").write_text(json.dumps(schema(True), indent=4, ensure_ascii=False) + "\n")
    print("wrote nextflow_schema.json and somatic/nextflow_schema.json")
