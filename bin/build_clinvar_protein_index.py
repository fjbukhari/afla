#!/usr/bin/env python3
"""ClinVar pathogenic/likely pathogenic missense variants (VEP-annotated) -> amino-acid index for ACMG PS1/PM5.
   build_clinvar_protein_index.py plp_missense.vep.vcf clinvar_protein_index.tsv.gz
Columns: gene, pos, ref_aa, alt_aa, hgvsp, clinvar_id, significance, stars
"""
import gzip
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from afla_acmg import protein_change  # noqa: E402

STARS = {"practice_guideline": 4, "reviewed_by_expert_panel": 3, "criteria_provided,_multiple_submitters,_no_conflicts": 2,
         "criteria_provided,_single_submitter": 1, "criteria_provided,_conflicting_classifications": 1}


def main(inp, out):
    fields = []
    n = 0
    op = gzip.open if inp.endswith(".gz") else open
    with op(inp, "rt") as fh, gzip.open(out, "wt") as o:
        o.write("gene\tpos\tref_aa\talt_aa\thgvsp\tclinvar_id\tsignificance\tstars\n")
        for line in fh:
            if line.startswith("##INFO=<ID=CSQ"):
                fields = re.search(r"Format: ([^\"]+)", line).group(1).split("|")
                continue
            if line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            info = dict(kv.split("=", 1) for kv in f[7].split(";") if "=" in kv)
            sig = info.get("CLNSIG", "")
            if not re.match(r"(Pathogenic|Likely_pathogenic|Pathogenic/Likely_pathogenic)$", sig):
                continue
            if "CSQ" not in info:
                continue
            c = dict(zip(fields, info["CSQ"].split(",")[0].split("|")))
            if "missense_variant" not in c.get("Consequence", ""):
                continue
            hgvsp = c.get("HGVSp", "").split(":")[-1].replace("%3D", "=")
            pc = protein_change(hgvsp)
            if not pc or not c.get("SYMBOL"):
                continue
            o.write(f"{c['SYMBOL']}\t{pc[1]}\t{pc[0]}\t{pc[2]}\t{hgvsp}\t{f[2]}\t{sig.replace('_', ' ')}\t{STARS.get(info.get('CLNREVSTAT', ''), 0)}\n")
            n += 1
    print(f"{n} pathogenic/likely pathogenic missense changes written to {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
