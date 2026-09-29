"""Phenotype-driven gene ranking from HPO terms (teaching aid, in the spirit of Phenomizer/Exomiser).

Each gene's phenotype annotations (HPO genes_to_phenotype.txt) are compared with the patient's HPO terms using
Resnik semantic similarity: for every patient term, the most informative ancestor it shares with any of the gene's
terms (information content = -log(fraction of genes annotated)). The score is the average over patient terms,
scaled to 0-1 by the best possible value. Uses the HPO files downloaded by scripts/afla-setup.sh.
"""
import math
import re
from pathlib import Path


def load_obo(path):
    """hp.obo -> (names, parents, alternative/obsolete id -> current id)."""
    names, parents, alt = {}, {}, {}
    text = open(path, encoding="utf-8").read()
    for stanza in text.split("\n\n"):
        lines = stanza.strip().split("\n")
        if not lines or lines[0] != "[Term]":
            continue
        t = {"is_a": [], "alt": []}
        for line in lines[1:]:
            k, _, v = line.partition(": ")
            if k == "id":
                t["id"] = v
            elif k == "name":
                t["name"] = v
            elif k == "is_a":
                t["is_a"].append(v.split(" ")[0])
            elif k == "alt_id":
                t["alt"].append(v)
            elif k == "is_obsolete" and v.strip() == "true":
                t["obsolete"] = True
            elif k == "replaced_by":
                t["replaced_by"] = v.strip()
        if "id" not in t:
            continue
        if t.get("obsolete"):
            if t.get("replaced_by"):
                alt[t["id"]] = t["replaced_by"]
            continue
        names[t["id"]] = t.get("name", t["id"])
        parents[t["id"]] = t["is_a"]
        for a in t["alt"]:
            alt[a] = t["id"]
    return names, parents, alt


class HPO:
    def __init__(self, hpo_dir):
        d = Path(hpo_dir)
        self.names, self.parents, self.alt = load_obo(d / "hp.obo")
        self._anc = {}
        self.gene_terms = {}
        g2p = d / "genes_to_phenotype.txt"
        for line in open(g2p, encoding="utf-8"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 3 or not f[2].startswith("HP:"):
                continue
            t = self.norm(f[2])
            # phenotypic abnormalities only (not inheritance modes, onset or frequency terms)
            if "HP:0000118" in self.ancestors(t) and t != "HP:0000118":
                self.gene_terms.setdefault(f[1], set()).add(t)
        # information content from the number of genes annotated to each term or its descendants
        counts = {}
        self.gene_anc = {}
        for g, terms in self.gene_terms.items():
            anc = set()
            for t in terms:
                anc |= self.ancestors(t)
            self.gene_anc[g] = anc
            for t in anc:
                counts[t] = counts.get(t, 0) + 1
        n = max(1, len(self.gene_terms))
        self.ic = {t: -math.log(c / n) for t, c in counts.items()}

    def norm(self, t):
        return self.alt.get(t, t)

    def ancestors(self, t):
        t = self.norm(t)
        if t in self._anc:
            return self._anc[t]
        out = {t}
        for p in self.parents.get(t, []):
            out |= self.ancestors(p)
        self._anc[t] = out
        return out

    def parse_terms(self, text):
        terms = []
        for t in re.findall(r"HP:\d{7}", text or ""):
            t = self.norm(t)
            if t in self.names and t not in terms:
                terms.append(t)
        return terms

    def _best(self, t, anc_set):
        best, bt = 0.0, None
        for a in self.ancestors(t) & anc_set:
            ic = self.ic.get(a, 0.0)
            if ic > best:
                best, bt = ic, a
        return best, bt

    def score(self, gene, terms):
        """Symmetric Resnik similarity, 0-1: how well the gene explains the patient's terms, averaged with how
        much of the gene's own phenotype the patient shows. (score, [(patient term, shared ancestor, IC)])."""
        anc = self.gene_anc.get(gene)
        if not anc or not terms:
            return 0.0, []
        pat_anc = set()
        for q in terms:
            pat_anc |= self.ancestors(q)
        got, top, matches = 0.0, 0.0, []
        for q in terms:
            best, bt = self._best(q, anc)
            got += best
            top += self.ic.get(q, 0.0) or 1.0
            if bt:
                matches.append([q, bt, round(best, 2)])
        g_terms = self.gene_terms.get(gene, set())
        got2 = sum(self._best(g, pat_anc)[0] for g in g_terms)
        top2 = sum(self.ic.get(g, 0.0) for g in g_terms) or 1.0
        s = 0.5 * (got / top if top else 0) + 0.5 * (got2 / top2)
        return round(min(1.0, s), 3), matches

    def rank(self, genes, terms):
        out = {}
        for g in genes:
            s, m = self.score(g, terms)
            if s > 0:
                out[g] = {"score": s, "matches": [[q, self.names.get(q, q), a, self.names.get(a, a), ic] for q, a, ic in m]}
        return out
