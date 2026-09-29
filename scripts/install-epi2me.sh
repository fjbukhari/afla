#!/usr/bin/env bash
# Installs (or updates) the AFLA workflows in EPI2ME Desktop's workflow folder as two entries:
#   fjbukhari/afla          "AFLA germline"  (this repository; its form can also switch to somatic)
#   fjbukhari/afla-somatic  "AFLA somatic"   (same code; somatic form and defaults from somatic/)
# Other computers can instead import https://github.com/fjbukhari/afla in EPI2ME ("Import workflow"),
# which gives the germline entry with the "Analysis mode" switch.
#
# Usage: bash scripts/install-epi2me.sh [EPI2ME workflows folder]
# The folder is found automatically (Windows: C:\Users\<you>\epi2melabs\workflows; Linux/macOS: ~/epi2melabs/workflows).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
DEST=${1:-}
if [ -z "$DEST" ]; then
  for c in /mnt/c/Users/*/epi2melabs/workflows "$HOME/epi2melabs/workflows" "$HOME/Library/Application Support/EPI2ME/workflows"; do
    if [ -d "$c" ]; then DEST="$c"; break; fi
  done
fi
if [ -z "$DEST" ]; then
  echo "EPI2ME workflow folder not found. Open EPI2ME Desktop once (so it creates it), or give the folder:"
  echo "  bash scripts/install-epi2me.sh /mnt/c/Users/<you>/epi2melabs/workflows"
  exit 1
fi
DEST="$DEST/fjbukhari"
python3 "$REPO/scripts/make_schema.py" >/dev/null 2>&1 || true
EXCL=(--exclude output --exclude work --exclude '.nextflow*' --exclude somatic --exclude docs/slides --exclude tests/data)
mkdir -p "$DEST/afla" "$DEST/afla-somatic"
rsync -a --delete "${EXCL[@]}" "$REPO/" "$DEST/afla/"
rsync -a --delete "${EXCL[@]}" "$REPO/" "$DEST/afla-somatic/"
cp "$REPO/somatic/mode.config" "$DEST/afla-somatic/conf/mode.config"
cp "$REPO/somatic/nextflow_schema.json" "$DEST/afla-somatic/nextflow_schema.json"
cp "$REPO/somatic/output_definition.json" "$DEST/afla-somatic/output_definition.json"
for d in afla afla-somatic; do (cd "$DEST/$d" && git config core.filemode false 2>/dev/null || true); done
echo "Installed: $DEST/afla (germline) and $DEST/afla-somatic (somatic). Restart EPI2ME Desktop to see changes."
