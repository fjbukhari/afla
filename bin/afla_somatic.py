"""Somatic evidence and AMP/ASCO/CAP 2017 tier suggestions (teaching aid).

Evidence sources (all optional): CIViC (CC0, nightly TSV), COSMIC (user download under its own licence),
OncoKB (API, free academic token, internet needed), ClinVar somatic classifications (ONC/SCI fields).
Tier suggestion:
  I   : level A/B evidence (CIViC) or OncoKB level 1/2/R1, in the tumour type given
  II  : level A/B in another tumour type, level C/D, OncoKB 3A/3B/4/R2, or a recurrent COSMIC hotspot
  III : no evidence of significance, rare in the population (VUS)
  IV  : common in the population (>= 1%) or ClinVar benign
The tier is a suggestion to review, not a result. Education and research use only.
"""
import csv
import gzip
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from afla_acmg import one_letter, pop_af

TRUNCATING = {"stop_gained", "frameshift_variant", "splice_acceptor_variant", "splice_donor_variant", "start_lost"}
CODING = TRUNCATING | {"missense_variant", "inframe_insertion", "inframe_deletion", "protein_altering_variant", "stop_lost"}


def _open(p):
    return gzip.open(p, "rt", encoding="utf-8", errors="replace") if str(p).endswith(".gz") else open(p, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- CIViC
def load_civic(civic_dir, genes):
    """{gene: [evidence dicts]} from the CIViC nightly ClinicalEvidenceSummaries TSV (old and new column names)."""
    out = {}
    if not civic_dir:
        return out
    files = sorted(Path(civic_dir).glob("*ClinicalEvidenceSummaries*.tsv")) + sorted(Path(civic_dir).glob("*clinical_evidence*.tsv"))
    if not files:
        return out
    with _open(files[-1]) as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        for r in rd:
            if r.get("evidence_status", "accepted") not in ("accepted", ""):
                continue
            if r.get("molecular_profile"):
                mp = r["molecular_profile"]
                if " AND " in mp or " OR " in mp:
                    continue
                gene, _, variant = mp.partition(" ")
            else:
                gene, variant = r.get("gene", ""), r.get("variant", "")
            if genes and gene not in genes:
                continue
            out.setdefault(gene, []).append({
                "variant": variant.strip(), "disease": r.get("disease", ""),
                "therapies": r.get("therapies") or r.get("drugs") or "",
                "type": r.get("evidence_type", ""), "direction": r.get("evidence_direction", ""),
                "level": r.get("evidence_level", ""), "significance": r.get("significance") or r.get("clinical_significance", ""),
                "rating": r.get("rating", ""), "id": r.get("evidence_id", ""),
                "url": r.get("evidence_civic_url") or (f"https://civicdb.org/evidence/{r.get('evidence_id')}" if r.get("evidence_id") else ""),
            })
    return out


def civic_match(v, civic):
    """Evidence items whose CIViC variant name fits this variant (exact change, codon, exon indel, gene-level)."""
    gene = v.get("gene")
    items = civic.get(gene) or []
    if not items:
        return []
    change = one_letter(v.get("hgvsp"))
    codon = re.match(r"([A-Z*])(\d+)", change).group(0) if change else None
    csq = set((v.get("consequence") or "").split("&"))
    exon = (v.get("exon") or "").split("/")[0]
    hits = []
    for e in items:
        name = e["variant"].upper()
        why = None
        if change and re.search(rf"(^|[ (/]){re.escape(change)}($|[ )/,])", name):
            why = "exact"
        elif codon and re.fullmatch(rf"{re.escape(codon)}([A-Z]?|X)?", name.replace(" ", "")):
            why = "codon"
        elif exon and re.search(rf"EXON {exon}\b", name) and (
                ("DELETION" in name and "inframe_deletion" in csq) or ("INSERTION" in name and "inframe_insertion" in csq)
                or ("MUTATION" in name and csq & CODING)):
            why = f"exon {exon}"
        elif name in ("MUTATION", "MUTATIONS") and csq & CODING:
            why = "gene-level (any mutation)"
        elif name in ("LOSS-OF-FUNCTION", "LOSS", "TRUNCATING MUTATION", "FRAMESHIFT MUTATION", "NONSENSE MUTATION") and csq & TRUNCATING:
            why = "gene-level (loss of function)"
        if why:
            hits.append(dict(e, match=why))
    return hits


# ---------------------------------------------------------------- COSMIC (user-provided)
def load_cosmic(path, genes):
    """{(gene, 'p.V600E'): {'count': n, 'tier': t}} from a COSMIC Cancer Mutation Census or mutation export TSV."""
    out = {}
    if not path:
        return out
    with _open(path) as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        cols = rd.fieldnames or []
        gcol = next((c for c in cols if c.upper() in ("GENE_NAME", "GENE NAME", "GENE_SYMBOL", "GENE")), None)
        acol = next((c for c in cols if c.upper().replace(" ", "_") in ("MUTATION_AA", "AA_MUT", "HGVSP", "MUTATION_AA_CHANGE")), None)
        ccol = next((c for c in cols if c.upper() in ("COSMIC_SAMPLE_MUTATED", "COUNT", "SAMPLE_COUNT")), None)
        tcol = next((c for c in cols if c.upper() in ("MUTATION_SIGNIFICANCE_TIER", "TIER")), None)
        if not gcol or not acol:
            return out
        for r in rd:
            g = (r.get(gcol) or "").split("_")[0]
            if genes and g not in genes:
                continue
            aa = r.get(acol) or ""
            if not aa.startswith("p."):
                continue
            k = (g, aa)
            cur = out.setdefault(k, {"count": 0, "tier": ""})
            try:
                cur["count"] += int(r.get(ccol) or 1) if ccol else 1
            except ValueError:
                cur["count"] += 1
            if tcol and r.get(tcol):
                cur["tier"] = r[tcol]
    return out


# ---------------------------------------------------------------- OncoKB (optional, online)
def oncokb(variants, token, tumour_type):
    """Adds v['oncokb'] for coding variants; silently skipped without internet."""
    if not token:
        return "not used"
    done = 0
    for v in variants:
        change = one_letter(v.get("hgvsp"))
        if not v.get("gene") or not change or v.get("filter") not in ("PASS", "."):
            continue
        q = {"hugoSymbol": v["gene"], "alteration": change}
        if tumour_type:
            q["tumorType"] = tumour_type
        req = urllib.request.Request("https://www.oncokb.org/api/v1/annotate/mutations/byProteinChange?" + urllib.parse.urlencode(q),
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
        except Exception as e:  # offline, bad token, rate limit
            return f"failed ({type(e).__name__}); OncoKB evidence not included"
        v["oncokb"] = {
            "oncogenic": d.get("oncogenic"), "effect": (d.get("mutationEffect") or {}).get("knownEffect"),
            "level": d.get("highestSensitiveLevel"), "resistance": d.get("highestResistanceLevel"),
            "drugs": sorted({dr.get("drugName") for t in d.get("treatments", []) for dr in t.get("drugs", [])}),
        }
        done += 1
    return f"queried for {done} variants"


# ---------------------------------------------------------------- tiers
def _disease_match(disease, tumour_type):
    if not tumour_type:
        return None
    a = set(re.findall(r"[a-z]{4,}", disease.lower()))
    b = set(re.findall(r"[a-z]{4,}", tumour_type.lower())) - {"cancer", "carcinoma", "tumour", "tumor", "neoplasm"}
    return bool(a & b)


def tier(v, tumour_type):
    """(tier, reason)"""
    af = pop_af(v)
    clin = (v.get("clinvar") or "").lower()
    if (af is not None and af >= 0.01) or ("benign" in clin and "pathogenic" not in clin and "conflicting" not in clin):
        return "IV", "common in the population (≥1%) or ClinVar benign: likely a germline polymorphism"
    best = None
    for e in v.get("civic") or []:
        lvl = e["level"]
        if e["direction"].lower().startswith("does not"):
            continue
        same = _disease_match(e["disease"], tumour_type)
        if lvl in ("A", "B") and same:
            cand = ("I", f"CIViC level {lvl} {e['type'].lower()} evidence in {e['disease']} ({e['match']} match)")
        elif lvl in ("A", "B"):
            cand = ("II", f"CIViC level {lvl} evidence in another tumour type: {e['disease']} ({e['match']} match)"
                    + ("" if tumour_type else "; give the tumour type to decide between tier I and II"))
        elif lvl in ("C", "D"):
            cand = ("II", f"CIViC level {lvl} evidence ({e['disease']}, {e['match']} match)")
        else:
            continue
        if best is None or cand[0] < best[0]:
            best = cand
    ok = v.get("oncokb") or {}
    lvl = (ok.get("level") or "") + " " + (ok.get("resistance") or "")
    if re.search(r"LEVEL_(1|2|R1)\b", lvl):
        cand = ("I", f"OncoKB {lvl.strip()} ({ok.get('oncogenic')})")
        best = cand if best is None or cand[0] < best[0] else best
    elif re.search(r"LEVEL_(3A|3B|4|R2)\b", lvl) or ok.get("oncogenic") in ("Oncogenic", "Likely Oncogenic"):
        cand = ("II", f"OncoKB {lvl.strip() or ok.get('oncogenic')}")
        best = cand if best is None or cand[0] < best[0] else best
    if best:
        return best
    cos = v.get("cosmic_count") or 0
    if cos >= 20:
        return "II", f"recurrent in COSMIC ({cos} samples): possible hotspot, check the literature"
    onc = v.get("clinvar_onc") or ""
    if re.search(r"oncogenic", onc, re.I) and not re.search(r"benign", onc, re.I):
        return "II", f"ClinVar somatic classification: {onc}"
    return "III", "no evidence of clinical significance found in the sources used (variant of unknown significance)"


# ---------------------------------------------------------------- TMB and MSI
def coding_mb(targets_bed, refflat):
    """Size (Mb) of target regions; intersected with coding exons when a refFlat is available."""
    if not targets_bed:
        return None, "unknown"
    tg = {}
    total = 0
    with open(targets_bed) as fh:
        lines = fh.readlines()
    for line in lines:
        f = line.split("\t")
        if len(f) < 3 or line.startswith(("#", "track", "browser")):
            continue
        s, e = int(f[1]), int(f[2])
        tg.setdefault(f[0], []).append((s, e))
        total += e - s
    if not refflat:
        return total / 1e6, "all target bases (coding regions unknown)"
    cds = {}
    with _open(refflat) as fh:
        rf_lines = fh.readlines()
    for line in rf_lines:
        f = line.rstrip("\n").split("\t")
        if len(f) < 11:
            continue
        ch, cs, ce = f[2], int(f[6]), int(f[7])
        for a, b in zip(f[9].strip(",").split(","), f[10].strip(",").split(",")):
            a, b = max(int(a), cs), min(int(b), ce)
            if b > a:
                cds.setdefault(ch, []).append((a, b))
    size = 0
    for ch, ivs in tg.items():
        c = sorted(cds.get(ch, []))
        merged = []
        for a, b in c:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        j = 0
        for s, e in sorted(ivs):
            while j < len(merged) and merged[j][1] <= s:
                j += 1
            k = j
            while k < len(merged) and merged[k][0] < e:
                size += max(0, min(e, merged[k][1]) - max(s, merged[k][0]))
                k += 1
    return size / 1e6, "coding bases within the target regions"


def tmb(variants, mb, min_vaf, min_dp):
    if not mb:
        return None
    n = 0
    for v in variants:
        csq = set((v.get("consequence") or "").split("&"))
        af = pop_af(v)
        if (v.get("filter") in ("PASS", ".") and csq & CODING and (v.get("vaf") or 0) >= min_vaf
                and (v.get("dp") or 0) >= min_dp and (af is None or af < 0.001) and "germline" not in (v.get("filter") or "")):
            n += 1
    return {"mutations": n, "mb": round(mb, 3), "tmb": round(n / mb, 1) if mb else None,
            "note": "Panels under ~1 Mb give imprecise TMB; tumour-only TMB is inflated by remaining germline variants."}


def parse_msi(path):
    with open(path) as fh:
        lines = [l.rstrip("\n").split("\t") for l in fh if l.strip()]
    if len(lines) < 2:
        return None
    d = dict(zip(lines[0], lines[1]))
    try:
        sites = int(float(d.get("Total_Number_of_Sites", 0)))
        pct = float(d.get("%", 0))
    except ValueError:
        return None
    if sites < 50:
        interp = "too few microsatellite sites in the targets for a reliable result"
    elif pct >= 10:
        interp = "high (MSI-H range by the MSK-IMPACT MSIsensor convention, ≥10%)"
    elif pct >= 3:
        interp = "indeterminate (3–10%)"
    else:
        interp = "stable (MSS range, <3%)"
    return {"sites": sites, "unstable": int(float(d.get("Number_of_Unstable_Sites", 0))), "score": pct, "interpretation": interp}
