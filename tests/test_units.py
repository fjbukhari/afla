#!/usr/bin/env python3
"""Unit tests for the AFLA analysis logic (standard library only):  python3 tests/test_units.py"""
import gzip
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import afla_acmg as A  # noqa: E402
import afla_somatic as S  # noqa: E402
import afla_report as R  # noqa: E402


def var(**kw):
    v = {"gene": "GENE1", "consequence": "missense_variant", "impact": "MODERATE", "hgvsp": "p.Arg882His", "exon": "5/10",
         "max_af": None, "gnomade": None, "gnomadg": None, "gnomad_af": None, "gnomad_grpmax": None, "revel": None,
         "am_class": "", "am_score": None, "spliceai": None, "clinvar": "", "clinvar_id": "", "filter": "PASS", "vaf": 0.4, "dp": 100}
    v.update(kw)
    return v


def codes(crit, suggested_only=True):
    return {c["code"] + "_" + c["strength"] for c in crit if c["suggested"] or not suggested_only}


class ACMG(unittest.TestCase):
    CON = {"GENE1": {"loeuf": 0.2, "pli": 1.0, "mis_z": 3.5}, "TOL": {"loeuf": 1.4, "pli": 0.0, "mis_z": 0.1}}

    def test_protein_change(self):
        self.assertEqual(A.protein_change("p.Arg882His"), ("R", 882, "H"))
        self.assertEqual(A.protein_change("p.Leu10="), ("L", 10, "="))
        self.assertIsNone(A.protein_change("p.Arg882fs"))
        self.assertEqual(A.one_letter("p.Val600Glu"), "V600E")

    def test_population(self):
        self.assertIn("BA1_StandAlone", codes(A.evaluate(var(max_af=0.2), {}, {})))
        self.assertIn("BS1_Strong", codes(A.evaluate(var(max_af=0.02), {}, {})))
        self.assertIn("PM2_Supporting", codes(A.evaluate(var(), {}, {})))
        self.assertNotIn("PM2_Supporting", codes(A.evaluate(var(gnomade=0.001), {}, {})))

    def test_pvs1(self):
        c = codes(A.evaluate(var(consequence="stop_gained", impact="HIGH"), self.CON, {}))
        self.assertIn("PVS1_VeryStrong", c)
        c = codes(A.evaluate(var(consequence="stop_gained", impact="HIGH", exon="10/10"), self.CON, {}))
        self.assertIn("PVS1_Strong", c)                      # last exon: NMD escape
        c = A.evaluate(var(gene="TOL", consequence="frameshift_variant", impact="HIGH"), self.CON, {})
        self.assertIn("PVS1_VeryStrong", codes(c, suggested_only=False))
        self.assertNotIn("PVS1_VeryStrong", codes(c))       # tolerant gene: only "consider"
        self.assertNotIn("PP3_Supporting", codes(A.evaluate(var(consequence="splice_donor_variant", spliceai=0.9), self.CON, {})))

    def test_revel_bands(self):
        self.assertIn("PP3_Strong", codes(A.evaluate(var(revel=0.95), {}, {})))
        self.assertIn("PP3_Moderate", codes(A.evaluate(var(revel=0.8), {}, {})))
        self.assertIn("PP3_Supporting", codes(A.evaluate(var(revel=0.7), {}, {})))
        self.assertIn("BP4_Supporting", codes(A.evaluate(var(revel=0.25), {}, {})))
        self.assertIn("BP4_Moderate", codes(A.evaluate(var(revel=0.1), {}, {})))
        self.assertFalse({c for c in codes(A.evaluate(var(revel=0.5), {}, {})) if c.startswith(("PP3", "BP4"))})

    def test_ps1_pm5(self):
        idx = {"GENE1": {882: [("H", "p.Arg882His", "111", "Pathogenic", 3), ("C", "p.Arg882Cys", "222", "Likely pathogenic", 2)]}}
        c = codes(A.evaluate(var(clinvar_id="999"), {}, idx))
        self.assertIn("PS1_Strong", c)
        self.assertIn("PM5_Moderate", c)
        self.assertNotIn("PS1_Strong", codes(A.evaluate(var(clinvar_id="111"), {}, idx)))   # the same ClinVar record

    def test_family_and_points(self):
        c = A.evaluate(var(), {}, {}, {"inheritance": "de novo"})
        self.assertIn("PM6_Moderate", codes(c))
        c = A.evaluate(var(), {}, {}, {"inheritance": "possible de novo (low allele fraction: artefact or mosaic?)"})
        self.assertNotIn("PM6_Moderate", codes(c))
        self.assertEqual(A.points_class(10), "Pathogenic")
        self.assertEqual(A.points_class(6), "Likely pathogenic")
        self.assertEqual(A.points_class(0), "Uncertain significance")
        self.assertEqual(A.points_class(-1), "Likely benign")
        self.assertEqual(A.points_class(-7), "Benign")
        pts, cls = A.classify([A.crit("PVS1", "VeryStrong", ""), A.crit("PM2", "Supporting", ""), A.crit("PP3", "Supporting", "")])
        self.assertEqual((pts, cls), (10, "Pathogenic"))


class Somatic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        head = "molecular_profile\tdisease\ttherapies\tevidence_type\tevidence_direction\tevidence_level\tsignificance\tevidence_status\tevidence_id\n"
        rows = ["BRAF V600E\tMelanoma\tVemurafenib\tPredictive\tSupports\tA\tSensitivity/Response\taccepted\t1\n",
                "BRAF V600\tColorectal Cancer\t\tPrognostic\tSupports\tB\tPoor Outcome\taccepted\t2\n",
                "EGFR EXON 19 DELETION\tLung Non-small Cell Carcinoma\tErlotinib\tPredictive\tSupports\tA\tSensitivity/Response\taccepted\t3\n",
                "TP53 LOSS-OF-FUNCTION\tChronic Lymphocytic Leukemia\t\tPrognostic\tSupports\tB\tPoor Outcome\taccepted\t4\n",
                "KRAS G12C AND STK11 LOSS\tLung\t\tPredictive\tSupports\tC\tResistance\taccepted\t5\n"]
        Path(self.tmp, "nightly-ClinicalEvidenceSummaries.tsv").write_text(head + "".join(rows))

    def test_civic_and_tiers(self):
        civ = S.load_civic(self.tmp, {"BRAF", "EGFR", "TP53", "KRAS"})
        self.assertNotIn("KRAS", civ)                        # combination profiles are skipped
        v = var(gene="BRAF", hgvsp="p.Val600Glu", consequence="missense_variant")
        v["civic"] = S.civic_match(v, civ)
        self.assertEqual({e["match"] for e in v["civic"]}, {"exact", "codon"})
        self.assertEqual(S.tier(v, "melanoma")[0], "I")
        self.assertEqual(S.tier(v, "")[0], "II")
        e = var(gene="EGFR", hgvsp="p.Glu746_Ala750del", consequence="inframe_deletion", exon="19/28")
        e["civic"] = S.civic_match(e, civ)
        self.assertTrue(e["civic"] and e["civic"][0]["match"].startswith("exon"))
        t = var(gene="TP53", hgvsp="p.Arg196Ter", consequence="stop_gained")
        t["civic"] = S.civic_match(t, civ)
        self.assertEqual(S.tier(t, "chronic lymphocytic leukemia")[0], "I")
        self.assertEqual(S.tier(var(max_af=0.3), "x")[0], "IV")
        self.assertEqual(S.tier(var(), "x")[0], "III")

    def test_cosmic_tmb_msi(self):
        p = Path(self.tmp, "cmc.tsv")
        p.write_text("GENE_NAME\tMutation AA\tCOSMIC_SAMPLE_MUTATED\tMUTATION_SIGNIFICANCE_TIER\nBRAF\tp.V600E\t50000\t1\nBRAF_ENST1\tp.V600E\t10\t1\n")
        c = S.load_cosmic(p, {"BRAF"})
        self.assertEqual(c[("BRAF", "p.V600E")]["count"], 50010)
        vs = [var(consequence="missense_variant", vaf=0.3, dp=200), var(consequence="synonymous_variant", vaf=0.3, dp=200),
              var(consequence="missense_variant", vaf=0.01, dp=200), var(consequence="missense_variant", vaf=0.3, dp=200, max_af=0.2)]
        self.assertEqual(S.tmb(vs, 0.5, 0.05, 50)["mutations"], 1)
        m = Path(self.tmp, "m.txt"); m.write_text("Total_Number_of_Sites\tNumber_of_Unstable_Sites\t%\n400\t60\t15.0\n")
        self.assertTrue(S.parse_msi(m)["interpretation"].startswith("high"))
        m.write_text("Total_Number_of_Sites\tNumber_of_Unstable_Sites\t%\n10\t5\t50\n")
        self.assertTrue(S.parse_msi(m)["interpretation"].startswith("too few"))

    def test_coding_mb(self):
        bed = Path(self.tmp, "t.bed"); bed.write_text("chr1\t100\t300\nchr1\t1000\t1100\n")
        rf = Path(self.tmp, "rf.txt"); rf.write_text("G\tNM_1\tchr1\t+\t0\t2000\t150\t1050\t2\t120,900,\t250,1200,\n")
        mb, what = S.coding_mb(bed, rf)
        self.assertAlmostEqual(mb * 1e6, 100 + 50)          # 150-250 and 1000-1050
        self.assertIn("coding", what)


class Inheritance(unittest.TestCase):
    def row(self, gene, p, m, f, af=None, clin=""):
        mk = lambda gt, vaf: {"gt": gt, "dp": 40, "gq": 99, "vaf": vaf, "alt_reads": 0 if gt == "0/0" else 20}
        return {"gene": gene, "chrom": "chr1", "pos": 1, "hgvsc": "c.1A>G", "clinvar": clin, "filter": "PASS", "impact": "MODERATE",
                "max_af": af, "gnomade": None, "gnomadg": None, "gnomad_af": None, "gnomad_grpmax": None,
                "samples": {"P": mk(*p), "M": mk(*m), "F": mk(*f)}}

    def test_trio(self):
        rows = [self.row("A", ("0/1", 0.5), ("0/0", 0), ("0/0", 0)),
                self.row("B", ("0/1", 0.5), ("0/1", 0.5), ("0/0", 0)),
                self.row("B", ("0/1", 0.5), ("0/0", 0), ("0/1", 0.5), clin="Pathogenic"),
                self.row("C", ("1/1", 1.0), ("0/1", 0.5), ("0/1", 0.5)),
                self.row("D", ("0/1", 0.1), ("0/0", 0), ("0/0", 0))]
        R.inheritance(rows, "P", {"mother": "M", "father": "F"}, "female", 10, 20)
        self.assertEqual(rows[0]["inheritance"], "de novo")
        self.assertIn("compound heterozygous", rows[1]["inheritance"])
        self.assertIn("Pathogenic", rows[1].get("partner_plp", ""))
        self.assertEqual(rows[3]["inheritance"], "homozygous")
        self.assertTrue(rows[4]["inheritance"].startswith("possible de novo"))


class Tools(unittest.TestCase):
    def test_manifest(self):
        tmp = tempfile.mkdtemp()
        m = Path(tmp, "m.txt")
        m.write_text("[Header]\nx\ty\n[Probes]\nTarget Region Name\tTarget Region ID\tTarget ID\tSpecies\tBuild ID\tChromosome\tStart Position\tEnd Position\tSubmitted Target Region Strand\tULSO Sequence\tULSO Genomic Hits\tDLSO Sequence\tDLSO Genomic Hits\tProbe Strand\n"
                     "R\tR1\tAMP1\thuman\thg38\tchr2\t1001\t1200\t+\tAAAAAAAAAAAAAAAAAAAAAAAA\t1\tCCCCCCCCCCCCCCCCCCCCC\t1\t+\n"
                     "[Targets]\nTargetA\tTargetB\tTarget Number\tChromosome\tStart Position\tEnd Position\tProbe Strand\tSequence\tSpecies\tBuild ID\n"
                     "AMP1\tAMP1\t1\tchr2\t1001\t1200\t+\tACGT\thuman\thg38\n")
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "manifest_to_primers.py"), str(m), str(Path(tmp, "p"))], check=True, capture_output=True)
        primers = Path(tmp, "p.primers.bed").read_text().split("\n")
        self.assertEqual(primers[0].split("\t")[:3], ["chr2", "1000", "1024"])     # 24-base ULSO
        self.assertEqual(primers[1].split("\t")[:3], ["chr2", "1179", "1200"])     # 21-base DLSO
        self.assertEqual(Path(tmp, "p.inserts.bed").read_text().split("\t")[:3], ["chr2", "1024", "1179"])

    def test_gene_list(self):
        self.assertEqual(R.read_gene_list("brca1, BRCA2;palb2"), ["BRCA1", "BRCA2", "PALB2"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
