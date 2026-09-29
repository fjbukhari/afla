#!/usr/bin/env python3
"""AFLA germline report (education and research use only, not for clinical use).

  afla_report.py summarise --sample S --vcf S.annotated.vcf.gz --qc <qc files...> --out S.summary.json
  afla_report.py html --summaries *.summary.json --meta meta.json --out afla-report.html

Only the Python standard library is used, so it runs in a plain Python 3 container.
"""
import argparse
import gzip
import html
import json
import re
import sys
from pathlib import Path

CSQ_WANTED = [
    "SYMBOL", "Gene", "Feature", "MANE_SELECT", "BIOTYPE", "Consequence", "IMPACT", "EXON", "INTRON",
    "HGVSc", "HGVSp", "Existing_variation", "gnomADe_AF", "gnomADg_AF", "MAX_AF", "MAX_AF_POPS",
    "CLIN_SIG", "SIFT", "PolyPhen", "REVEL", "am_class", "am_pathogenicity",
    "ClinVar", "ClinVar_CLNSIG", "ClinVar_CLNREVSTAT", "ClinVar_CLNDN", "PUBMED", "VARIANT_CLASS",
]


def opener(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


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
    low = []
    with gzip.open(regions, "rt") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            depth = float(f[-1])
            if depth < 20:
                low.append([f[0], int(f[1]), int(f[2]), round(depth, 1)])
    out["n_regions"] = sum(1 for _ in gzip.open(regions, "rt"))
    out["low_regions"] = sorted(low, key=lambda r: r[3])[:200]
    out["n_low_regions"] = len(low)
    return out


# ---------------------------------------------------------------- VCF
def parse_vcf(path):
    csq_fields, variants = [], []
    stats = {"total": 0, "pass": 0, "snv": 0, "indel": 0, "ti": 0, "tv": 0, "het": 0, "hom": 0}
    purines = {"A", "G"}
    with opener(path) as fh:
        for line in fh:
            if line.startswith("##INFO=<ID=CSQ"):
                m = re.search(r"Format: ([^\"]+)", line)
                csq_fields = m.group(1).split("|") if m else []
                continue
            if line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            chrom, pos, vid, ref, alt, qual, filt, info = f[:8]
            fmt = f[8].split(":") if len(f) > 9 else []
            smp = dict(zip(fmt, f[9].split(":"))) if len(f) > 9 else {}
            gt = smp.get("GT", ".")
            ad = [num(x) for x in smp.get("AD", "").split(",")] if smp.get("AD") else []
            dp = num(smp.get("DP"))
            vaf = None
            if len(ad) >= 2 and all(x is not None for x in ad) and sum(ad) > 0:
                vaf = ad[1] / sum(ad)
            elif smp.get("VAF"):
                vaf = num(smp["VAF"].split(",")[0])
            csq = {}
            for kv in info.split(";"):
                if kv.startswith("CSQ="):
                    first = kv[4:].split(",")[0].split("|")
                    csq = {k: v for k, v in zip(csq_fields, first) if k in CSQ_WANTED and v != ""}
            stats["total"] += 1
            passed = filt in ("PASS", ".")
            is_snv = len(ref) == 1 and len(alt) == 1
            if passed:
                stats["pass"] += 1
                stats["snv" if is_snv else "indel"] += 1
                if is_snv:
                    stats["ti" if ((ref in purines) == (alt in purines)) else "tv"] += 1
                g = gt.replace("|", "/")
                if g in ("0/1", "1/0"):
                    stats["het"] += 1
                elif g == "1/1":
                    stats["hom"] += 1
            clin = csq.get("ClinVar_CLNSIG", "")
            variants.append({
                "chrom": chrom, "pos": int(pos), "ref": ref, "alt": alt, "id": vid,
                "qual": num(qual), "filter": filt, "gt": gt, "dp": dp, "gq": num(smp.get("GQ")),
                "vaf": round(vaf, 3) if vaf is not None else None,
                "gene": csq.get("SYMBOL", ""), "transcript": csq.get("Feature", ""),
                "mane": csq.get("MANE_SELECT", ""), "consequence": csq.get("Consequence", ""),
                "impact": csq.get("IMPACT", ""), "exon": csq.get("EXON", ""),
                "hgvsc": csq.get("HGVSc", "").split(":")[-1], "hgvsp": csq.get("HGVSp", "").split(":")[-1].replace("%3D", "="),
                "gnomade": num(csq.get("gnomADe_AF")), "gnomadg": num(csq.get("gnomADg_AF")),
                "max_af": num(csq.get("MAX_AF")), "max_af_pops": csq.get("MAX_AF_POPS", ""),
                "clinvar": clin.replace("_", " "), "clinvar_status": csq.get("ClinVar_CLNREVSTAT", "").replace("_", " "),
                "clinvar_disease": csq.get("ClinVar_CLNDN", "").replace("_", " "),
                "clin_sig_cache": csq.get("CLIN_SIG", ""),
                "revel": num(csq.get("REVEL")), "am_class": csq.get("am_class", ""), "am_score": num(csq.get("am_pathogenicity")),
                "sift": csq.get("SIFT", ""), "polyphen": csq.get("PolyPhen", ""),
                "existing": csq.get("Existing_variation", ""), "vclass": csq.get("VARIANT_CLASS", ""),
            })
    stats["titv"] = round(stats["ti"] / stats["tv"], 2) if stats["tv"] else None
    stats["het_hom"] = round(stats["het"] / stats["hom"], 2) if stats["hom"] else None
    return {"csq_fields": csq_fields, "stats": stats, "variants": variants, "annotated": bool(csq_fields)}


def summarise(a):
    s = {"sample": a.sample, "qc": {}}
    files = [Path(p) for p in (a.qc or []) if p and Path(p).exists()]
    by = lambda suffix: next((p for p in files if p.name.endswith(suffix)), None)
    if by(".fastp.json"):
        s["qc"]["fastp"] = parse_fastp(by(".fastp.json"))
    if by(".flagstat.txt"):
        s["qc"]["flagstat"] = parse_flagstat(by(".flagstat.txt"))
    if by(".mosdepth.summary.txt") and by(".thresholds.bed.gz") and by(".regions.bed.gz"):
        s["qc"]["coverage"] = parse_mosdepth(by(".mosdepth.summary.txt"), by(".thresholds.bed.gz"), by(".regions.bed.gz"))
    if a.vcf and Path(a.vcf).exists():
        s.update(parse_vcf(a.vcf))
    json.dump(s, open(a.out, "w"))


# ---------------------------------------------------------------- HTML
def build_html(a):
    samples = [json.load(open(p)) for p in sorted(a.summaries)]
    meta = json.load(open(a.meta)) if a.meta else {}
    data = json.dumps({"samples": samples, "meta": meta}, separators=(",", ":")).replace("</", "<\\/")
    tpl = (Path(__file__).parent / "afla_report_template.html").read_text()
    Path(a.out).write_text(tpl.replace("__AFLA_DATA__", data).replace("__TITLE__", html.escape(meta.get("title", "AFLA report"))))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summarise")
    s.add_argument("--sample", required=True)
    s.add_argument("--vcf")
    s.add_argument("--qc", nargs="*")
    s.add_argument("--out", required=True)
    h = sub.add_parser("html")
    h.add_argument("--summaries", nargs="+", required=True)
    h.add_argument("--meta")
    h.add_argument("--out", required=True)
    a = p.parse_args()
    summarise(a) if a.cmd == "summarise" else build_html(a)


if __name__ == "__main__":
    sys.exit(main())
