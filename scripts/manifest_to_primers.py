#!/usr/bin/env python3
"""Illumina TruSeq Custom Amplicon / TruSight (TSCA-style) manifest -> primer BED + insert BED for AFLA.

   python3 scripts/manifest_to_primers.py panel_manifest.txt OUT_PREFIX
   -> OUT_PREFIX.primers.bed  (use as "Primer BED")      OUT_PREFIX.inserts.bed  (use as "Target regions")

The manifest's [Probes] section lists, per amplicon, the upstream (ULSO) and downstream (DLSO) locus-specific
oligo sequences; the [Targets] section lists amplicon start/end. The oligo lengths give the primer positions.
Check the result against the vendor's documentation for your panel (EXPERIMENTAL, education use).
Coordinates are written as in the manifest (usually hg19 for older panels!): lift them over to GRCh38 if needed
(e.g. UCSC liftOver or CrossMap) before use.
"""
import sys


def sections(path):
    cur, out = None, {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        if line.startswith("[") and line.endswith("]"):
            cur = line.strip("[]").lower()
            out[cur] = []
            continue
        if cur and line.strip():
            out[cur].append(line.split("\t"))
    return out


def main(manifest, prefix):
    s = sections(manifest)
    probes, targets = s.get("probes", []), s.get("targets", [])
    if not probes or not targets:
        sys.exit("No [Probes] and [Targets] sections found: is this an Illumina TruSeq/TSCA manifest?")
    ph, th = [h.lower() for h in probes[0]], [h.lower() for h in targets[0]]
    col = lambda head, *names: next((head.index(n) for n in names if n in head), None)
    p_id, p_ulso, p_dlso, p_strand = col(ph, "target id"), col(ph, "ulso sequence"), col(ph, "dlso sequence"), col(ph, "probe strand")
    t_id, t_chr, t_s, t_e, t_strand = col(th, "targeta", "target id", "name"), col(th, "chromosome"), col(th, "start position"), col(th, "end position"), col(th, "probe strand")
    oligos = {}
    for r in probes[1:]:
        oligos[r[p_id]] = (len(r[p_ulso]), len(r[p_dlso]), r[p_strand] if p_strand is not None else "+")
    n = 0
    with open(prefix + ".primers.bed", "w") as pb, open(prefix + ".inserts.bed", "w") as ib:
        for r in targets[1:]:
            tid = r[t_id]
            if tid not in oligos:
                continue
            ulso, dlso, strand = oligos[tid]
            chrom = r[t_chr] if r[t_chr].startswith("chr") else "chr" + r[t_chr]
            start, end = int(r[t_s]) - 1, int(r[t_e])       # BED is 0-based
            left, right = (ulso, dlso) if strand in ("+", "1", "plus") else (dlso, ulso)
            pb.write(f"{chrom}\t{start}\t{start + left}\t{tid}_left\t0\t+\n")
            pb.write(f"{chrom}\t{end - right}\t{end}\t{tid}_right\t0\t-\n")
            ib.write(f"{chrom}\t{start + left}\t{end - right}\t{tid}\n")
            n += 1
    print(f"{n} amplicons -> {prefix}.primers.bed and {prefix}.inserts.bed")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
