#!/usr/bin/env bash
# AFLA classroom USB kit: install AFLA on computers with slow or no internet.
#
#   On a PREPARED computer (AFLA working, resources downloaded, Docker running):
#     bash scripts/afla-usb-kit.sh pack   --usb /mnt/e [--resources DIR] [--testdata DIR] [--no-deepvariant] [--no-testdata] [--no-images]
#   On each NEW computer (WSL2 Ubuntu + Docker Desktop + EPI2ME Desktop already installed):
#     bash /mnt/e/AFLA-KIT/afla-usb-kit.sh unpack --usb /mnt/e [--resources-dest DIR]
#
# The kit (folder AFLA-KIT on the drive) holds:
#   afla.bundle        the AFLA code at the current release (git bundle, ~5 MB)
#   images/*.tar.gz    every Docker container the workflows use (~12 GB; +3-7 GB with DeepVariant)
#   afla-resources/    reference genome and databases (~45 GB full, ~15 GB lean)
#   afla-testdata/     GIAB practice data (~1.5 GB)
#   KIT_INFO.txt       version, contents, checksums of the images
# Use a drive of 128 GB formatted as exFAT or NTFS (FAT32 cannot hold files over 4 GB).
# Installers for WSL/Docker Desktop/EPI2ME are NOT included: get them from their official sites (licences).
# Non-commercial databases (REVEL, AlphaMissense, ...) may only be shared within your own non-profit teaching use.
set -uo pipefail

MODE=${1:-}; shift || true
USB=""; RES=""; TD=""; DV=1; WITH_TD=1; RES_DEST=""; IMAGES=1
while [ $# -gt 0 ]; do
  case "$1" in
    --usb) USB=$2; shift 2 ;;
    --resources) RES=$2; shift 2 ;;
    --testdata) TD=$2; shift 2 ;;
    --resources-dest) RES_DEST=$2; shift 2 ;;
    --no-deepvariant) DV=0; shift ;;
    --no-testdata) WITH_TD=0; shift ;;
    --no-images) IMAGES=0; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
done
[ -n "$MODE" ] && [ -n "$USB" ] || { sed -n '2,20p' "$0"; exit 1; }
KIT="$USB/AFLA-KIT"
say() { echo "== $*"; }
winhome() {
  local u; u=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')
  if [ -n "$u" ] && [ -d "/mnt/c/Users/$u" ]; then echo "/mnt/c/Users/$u"; else echo "$HOME"; fi
}
# copy a folder's contents (rsync shows progress and resumes; plain cp works everywhere)
copydir() {
  mkdir -p "$2"
  if command -v rsync >/dev/null; then rsync -a --info=progress2 --exclude setup.log "$1/" "$2/"; else cp -a "$1/." "$2/"; fi
}
free_gb() { df -Pk "$1" | awk 'NR==2 {printf "%d", $4/1048576}'; }

# container images named in the workflow (DeepVariant's tag depends on two parameters)
images() {
  local repo=$1
  grep -ho 'container "[^"$]*"' "$repo"/modules/*.nf | sed 's/container "//; s/"$//' | sort -u
  if [ $DV -eq 1 ]; then
    local v; v=$(sed -n 's/.*deepvariant_version = "\([^"]*\)".*/\1/p' "$repo/nextflow.config" | head -n1)
    echo "google/deepvariant:$v"; echo "google/deepvariant:$v-gpu"
  fi
  echo "quay.io/biocontainers/htslib:1.21--h566b1c6_1"       # used by afla-setup.sh
  echo "quay.io/biocontainers/rtg-tools:3.13--hdfd78af_0"    # used by afla-benchmark.sh
}
fname() { echo "$1" | tr '/:' '__'; }

# ======================================================================================== pack
if [ "$MODE" = pack ]; then
  REPO=$(cd "$(dirname "$0")/.." && pwd)
  RES=${RES:-$(winhome)/afla-resources}
  TD=${TD:-$(winhome)/afla-testdata}
  [ -d "$USB" ] || { echo "Drive $USB not found (Windows drive E: is /mnt/e in Ubuntu)."; exit 1; }
  mkdir -p "$KIT/images" || exit 1
  fs=$(df -PT "$USB" | awk 'NR==2 {print $2}')
  echo "Kit folder: $KIT (file system: $fs, free: $(free_gb "$USB") GB)"
  case "$fs" in vfat|msdos) echo "The drive is FAT32: files over 4 GB will fail. Reformat as exFAT or NTFS."; exit 1 ;; esac

  say "AFLA code"
  (cd "$REPO" && git bundle create "$KIT/afla.bundle" --all >/dev/null 2>&1) || { echo "git bundle failed"; exit 1; }
  VERSION=$(cd "$REPO" && git describe --tags --always 2>/dev/null)
  cp "$0" "$KIT/afla-usb-kit.sh"
  cp "$REPO/docs/INSTALL.md" "$KIT/INSTALL.md" 2>/dev/null || true

  say "Docker images"
  if [ $IMAGES -eq 0 ]; then echo "  skipped (--no-images): each computer downloads containers on its first run"
  elif ! docker info >/dev/null 2>&1; then echo "Docker is not running: start Docker Desktop and try again (or use --no-images)."; exit 1
  else
  : > "$KIT/images/SHA256SUMS"
  for img in $(images "$REPO"); do
    f="$KIT/images/$(fname "$img").tar.gz"
    if [ -s "$f" ]; then echo "  kept   $img"; else
      docker image inspect "$img" >/dev/null 2>&1 || { echo "  pull   $img"; docker pull -q "$img" >/dev/null || { echo "  ! could not pull $img"; continue; }; }
      echo "  save   $img"
      docker save "$img" | gzip -1 > "$f.part" && mv "$f.part" "$f"
    fi
    (cd "$KIT/images" && sha256sum "$(basename "$f")" >> SHA256SUMS)
  done
  fi

  say "Resources ($RES)"
  if [ -d "$RES" ]; then
    need=$(du -s --block-size=1G "$RES" | cut -f1)
    [ "$(free_gb "$USB")" -gt "$need" ] || { echo "  ! not enough space on the drive for resources (~$need GB)"; exit 1; }
    copydir "$RES" "$KIT/afla-resources"
  else echo "  ! $RES not found: the kit will have no resources (run afla-setup.sh on each computer instead)"; fi

  if [ $WITH_TD -eq 1 ] && [ -d "$TD" ]; then say "Practice data ($TD)"; copydir "$TD" "$KIT/afla-testdata"; fi

  cat > "$KIT/KIT_INFO.txt" <<EOF
AFLA classroom kit
Made: $(date)   AFLA version: $VERSION
Images: $(ls "$KIT"/images/*.tar.gz 2>/dev/null | wc -l)   Kit size: $(du -sh "$KIT" | cut -f1)
Contents: $(ls "$KIT" | tr '\n' ' ')

On a new computer (WSL2 Ubuntu, Docker Desktop and EPI2ME Desktop installed first; see INSTALL.md):
  open Ubuntu and run:  bash /mnt/<drive letter>/AFLA-KIT/afla-usb-kit.sh unpack --usb /mnt/<drive letter>
Education and research use only.
EOF
  say "Done: $(du -sh "$KIT" | cut -f1) in $KIT"
  exit 0
fi

# ======================================================================================== unpack
if [ "$MODE" = unpack ]; then
  [ -d "$KIT" ] || { echo "No AFLA-KIT folder on $USB"; exit 1; }
  cat "$KIT/KIT_INFO.txt" 2>/dev/null | head -n 3
  command -v git >/dev/null || { echo "git is missing: sudo apt install -y git rsync (needs internet once), or install from the Ubuntu image."; exit 1; }
  ls "$KIT"/images/*.tar.gz >/dev/null 2>&1 && ! docker info >/dev/null 2>&1 && { echo "Docker is not reachable from Ubuntu: start Docker Desktop and enable WSL integration for Ubuntu."; exit 1; }

  say "AFLA code -> ~/afla"
  if [ -d "$HOME/afla/.git" ]; then
    (cd "$HOME/afla" && git fetch -q "$KIT/afla.bundle" '+refs/heads/*:refs/remotes/kit/*' '+refs/tags/*:refs/tags/*' && \
      git checkout -q "$(git -C "$HOME/afla" describe --tags --abbrev=0 2>/dev/null || echo kit/HEAD)") && echo "  updated"
  else
    git clone -q "$KIT/afla.bundle" "$HOME/afla" && echo "  installed"
    tag=$(git -C "$HOME/afla" describe --tags --abbrev=0 2>/dev/null) && git -C "$HOME/afla" checkout -q "$tag"
  fi
  (cd "$HOME/afla" && echo "  version: $(git describe --tags --always)")

  say "Docker images (a few minutes)"
  [ -s "$KIT/images/SHA256SUMS" ] && { (cd "$KIT/images" && sha256sum -c --quiet SHA256SUMS) || echo "  ! some image files are damaged: copy the kit again"; }
  ls "$KIT"/images/*.tar.gz >/dev/null 2>&1 || echo "  none in the kit: containers will be downloaded on the first run (internet needed once)"
  for f in "$KIT"/images/*.tar.gz; do
    [ -e "$f" ] || continue
    echo "  load $(basename "$f" .tar.gz)"; gunzip -c "$f" | docker load -q >/dev/null || echo "  ! failed: $f"
  done

  WH=$(winhome)
  RES_DEST=${RES_DEST:-$WH/afla-resources}
  if [ -d "$KIT/afla-resources" ]; then
    say "Resources -> $RES_DEST"
    need=$(du -s --block-size=1G "$KIT/afla-resources" | cut -f1)
    mkdir -p "$RES_DEST"
    [ "$(free_gb "$RES_DEST")" -gt $((need + 15)) ] || { echo "  ! not enough free disk (need ~$((need + 15)) GB incl. room for runs)"; exit 1; }
    copydir "$KIT/afla-resources" "$RES_DEST"
  fi
  if [ -d "$KIT/afla-testdata" ]; then say "Practice data -> $WH/afla-testdata"; copydir "$KIT/afla-testdata" "$WH/afla-testdata"; fi

  say "EPI2ME"
  bash "$HOME/afla/scripts/install-epi2me.sh" || echo "  Open EPI2ME Desktop once, then run: bash ~/afla/scripts/install-epi2me.sh"
  cat <<EOF

Ready. Restart EPI2ME Desktop: "AFLA germline" and "AFLA somatic" appear.
In the form, set "Resources folder" to: $(wslpath -w "$RES_DEST" 2>/dev/null || echo "$RES_DEST")
Practice data: $(wslpath -w "$WH/afla-testdata" 2>/dev/null || echo "$WH/afla-testdata")  (see docs/TEACHING_GUIDE.md)
EOF
  exit 0
fi
echo "First word must be 'pack' or 'unpack'."; exit 1
