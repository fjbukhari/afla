#!/usr/bin/env bash
# Installs (or updates) the AFLA workflows in EPI2ME Desktop's workflow folder:
#   fjbukhari/afla          germline  (this repository as it is)
#   fjbukhari/afla-somatic  somatic   (same code; form, output list and mode from somatic/)
# Usage: bash scripts/install-epi2me.sh [EPI2ME workflows folder]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
DEST=${1:-/mnt/c/Users/fjbuk/epi2melabs/workflows/fjbukhari}
EXCL=(--exclude output --exclude work --exclude '.nextflow*' --exclude somatic)

mkdir -p "$DEST/afla" "$DEST/afla-somatic"
rsync -a --delete "${EXCL[@]}" "$REPO/" "$DEST/afla/"
rsync -a --delete "${EXCL[@]}" "$REPO/" "$DEST/afla-somatic/"
cp "$REPO/somatic/mode.config" "$DEST/afla-somatic/conf/mode.config"
cp "$REPO/somatic/nextflow_schema.json" "$DEST/afla-somatic/nextflow_schema.json"
cp "$REPO/somatic/output_definition.json" "$DEST/afla-somatic/output_definition.json"
for d in afla afla-somatic; do (cd "$DEST/$d" && git config core.filemode false); done
echo "Installed: $DEST/afla (germline) and $DEST/afla-somatic (somatic). Restart EPI2ME Desktop to see changes."
