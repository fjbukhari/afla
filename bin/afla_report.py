#!/usr/bin/env python3
"""AFLA report (education and research use only, not for clinical use).

  afla_report.py summarise --sample UNIT --vcf UNIT.annotated.vcf.gz --qc <qc files...> --extra <cnv/sv/msi/roh...>
                           --case case.json [--targets bed] [--constraint f] [--clinvar-index f] [--hpo-dir d]
                           [--civic-dir d] [--cosmic f] [--gene-list-file f] [--panelapp-dir d] [--refflat f]
                           --out UNIT.summary.json
  afla_report.py html --summaries *.summary.json --meta meta.json --out afla-report.html

A "unit" is one sample, one family (joint VCF of a trio) or one tumour. Only the Python standard library is
used, so it runs in a plain Python 3 container.
"""
import argparse
import base64
import csv
import gzip
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afla_acmg  # noqa: E402
import afla_somatic  # noqa: E402

CSQ_WANTED = {
    "SYMBOL", "Gene", "Feature", "MANE_SELECT", "BIOTYPE", "Consequence", "IMPACT", "EXON", "INTRON",
    "HGVSc", "HGVSp", "Existing_variation", "gnomADe_AF", "gnomADg_AF", "MAX_AF", "MAX_AF_POPS",
    "CLIN_SIG", "SIFT", "PolyPhen", "REVEL", "am_class", "am_pathogenicity", "VARIANT_CLASS", "PUBMED",
    "ClinVar", "ClinVar_CLNSIG", "ClinVar_CLNREVSTAT", "ClinVar_CLNDN", "ClinVar_CLNSIGCONF", "ClinVar_ONC",
    "ClinVar_ONCDN", "ClinVar_SCI", "ClinVar_SCIDN", "gnomAD_AF", "gnomAD_AF_grpmax", "gnomAD_nhomalt",
    "COSMIC", "COSMIC_CNT", "SpliceAI_pred_DS_AG", "SpliceAI_pred_DS_AL", "SpliceAI_pred_DS_DG", "SpliceAI_pred_DS_DL",
}
STARS = {"practice guideline": 4, "reviewed by expert panel": 3, "criteria provided, multiple submitters, no conflicts": 2,
         "criteria provided, conflicting classifications": 1, "criteria provided, conflicting interpretations": 1,
         "criteria provided, single submitter": 1}


def opener(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def clean(x):
    return (x or "").replace("_", " ").replace("%3D", "=").replace("%2C", ",")


# ---------------------------------------------------------------- QC parsers
def parse_fastp(path):
    d = json.load(open(path))
    b, a = d["summary"]["before_filtering"], d["summary"]["after_filtering"]
    return {
        "reads_before": b["total_reads"], "reads_after": a["total_reads"],
        "bases_before": b["total_bases"], "q30_before": b["q30_rate"], "q30_after": a["q30_rate"],
        "read1_len_before": b.get("read1_mean_length"), "read1_len_after": a.get("read1_mean_length"),
        "gc": a.get("gc_content"), "dup_rate_fastp": d.get("duplication", {}).get("rate"),
        "adapter_trimmed_reads": d.get("adapter_cutting", {}).get("adapter_trimmed_reads"),
        "insert_size_peak": d.get("insert_size", {}).get("peak"),
    }


def parse_flagstat(path):
    out = {}
    for line in open(path):
        n = int(line.split(" ")[0])
        if " in total" in line:
            out["total"] = n
        elif " primary mapped" in line:
            out["primary_mapped"] = n
        elif " mapped (" in line and "mapped" not in out:
            out["mapped"] = n
        elif "properly paired" in line:
            out["properly_paired"] = n
        elif " primary duplicates" in line:
            out["primary_duplicates"] = n
        elif " duplicates" in line and "duplicates" not in out:
            out["duplicates"] = n
        elif " primary" in line and "primary" not in out and "mapped" not in line and "dup" not in line:
            out["primary"] = n
        elif "paired in sequencing" in line:
            out["paired"] = n
    tot = out.get("primary") or out.get("total") or 0
    if tot:
        out["pct_mapped"] = 100.0 * out.get("primary_mapped", out.get("mapped", 0)) / tot
        dups = out.get("primary_duplicates", out.get("duplicates", 0))
        out["pct_duplicates"] = 100.0 * dups / tot
    if out.get("paired"):
        out["pct_properly_paired"] = 100.0 * out.get("properly_paired", 0) / out["paired"]
    return out


def parse_mosdepth(summary, thresholds, regions):
    out = {}
    for line in open(summary):
        f = line.rstrip("\n").split("\t")
        if f[0] == "total_region":
            out["target_bases"] = int(f[1])
            out["mean_depth"] = float(f[3])
    with gzip.open(thresholds, "rt") as fh:
        header = fh.readline().lstrip("#").split()
        cols = header[4:]
        sums = [0] * len(cols)
        total = 0
        for line in fh:
            f = line.split("\t")
            total += int(f[2]) - int(f[1])
            for i, v in enumerate(f[4:]):
                sums[i] += int(v)
    out["pct_at"] = {c: (100.0 * s / total if total else 0.0) for c, s in zip(cols, sums)}
    low, depths = [], []
    with gzip.open(regions, "rt") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            depth = float(f[-1])
            depths.append(depth)
            if depth < 20:
                low.append([f[0], int(f[1]), int(f[2]), round(depth, 1)])
    out["n_regions"] = len(depths)
    out["low_regions"] = sorted(low, key=lambda r: r[3])[:200]
    out["n_low_regions"] = len(low)
    if depths:
        mean = sum(depths) / len(depths)
        out["uniformity_pct_02x_mean"] = round(100.0 * sum(1 for d in depths if d >= 0.2 * mean) / len(depths), 1)
    return out


def parse_umi(path):
    """fgbio family size histogram -> summary."""
    rows = list(csv.DictReader(open(path), delimiter="\t"))
    fams = sum(int(r["count"]) for r in rows)
    reads = sum(int(r["family_size"]) * int(r["count"]) for r in rows)
    single = sum(int(r["count"]) for r in rows if r["family_size"] == "1")
    return {"families": fams, "reads": reads, "mean_family_size": round(reads / fams, 2) if fams else None,
            "pct_singletons": round(100.0 * single / fams, 1) if fams else None,
            "histogram": [[int(r["family_size"]), int(r["count"])] for r in rows[:30]]}


def parse_primerclip(stats, counts):
    out = {}
    if stats:
        for line in open(stats):
            k, _, v = line.partition(":")
            v = v.strip()
            if v.replace(".", "", 1).isdigit():
                out[k.strip().lower().replace(" ", "_")] = float(v) if "." in v else int(v)
    if counts:
        vals = []
        for line in open(counts):
            f = line.rstrip("\n").split("\t")
            if len(f) >= 4 and not line.startswith(("track", "#")):
                vals.append(num(f[-1]) or 0)
        if vals:
            mean = sum(vals) / len(vals)
            out["primers"] = len(vals)
            out["primers_zero"] = sum(1 for x in vals if x == 0)
            out["primer_uniformity_pct"] = round(100.0 * sum(1 for x in vals if x >= 0.2 * mean) / len(vals), 1)
    return out


# ---------------------------------------------------------------- VCF
def parse_vcf(path, roles):
    """Variants of a single sample, a family (joint VCF) or a tumour. roles: {sample: role}."""
    csq_fields, rows = [], []
    samples = []
    with opener(path) as fh:
        for line in fh:
            if line.startswith("##INFO=<ID=CSQ"):
                m = re.search(r"Format: ([^\"]+)", line)
                csq_fields = m.group(1).split("|") if m else []
                continue
            if line.startswith("#CHROM"):
                samples = line.rstrip("\n").split("\t")[9:]
                continue
            if line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            chrom, pos, vid, ref, alt, qual, filt, info = f[:8]
            fmt = f[8].split(":") if len(f) > 9 else []
            gts = {}
            for s, col in zip(samples, f[9:]):
                d = dict(zip(fmt, col.split(":")))
                ad = [num(x) for x in d.get("AD", "").split(",")] if d.get("AD") not in (None, "", ".") else []
                vaf = None
                if len(ad) >= 2 and all(x is not None for x in ad) and sum(ad) > 0:
                    vaf = ad[1] / sum(ad)
                elif d.get("AF") not in (None, "", "."):
                    vaf = num(d["AF"].split(",")[0])
                elif d.get("VAF") not in (None, "", "."):
                    vaf = num(d["VAF"].split(",")[0])
                gts[s] = {"gt": d.get("GT", "."), "dp": num(d.get("DP")) if d.get("DP") not in (None, ".") else (sum(ad) if ad and None not in ad else None),
                          "gq": num(d.get("GQ")), "vaf": round(vaf, 3) if vaf is not None else None,
                          "alt_reads": ad[1] if len(ad) >= 2 else None}
            csq = {}
            for kv in info.split(";"):
                if kv.startswith("CSQ="):
                    first = kv[4:].split(",")[0].split("|")
                    csq = {k: v for k, v in zip(csq_fields, first) if k in CSQ_WANTED and v != ""}
            sai = [num(csq.get(k)) for k in ("SpliceAI_pred_DS_AG", "SpliceAI_pred_DS_AL", "SpliceAI_pred_DS_DG", "SpliceAI_pred_DS_DL")]
            sai = [x for x in sai if x is not None]
            rev = clean(csq.get("ClinVar_CLNREVSTAT", "")).replace("&", ", ")
            rows.append({
                "chrom": chrom, "pos": int(pos), "ref": ref, "alt": alt, "id": vid, "qual": num(qual), "filter": filt,
                "samples": gts,
                "gene": csq.get("SYMBOL", ""), "transcript": csq.get("Feature", ""), "mane": csq.get("MANE_SELECT", ""),
                "consequence": csq.get("Consequence", ""), "impact": csq.get("IMPACT", ""), "exon": csq.get("EXON", ""),
                "intron": csq.get("INTRON", ""), "biotype": csq.get("BIOTYPE", ""),
                "hgvsc": clean(csq.get("HGVSc", "")).split(":")[-1], "hgvsp": clean(csq.get("HGVSp", "")).split(":")[-1],
                "gnomade": num(csq.get("gnomADe_AF")), "gnomadg": num(csq.get("gnomADg_AF")),
                "gnomad_af": num(csq.get("gnomAD_AF")), "gnomad_grpmax": num(csq.get("gnomAD_AF_grpmax")),
                "gnomad_nhomalt": num(csq.get("gnomAD_nhomalt")),
                "max_af": num(csq.get("MAX_AF")), "max_af_pops": csq.get("MAX_AF_POPS", ""),
                "clinvar": clean(csq.get("ClinVar_CLNSIG", "")).replace("&", ", "), "clinvar_status": rev,
                "clinvar_stars": STARS.get(rev.lower(), 0) if rev else None,
                "clinvar_disease": clean(csq.get("ClinVar_CLNDN", "")).replace("&", ", ").replace("|", "; "),
                "clinvar_conf": clean(csq.get("ClinVar_CLNSIGCONF", "")), "clinvar_id": csq.get("ClinVar", ""),
                "clinvar_onc": clean(csq.get("ClinVar_ONC", "")), "clinvar_onc_disease": clean(csq.get("ClinVar_ONCDN", "")),
                "clin_sig_cache": csq.get("CLIN_SIG", ""),
                "revel": num(csq.get("REVEL")), "am_class": csq.get("am_class", ""), "am_score": num(csq.get("am_pathogenicity")),
                "spliceai": max(sai) if sai else None,
                "sift": csq.get("SIFT", ""), "polyphen": csq.get("PolyPhen", ""),
                "existing": csq.get("Existing_variation", ""), "vclass": csq.get("VARIANT_CLASS", ""),
                "cosmic_id": csq.get("COSMIC", ""), "cosmic_count": num(csq.get("COSMIC_CNT")),
            })
    return samples, csq_fields, rows


def main_sample(samples, roles, unit):
    for s in samples:
        if roles.get(s, {}).get("role") in ("proband", "affected", "tumour", "tumor"):
            return s
    if unit in samples:
        return unit
    return samples[0] if samples else unit


def family_roles(samples, info, proband):
    """{'mother': name, 'father': name} from the sample sheet/PED."""
    p = info.get(proband, {})
    out = {}
    for s in samples:
        r = info.get(s, {}).get("role", "")
        if s == p.get("mother") or r == "mother":
            out["mother"] = s
        elif s == p.get("father") or r == "father":
            out["father"] = s
    return out


def is_het(gt):
    return gt.replace("|", "/") in ("0/1", "1/0")


def is_hom_alt(gt):
    return gt.replace("|", "/") in ("1/1", "1")


def is_ref(gt):
    return gt.replace("|", "/") in ("0/0", "0")


def inheritance(rows, proband, fam, sex, min_dp, min_gq, chrx=("chrX", "X")):
    """Adds v['inheritance'] and compound-het partners (family VCF or single sample)."""
    mo, fa = fam.get("mother"), fam.get("father")
    ok = lambda g: g and (g.get("dp") or 0) >= min_dp and (g.get("gq") is None or g["gq"] >= min_gq)
    by_gene = {}
    for v in rows:
        p = v["samples"].get(proband, {})
        gt = p.get("gt", ".")
        m, f = v["samples"].get(mo) if mo else None, v["samples"].get(fa) if fa else None
        tags = []
        if is_het(gt) and m and f and is_ref(m["gt"]) and is_ref(f["gt"]) and ok(m) and ok(f) and ok(p) and v["filter"] in ("PASS", ".") \
                and (m.get("alt_reads") or 0) <= 1 and (f.get("alt_reads") or 0) <= 1:
            # a true constitutional de novo variant is in ~50% of the child's reads
            tags.append("de novo" if (p.get("vaf") or 0) >= 0.25 else "possible de novo (low allele fraction: artefact or mosaic?)")
        if is_hom_alt(gt):
            if v["chrom"] in chrx and sex == "male":
                tags.append("hemizygous (X-linked)")
            else:
                tags.append("homozygous")
        if is_het(gt) and v["chrom"] in chrx and sex == "male":
            tags.append("hemizygous (X-linked)")
        src = None
        if is_het(gt) and m and f:
            if not is_ref(m["gt"]) and m["gt"] not in (".", "./.") and is_ref(f["gt"]):
                src = "mother"
            elif not is_ref(f["gt"]) and f["gt"] not in (".", "./.") and is_ref(m["gt"]):
                src = "father"
            if src:
                tags.append(f"inherited from {src}")
        v["inheritance"] = ", ".join(tags)
        rare = (afla_acmg.pop_af(v) or 0) <= 0.01 and v["filter"] in ("PASS", ".") and v["impact"] in ("HIGH", "MODERATE")
        if is_het(gt) and rare and v["gene"]:
            by_gene.setdefault(v["gene"], []).append((v, src))
    for gene, lst in by_gene.items():
        if len(lst) < 2:
            continue
        if mo and fa:
            moms = [v for v, s in lst if s == "mother"]
            dads = [v for v, s in lst if s == "father"]
            if moms and dads:
                for v, s in lst:
                    if s in ("mother", "father"):
                        partners = dads if s == "mother" else moms
                        v["inheritance"] = (v["inheritance"] + ", " if v["inheritance"] else "") + "compound heterozygous (in trans)"
                        v["partners"] = [f"{x['gene']} {x['hgvsc']}" for x in partners][:5]
                        plp = [x for x in partners if re.search(r"pathogenic", x["clinvar"], re.I) and not re.search(r"conflict|benign", x["clinvar"], re.I)]
                        if plp:
                            v["partner_plp"] = f"{plp[0]['hgvsc']} (ClinVar {plp[0]['clinvar']})"
        else:
            for v, _s in lst:
                v["inheritance"] = (v["inheritance"] + ", " if v["inheritance"] else "") + "possible compound heterozygous (phase unknown)"
                v["partners"] = [f"{x['gene']} {x['hgvsc']}" for x, _ in lst if x is not v][:5]


# ---------------------------------------------------------------- CNV, SV, ROH, MSI
def parse_cns(path):
    rows = list(csv.DictReader(open(path), delimiter="\t"))
    out = []
    for r in rows:
        cn = int(float(r["cn"])) if r.get("cn") not in (None, "") else None
        log2 = float(r["log2"])
        genes = sorted({g for g in (r.get("gene") or "").split(",") if g and g not in ("-", "Antitarget")})
        out.append({"chrom": r["chromosome"], "start": int(r["start"]), "end": int(r["end"]), "log2": round(log2, 3),
                    "cn": cn, "probes": int(float(r.get("probes") or 0)), "genes": genes[:60], "n_genes": len(genes)})
    return out


def cnv_genes_from_cnr(cnr, segs):
    """Gene names from the bins of each segment (CNVkit keeps gene names per bin in the .cnr)."""
    bins = {}
    for r in csv.DictReader(open(cnr), delimiter="\t"):
        bins.setdefault(r["chromosome"], []).append((int(r["start"]), int(r["end"]), r.get("gene", "")))
    for s in segs:
        genes = []
        for a, b, g in bins.get(s["chrom"], []):
            if a < s["end"] and b > s["start"]:
                for x in g.split(","):
                    if x and x not in ("-", "Antitarget") and x not in genes:
                        genes.append(x)
        s["genes"], s["n_genes"] = genes[:60], len(genes)
    return segs


def parse_sv(path, sample=""):
    """Manta VCF (VEP-annotated or not) -> list of SVs; BND pairs joined into fusion candidates."""
    csq_fields, recs = [], {}
    order = []
    with opener(path) as fh:
        for line in fh:
            if line.startswith("##INFO=<ID=CSQ"):
                m = re.search(r"Format: ([^\"]+)", line)
                csq_fields = m.group(1).split("|") if m else []
                continue
            if line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            info = dict(kv.split("=", 1) if "=" in kv else (kv, True) for kv in f[7].split(";"))
            genes = []
            if "CSQ" in info:
                for c in info["CSQ"].split(","):
                    d = dict(zip(csq_fields, c.split("|")))
                    if d.get("SYMBOL") and d["SYMBOL"] not in genes:
                        genes.append(d["SYMBOL"])
            fmt = f[8].split(":") if len(f) > 9 else []
            sup = []
            for col in f[9:]:
                d = dict(zip(fmt, col.split(":")))
                pr = [num(x) or 0 for x in d.get("PR", "0,0").split(",")]
                sr = [num(x) or 0 for x in d.get("SR", "0,0").split(",")]
                sup.append({"alt_pairs": int(pr[1]) if len(pr) > 1 else 0, "alt_split": int(sr[1]) if len(sr) > 1 else 0,
                            "ref_pairs": int(pr[0]), "ref_split": int(sr[0])})
            r = {"sample": sample, "id": f[2], "chrom": f[0], "pos": int(f[1]), "alt": f[4], "filter": f[6], "type": info.get("SVTYPE", ""),
                 "end": num(info.get("END")), "len": num(info.get("SVLEN")), "mate": info.get("MATEID"), "genes": genes[:20],
                 "support": sup[-1] if sup else {}, "imprecise": "IMPRECISE" in info}
            recs[f[2]] = r
            order.append(f[2])
    out, seen = [], set()
    for i in order:
        r = recs[i]
        if i in seen:
            continue
        seen.add(i)
        if r["type"] == "BND" and r["mate"] in recs:
            m = recs[r["mate"]]
            seen.add(r["mate"])
            g1, g2 = r["genes"], m["genes"]
            r["partner"] = f"{m['chrom']}:{m['pos']}"
            r["genes"] = sorted(set(g1 + g2))
            if g1 and g2 and set(g1) != set(g2):
                r["fusion"] = f"{g1[0]}::{g2[0]}"
        out.append(r)
    return out


def parse_roh(path):
    out = []
    for line in open(path):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 8 and f[0] == "RG":
            out.append({"sample": f[1], "chrom": f[2], "start": int(f[3]), "end": int(f[4]), "length": int(float(f[5])),
                        "markers": int(float(f[6])), "quality": num(f[7])})
    return out


def png_data(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def read_gene_list(text=None, path=None):
    genes = []
    src = []
    if path:
        src = open(path, encoding="utf-8", errors="replace").read().splitlines()
        if src and "\t" in src[0]:
            head = src[0].split("\t")
            col = next((i for i, h in enumerate(head) if h.lower() in ("gene symbol", "gene_symbol", "gene", "symbol", "entity_name")), 0)
            src = [l.split("\t")[col] for l in src[1:] if l.strip()]
    if text:
        src += re.split(r"[\s,;]+", text)
    for g in src:
        g = g.strip().upper()
        if g and not g.startswith("#") and g not in genes:
            genes.append(g)
    return genes


def load_panelapp(d):
    """{panel name: [green genes]} from TSVs written by scripts/afla-setup.sh (panelapp/*.tsv)."""
    out = {}
    if not d:
        return out
    for p in sorted(Path(d).glob("*.tsv")):
        rows = list(csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"))
        for r in rows:
            name = r.get("panel") or p.stem
            if r.get("confidence", "3") in ("3", "green", "Green"):
                out.setdefault(name, []).append(r.get("gene"))
    return out


# ---------------------------------------------------------------- summarise
def summarise(a):
    case = json.load(open(a.case)) if a.case else {}
    info = case.get("samples") or {}
    somatic = case.get("mode") == "somatic"
    s = {"sample": a.sample, "qc": {}, "mode": case.get("mode", "germline")}
    files = [Path(p) for p in (a.qc or []) + (a.extra or []) if p and Path(p).exists() and Path(p).is_file()]

    # QC per sequenced sample (a family unit has several)
    def qc_for(prefix):
        q = {}
        by = lambda suffix: next((p for p in files if p.name == prefix + suffix), None)
        if by(".fastp.json"):
            q["fastp"] = parse_fastp(by(".fastp.json"))
        if by(".flagstat.txt"):
            q["flagstat"] = parse_flagstat(by(".flagstat.txt"))
        if by(".mosdepth.summary.txt") and by(".thresholds.bed.gz") and by(".regions.bed.gz"):
            q["coverage"] = parse_mosdepth(by(".mosdepth.summary.txt"), by(".thresholds.bed.gz"), by(".regions.bed.gz"))
        if by(".umi_family_sizes.txt"):
            q["umi"] = parse_umi(by(".umi_family_sizes.txt"))
        if by(".primerclip.txt") or by(".primer_counts.bedgraph"):
            q["primers"] = parse_primerclip(by(".primerclip.txt"), by(".primer_counts.bedgraph"))
        return q
    prefixes = sorted({p.name.split(".")[0] for p in files if p.name.endswith((".flagstat.txt", ".fastp.json", ".mosdepth.summary.txt"))})
    s["qc_by_sample"] = {p: qc_for(p) for p in prefixes}
    samples = []
    rows = []
    if a.vcf and Path(a.vcf).exists():
        samples, csq_fields, rows = parse_vcf(a.vcf, info)
        s["annotated"] = bool(csq_fields)
    s["vcf_samples"] = samples
    main = main_sample(samples, info, a.sample) if samples else a.sample
    s["main_sample"] = main
    s["qc"] = s["qc_by_sample"].get(main) or (next(iter(s["qc_by_sample"].values())) if s["qc_by_sample"] else {})
    s["role"] = info.get(main, {}).get("role", "")
    s["sex"] = info.get(main, {}).get("sex", "")

    # knowledge
    genes = {v["gene"] for v in rows if v["gene"]}
    constraint = afla_acmg.load_constraint(a.constraint) if a.constraint else {}
    cv_index = afla_acmg.load_clinvar_index(a.clinvar_index, genes) if a.clinvar_index else {}
    s["knowledge"] = {"constraint": bool(constraint), "clinvar_index": bool(cv_index), "hpo": False, "civic": False, "cosmic": False}

    # family / inheritance
    fam = family_roles(samples, info, main)
    s["family"] = {"members": samples, "proband": main, **fam}
    if rows and not somatic:
        inheritance(rows, main, fam, s["sex"], case.get("min_dp") or 10, case.get("min_gq") or 20)

    # stats on the main sample
    stats = {"total": 0, "pass": 0, "snv": 0, "indel": 0, "ti": 0, "tv": 0, "het": 0, "hom": 0, "spectrum": {}}
    comp = {"A": "T", "C": "G", "G": "C", "T": "A"}
    purines = {"A", "G"}
    variants = []
    for v in rows:
        g = v["samples"].get(main, {})
        gt = g.get("gt", ".")
        if gt.replace("|", "/") in ("0/0", "./.", ".", "0") and not somatic:
            continue   # family VCF: variants the proband does not carry are not listed
        v.update({"gt": gt, "dp": g.get("dp"), "gq": g.get("gq"), "vaf": g.get("vaf")})
        if not somatic and len(samples) > 1 and is_het(gt) and v["filter"] in ("PASS", ".") \
                and g.get("vaf") is not None and g["vaf"] < (case.get("min_het_vaf") or 0.2):
            v["filter"] = "LowVAF"   # family VCF: the site filter cannot judge each member, so label the proband's call here
        stats["total"] += 1
        passed = v["filter"] in ("PASS", ".")
        is_snv = len(v["ref"]) == 1 and len(v["alt"]) == 1
        if passed:
            stats["pass"] += 1
            stats["snv" if is_snv else "indel"] += 1
            if is_snv:
                r, al = v["ref"], v["alt"]
                stats["ti" if ((r in purines) == (al in purines)) else "tv"] += 1
                rr, aa = (comp.get(r, r), comp.get(al, al)) if r in purines else (r, al)
                stats["spectrum"][f"{rr}>{aa}"] = stats["spectrum"].get(f"{rr}>{aa}", 0) + 1
            if is_het(gt):
                stats["het"] += 1
            elif is_hom_alt(gt):
                stats["hom"] += 1
        variants.append(v)
    stats["titv"] = round(stats["ti"] / stats["tv"], 2) if stats["tv"] else None
    stats["het_hom"] = round(stats["het"] / stats["hom"], 2) if stats["hom"] else None

    # keep the report light: very large VCFs lose common, non-coding, non-ClinVar variants
    dropped = 0
    if len(variants) > 60000:
        keep = []
        for v in variants:
            af = afla_acmg.pop_af(v)
            if v["impact"] == "MODIFIER" and not v["clinvar"] and af is not None and af > 0.01 and (v["spliceai"] or 0) < 0.1:
                dropped += 1
                continue
            keep.append(v)
        variants = keep
    stats["dropped_common_modifier"] = dropped
    s["stats"] = stats if rows else None

    # ROH: flag homozygous variants inside runs of homozygosity
    roh = []
    for p in files:
        if p.name.endswith(".roh.txt"):
            roh += parse_roh(p)
    s["roh"] = {"segments": [r for r in roh if r["length"] >= 500000], "total_mb": {}}
    for r in roh:
        if r["length"] >= 1500000:
            s["roh"]["total_mb"][r["sample"]] = round(s["roh"]["total_mb"].get(r["sample"], 0) + r["length"] / 1e6, 1)
    main_roh = [r for r in roh if r["sample"] == main and r["length"] >= 1000000]
    for v in variants:
        if any(r["chrom"] == v["chrom"] and r["start"] <= v["pos"] <= r["end"] for r in main_roh):
            v["in_roh"] = True

    # phenotype
    hpo_text = " ".join(filter(None, [case.get("hpo_terms"), info.get(main, {}).get("hpo", "")]))
    s["hpo"] = {"terms": [], "genes": {}}
    if a.hpo_dir and hpo_text.strip() and not somatic:
        import afla_hpo
        h = afla_hpo.HPO(a.hpo_dir)
        terms = h.parse_terms(hpo_text)
        cand = {v["gene"] for v in variants if v["gene"] and v["impact"] in ("HIGH", "MODERATE", "LOW")}
        s["hpo"] = {"terms": [[t, h.names.get(t, t)] for t in terms], "genes": h.rank(cand, terms)}
        s["knowledge"]["hpo"] = True
    elif a.hpo_dir and not somatic:
        s["knowledge"]["hpo"] = True

    # gene lists / panels
    s["gene_list"] = read_gene_list(case.get("gene_list"), a.gene_list_file)
    s["panels"] = load_panelapp(a.panelapp_dir) if a.panelapp_dir else {}

    # ACMG (germline) or tiers (somatic)
    if somatic:
        civic = afla_somatic.load_civic(a.civic_dir, genes) if a.civic_dir else {}
        cosmic = afla_somatic.load_cosmic(a.cosmic, genes) if a.cosmic else {}
        s["knowledge"]["civic"], s["knowledge"]["cosmic"] = bool(civic), bool(cosmic)
        s["oncokb"] = afla_somatic.oncokb([v for v in variants if v["impact"] in ("HIGH", "MODERATE")],
                                          case.get("oncokb_token_value"), case.get("tumour_type"))
        for v in variants:
            v["civic"] = afla_somatic.civic_match(v, civic)
            if cosmic and v["hgvsp"]:
                c = cosmic.get((v["gene"], "p." + afla_acmg.one_letter(v["hgvsp"])))
                if c:
                    v["cosmic_count"] = (v.get("cosmic_count") or 0) + c["count"]
                    v["cosmic_tier"] = c["tier"]
            v["tier"], v["tier_reason"] = afla_somatic.tier(v, case.get("tumour_type"))
        mb, what = afla_somatic.coding_mb(a.targets, a.refflat)
        s["tmb"] = afla_somatic.tmb(variants, mb, case.get("tmb_min_vaf") or 0.05, case.get("min_dp") or 50)
        if s["tmb"]:
            s["tmb"]["denominator"] = what
        msi = [p for p in files if p.name.endswith(".msi.txt")]
        s["msi"] = afla_somatic.parse_msi(msi[0]) if msi else None
    else:
        for v in variants:
            ctx = {"inheritance": v.get("inheritance", ""), "partner_plp": v.get("partner_plp")}
            v["acmg"] = afla_acmg.evaluate(v, constraint, cv_index, ctx)
            v["acmg_points"], v["acmg_class"] = afla_acmg.classify(v["acmg"])
            gc = constraint.get(v["gene"])
            if gc:
                v["loeuf"], v["mis_z"] = gc.get("loeuf"), gc.get("mis_z")
    for v in variants:
        if not somatic and s["hpo"]["genes"].get(v["gene"]):
            v["hpo_score"] = s["hpo"]["genes"][v["gene"]]["score"]
        v.pop("samples", None) if len(samples) <= 1 else None
    s["variants"] = variants if rows else None

    # CNV (per sequenced sample)
    s["cnv"] = {}
    for p in files:
        if p.name.endswith(".call.cns"):
            smp = p.name[:-len(".call.cns")]
            segs = parse_cns(p)
            cnr = next((x for x in files if x.name == smp + ".cnr"), None)
            if cnr:
                segs = cnv_genes_from_cnr(cnr, segs)
            png = next((x for x in files if x.name == smp + ".cnv_scatter.png"), None)
            inf = next((x for x in files if x.name == smp + ".cnv_info.txt"), None)
            s["cnv"][smp] = {"segments": segs, "plot": png_data(png) if png else None,
                             "reference": open(inf).read().strip().split("=")[-1] if inf else ""}
            if somatic and a.civic_dir:
                seg_genes = {g for seg in segs if abs(seg["log2"]) >= 0.7 for g in seg["genes"]}
                civ = afla_somatic.load_civic(a.civic_dir, seg_genes) if seg_genes else {}
                for seg in segs:
                    if abs(seg["log2"]) < 0.7:
                        continue
                    want = ("AMPLIFICATION", "OVEREXPRESSION") if seg["log2"] > 0 else ("DELETION", "LOSS", "LOSS-OF-FUNCTION")
                    seg["civic"] = [dict(e, match="gene-level copy number") for g in seg["genes"] for e in civ.get(g, [])
                                    if any(w in e["variant"].upper() for w in want)][:10]
    # SV
    s["sv"] = []
    for p in files:
        if p.name.endswith(".sv.annotated.vcf.gz") or (p.name.endswith(".sv.vcf.gz") and not any(x.name.endswith(".sv.annotated.vcf.gz") for x in files)):
            s["sv"] += parse_sv(p, p.name.split(".sv.")[0])
    json.dump(s, open(a.out, "w"), separators=(",", ":"))


# ---------------------------------------------------------------- HTML
def build_html(a):
    samples = [json.load(open(p)) for p in sorted(a.summaries)]
    meta = json.load(open(a.meta)) if a.meta else {}
    data = json.dumps({"samples": samples, "meta": meta}, separators=(",", ":")).replace("</", "<\\/")
    tpl = (Path(__file__).resolve().parent / "afla_report_template.html").read_text()
    Path(a.out).write_text(tpl.replace("__AFLA_DATA__", data).replace("__TITLE__", html.escape(meta.get("title", "AFLA report"))))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summarise")
    s.add_argument("--sample", required=True)
    s.add_argument("--vcf")
    s.add_argument("--qc", nargs="*", default=[])
    s.add_argument("--extra", nargs="*", default=[])
    s.add_argument("--case")
    s.add_argument("--targets")
    s.add_argument("--constraint")
    s.add_argument("--clinvar-index")
    s.add_argument("--hpo-dir")
    s.add_argument("--civic-dir")
    s.add_argument("--cosmic")
    s.add_argument("--gene-list-file")
    s.add_argument("--panelapp-dir")
    s.add_argument("--refflat")
    s.add_argument("--out", required=True)
    h = sub.add_parser("html")
    h.add_argument("--summaries", nargs="+", required=True)
    h.add_argument("--meta")
    h.add_argument("--out", required=True)
    a = p.parse_args()
    summarise(a) if a.cmd == "summarise" else build_html(a)


if __name__ == "__main__":
    sys.exit(main())
