#!/usr/bin/env python3
"""Downloads PanelApp gene panels (Genomics England and Australian Genomics) as TSV files:
   panel, panel_id, version, gene, confidence (3 = green), moi
Usage: python3 scripts/panelapp_download.py OUT_DIR
Only public, open data; used for "virtual panels" in the AFLA report.
"""
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

SOURCES = {
    "england": "https://panelapp.genomicsengland.co.uk/api/v1",
    "australia": "https://panelapp-aus.org/api/v1",
}


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=60) as r:
                return json.load(r)
        except Exception as e:  # network hiccup: retry
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, base in SOURCES.items():
        rows = []
        url = f"{base}/panels/?page=1"
        panels = []
        try:
            while url:
                d = get(url)
                panels += d.get("results", [])
                url = d.get("next")
        except Exception as e:
            print(f"  {name}: panel list failed ({e}); skipped")
            continue
        for i, p in enumerate(panels):
            try:
                d = get(f"{base}/panels/{p['id']}/")
            except Exception as e:
                print(f"  {name}: panel {p.get('name')} failed ({e})")
                continue
            for g in d.get("genes", []):
                sym = (g.get("gene_data") or {}).get("gene_symbol") or g.get("entity_name")
                if sym:
                    rows.append([f"{d.get('name')} v{d.get('version')} ({name})", d.get("id"), d.get("version"), sym,
                                 g.get("confidence_level"), g.get("mode_of_inheritance", "")])
            if i % 25 == 0:
                print(f"  {name}: {i + 1}/{len(panels)} panels")
        with open(out / f"panelapp_{name}.tsv", "w", newline="") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["panel", "panel_id", "version", "gene", "confidence", "moi"])
            w.writerows(rows)
        print(f"  {name}: {len(panels)} panels, {len(rows)} gene entries")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "panelapp")
