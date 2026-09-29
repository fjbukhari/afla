"""ACMG/AMP 2015 evidence suggestions for germline small variants (teaching aid).

Criteria that can be judged from annotations are *suggested* (with the reason shown); the student accepts or
rejects each one in the report, which then combines them with the Bayesian points system
(Tavtigian et al. 2020): very strong 8, strong 4, moderate 2, supporting 1 (benign negative).
Thresholds follow ClinGen SVI recommendations where they exist (PM2 at supporting, PVS1 decision tree outline,
Pejaver et al. 2022 REVEL calibration, Walker et al. 2023 SpliceAI). Criteria needing literature, segregation,
functional data or phenotype (PS3, PS4, PP1, PP4, BS3, BS4, BP5, ...) are left to the user.
Not a validated classifier. Education and research use only.
"""
import csv
import gzip
import re

LOF = {"stop_gained", "frameshift_variant", "splice_acceptor_variant", "splice_donor_variant",
       "transcript_ablation", "start_lost"}
MISSENSE = {"missense_variant"}
INFRAME = {"inframe_insertion", "inframe_deletion", "stop_lost", "protein_altering_variant"}
POINTS = {"VeryStrong": 8, "Strong": 4, "Moderate": 2, "Supporting": 1, "StandAlone": 0}

AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H",
       "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
       "Tyr": "Y", "Val": "V", "Ter": "*", "Sec": "U", "Xaa": "X"}


def protein_change(hgvsp):
    """'p.Arg882His' -> ('R', 882, 'H'); None when not a simple substitution."""
    m = re.match(r"p\.\(?([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2}|=)\)?$", hgvsp or "")
    if not m:
        return None
    ref, pos, alt = m.groups()
    return AA3.get(ref, "X"), int(pos), ("=" if alt == "=" else AA3.get(alt, "X"))


def one_letter(hgvsp):
    pc = protein_change(hgvsp)
    return f"{pc[0]}{pc[1]}{pc[2]}" if pc else ""


def load_constraint(path):
    """gnomAD v4.1 constraint table -> {gene: {loeuf, pli, mis_z}} (MANE/canonical transcript)."""
    out = {}
    if not path:
        return out
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        cols = rd.fieldnames or []
        c_loeuf = next((c for c in ("lof.oe_ci.upper", "oe_lof_upper") if c in cols), None)
        c_pli = next((c for c in ("lof.pLI", "pLI") if c in cols), None)
        c_mis = next((c for c in ("mis.z_score", "mis_z") if c in cols), None)
        for r in rd:
            g = r.get("gene")
            if not g:
                continue
            best = r.get("mane_select") == "true" or r.get("canonical") == "true"
            if g in out and not best:
                continue

            def f(c):
                try:
                    return float(r[c]) if c and r.get(c) not in (None, "", "NA") else None
                except ValueError:
                    return None
            out[g] = {"loeuf": f(c_loeuf), "pli": f(c_pli), "mis_z": f(c_mis)}
    return out


def load_clinvar_index(path, genes):
    """ClinVar pathogenic/likely pathogenic missense changes: {gene: {pos: [(alt_aa, hgvsp, id, sig, stars)]}}."""
    idx = {}
    if not path:
        return idx
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            g = r["gene"]
            if genes and g not in genes:
                continue
            idx.setdefault(g, {}).setdefault(int(r["pos"]), []).append(
                (r["alt_aa"], r["hgvsp"], r["clinvar_id"], r["significance"], int(r.get("stars") or 0)))
    return idx


def pop_af(v):
    vals = [x for x in (v.get("max_af"), v.get("gnomade"), v.get("gnomadg"), v.get("gnomad_af"), v.get("gnomad_grpmax")) if x is not None]
    return max(vals) if vals else None


def crit(code, strength, reason, suggested=True):
    return {"code": code, "strength": strength, "reason": reason, "suggested": suggested}


def evaluate(v, constraint, cv_index, context=None):
    """List of criteria for one variant dict (fields as produced by afla_report.parse_vcf)."""
    context = context or {}
    out = []
    csq = set((v.get("consequence") or "").split("&"))
    gene = v.get("gene") or ""
    gc = constraint.get(gene, {})
    af = pop_af(v)
    is_lof = bool(csq & LOF)
    is_missense = bool(csq & MISSENSE)
    sai = v.get("spliceai")

    # ---------------- population data
    if af is not None and af > 0.05:
        out.append(crit("BA1", "StandAlone", f"population allele frequency {af:.3g} > 5% (stand-alone benign)"))
    elif af is not None and af > 0.01:
        out.append(crit("BS1", "Strong", f"allele frequency {af:.3g} is higher than expected for a rare disorder (>1%); "
                                         "use a disease-specific threshold"))
    elif af is None or af == 0:
        out.append(crit("PM2", "Supporting", "absent from gnomAD (ClinGen: PM2 at supporting strength)"))
    elif af <= 1e-5:
        out.append(crit("PM2", "Supporting", f"extremely rare in gnomAD (AF {af:.2g})"))
    elif af <= 1e-4:
        out.append(crit("PM2", "Supporting", f"rare in gnomAD (AF {af:.2g}); acceptable for recessive disorders, "
                                              "check against the disease prevalence", suggested=False))

    # ---------------- null variants (PVS1)
    if is_lof:
        loeuf, pli = gc.get("loeuf"), gc.get("pli")
        intolerant = (loeuf is not None and loeuf < 0.6) or (pli is not None and pli >= 0.9)
        exon = v.get("exon") or ""
        last_exon = bool(re.match(r"^(\d+)/(\1)$", exon))
        if "start_lost" in csq:
            strength, note = "Moderate", "start codon lost (ClinGen: at most PVS1_Moderate)"
        elif last_exon and csq & {"stop_gained", "frameshift_variant"}:
            strength, note = "Strong", "in the last exon: may escape nonsense-mediated decay (downgraded)"
        elif csq & {"splice_acceptor_variant", "splice_donor_variant"}:
            strength, note = "VeryStrong", "canonical splice site (check for in-frame exon skipping or rescue)"
        else:
            strength, note = "VeryStrong", "predicted null variant"
        if intolerant:
            out.append(crit("PVS1", strength, f"{note}; {gene} is loss-of-function intolerant (LOEUF {loeuf if loeuf is not None else '?'})"))
        else:
            out.append(crit("PVS1", strength, f"{note}; apply ONLY if loss of function is a known disease mechanism for "
                                              f"{gene or 'this gene'} (gnomAD LOEUF {loeuf if loeuf is not None else 'n/a'})",
                            suggested=False))

    # ---------------- same amino-acid change / same codon (PS1, PM5)
    pc = protein_change(v.get("hgvsp"))
    if is_missense and pc and gene in cv_index:
        ref_aa, pos, alt_aa = pc
        same = [e for e in cv_index[gene].get(pos, []) if e[0] == alt_aa and e[2] != (v.get("clinvar_id") or "")]
        other = [e for e in cv_index[gene].get(pos, []) if e[0] != alt_aa]
        if same:
            e = same[0]
            out.append(crit("PS1", "Strong", f"same amino-acid change as ClinVar {e[3]} variant {e[1]} (VCV/ID {e[2]}, {e[4]}★) "
                                             "caused by a different nucleotide change; check splicing is not the mechanism"))
        if other:
            e = sorted(other, key=lambda x: -x[4])[0]
            out.append(crit("PM5", "Moderate", f"different missense change at the same residue is ClinVar {e[3]}: {e[1]} "
                                               f"(ID {e[2]}, {e[4]}★)"))

    # ---------------- protein length changes (PM4)
    if csq & INFRAME and not is_lof:
        out.append(crit("PM4", "Moderate", "in-frame deletion/insertion or stop-loss changes protein length "
                                           "(not applicable inside a repeat region)"))

    # ---------------- computational evidence (PP3 / BP4)
    revel = v.get("revel")
    if is_missense and revel is not None:
        if revel >= 0.932:
            out.append(crit("PP3", "Strong", f"REVEL {revel:.3f} ≥ 0.932 (Pejaver et al. 2022)"))
        elif revel >= 0.773:
            out.append(crit("PP3", "Moderate", f"REVEL {revel:.3f} ≥ 0.773"))
        elif revel >= 0.644:
            out.append(crit("PP3", "Supporting", f"REVEL {revel:.3f} ≥ 0.644"))
        elif revel <= 0.003:
            out.append(crit("BP4", "VeryStrong", f"REVEL {revel:.3f} ≤ 0.003"))
        elif revel <= 0.016:
            out.append(crit("BP4", "Strong", f"REVEL {revel:.3f} ≤ 0.016"))
        elif revel <= 0.183:
            out.append(crit("BP4", "Moderate", f"REVEL {revel:.3f} ≤ 0.183"))
        elif revel <= 0.290:
            out.append(crit("BP4", "Supporting", f"REVEL {revel:.3f} ≤ 0.290"))
    elif is_missense and v.get("am_class"):
        am = v.get("am_class")
        if am == "likely_pathogenic":
            out.append(crit("PP3", "Supporting", f"AlphaMissense likely pathogenic ({v.get('am_score')}); REVEL not available"))
        elif am == "likely_benign":
            out.append(crit("BP4", "Supporting", f"AlphaMissense likely benign ({v.get('am_score')}); REVEL not available"))
    if sai is not None and not is_lof:
        if sai >= 0.2:
            out.append(crit("PP3", "Supporting", f"SpliceAI max delta score {sai:.2f} ≥ 0.2 predicts a splicing effect"))
        elif sai <= 0.1 and not is_missense:
            out.append(crit("BP4", "Supporting", f"SpliceAI max delta score {sai:.2f} ≤ 0.1: no predicted splicing effect"))

    # ---------------- gene-level missense constraint (PP2)
    mz = gc.get("mis_z")
    if is_missense and mz is not None and mz >= 3.09:
        out.append(crit("PP2", "Supporting", f"{gene} has few benign missense variants in gnomAD (missense Z {mz:.2f}); "
                                             "apply only if missense is a common disease mechanism", suggested=False))

    # ---------------- silent variants (BP7)
    if "synonymous_variant" in csq and "splice_region_variant" not in csq:
        known = "SpliceAI ≤ 0.1" if sai is not None and sai <= 0.1 else "no splice prediction available"
        out.append(crit("BP7", "Supporting", f"synonymous, outside the splice region ({known}); confirm the nucleotide is not highly conserved",
                        suggested=sai is not None and sai <= 0.1))

    # ---------------- family data
    inh = context.get("inheritance") or ""
    if re.search(r"(^|, )de novo", inh):
        out.append(crit("PM6", "Moderate", "de novo in the trio (parents sequenced, parentage assumed). Upgrade to PS2 "
                                           "if parentage is confirmed and the phenotype fits"))
    if "compound" in inh and context.get("partner_plp"):
        out.append(crit("PM3", "Moderate", f"in trans with a pathogenic/likely pathogenic variant ({context['partner_plp']})"))
    elif "compound" in inh:
        out.append(crit("PM3", "Supporting", "in trans with another rare variant in the same gene (recessive disorders; "
                                             "strength depends on the other variant's classification)", suggested=False))
    return out


def classify(criteria):
    """Points and class from the *suggested* criteria (the report recomputes after the user's choices)."""
    chosen = [c for c in criteria if c["suggested"]]
    if any(c["code"] == "BA1" for c in chosen):
        return -99, "Benign"
    pts = 0
    for c in chosen:
        p = POINTS[c["strength"]]
        pts += -p if c["code"].startswith("B") else p
    return pts, points_class(pts)


def points_class(pts):
    if pts >= 10:
        return "Pathogenic"
    if pts >= 6:
        return "Likely pathogenic"
    if pts >= 0:
        return "Uncertain significance"
    if pts >= -6:
        return "Likely benign"
    return "Benign"
