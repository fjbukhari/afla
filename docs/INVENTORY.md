# Checking what is already installed on your laptop

`scripts/afla-inventory.sh` is a **read-only** survey of your WSL setup. It does not change, delete or upload
anything. It lists:

- system resources, free disk, GPU, `.wslconfig`
- Docker images (e.g. biocontainers, DeepVariant, GATK, VEP) and their sizes; Singularity images
- conda/mamba environments and the versions of ~40 relevant tools
- reference FASTAs, **which build they are** (from chr1 length in the `.fai`), whether they have
  alt/decoy contigs, and which aligner indexes exist (bwa, bwa-mem2, minimap2)
- VEP caches (version + build) and plugins; ClinVar, gnomAD, REVEL, AlphaMissense, SpliceAI, CADD, dbNSFP, dbSNP,
  GATK resource VCFs, with their dates from the VCF header and whether they are indexed
- capture-kit BED files, Kraken2 / Exomiser / MetaPhlAn / AMRFinder databases
- a per-folder summary of FASTQ/BAM/CRAM files, and the first read header of one FASTQ (to confirm DNBSEQ/read length)
- the 40 largest files, to plan space clean-up

## Run it (in your WSL Ubuntu terminal)

```bash
cd ~
git clone -b claude/epi2me-illumina-ngs-pipeline-6qkr8o https://github.com/fjbukhari/afla.git
bash afla/scripts/afla-inventory.sh
# if some data lives on a Windows drive, add those folders (slower to scan):
# bash afla/scripts/afla-inventory.sh /mnt/d/genomics
```

If `git clone` asks for credentials (private repo), open `scripts/afla-inventory.sh` on GitHub, click **Raw**,
copy it, and save it in WSL with `nano afla-inventory.sh`.

It takes a few minutes and writes `afla-inventory-<date>.txt` in the current folder.

## Share the result

The file contains **folder and file names only**, with your home folder shown as `~`. Check that no patient
identifiers appear in folder names, then either:
- paste the contents into the Claude chat, or
- upload the file to the repo on GitHub (**Add file → Upload files**, folder `inventory/`, on the branch above).

Each item will then be marked **keep / update / re-download / delete** against the plan's requirements
(GRCh38 no-alt analysis set, matching indexes, VEP cache version, recent ClinVar, and so on).
