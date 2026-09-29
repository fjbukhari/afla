import json
from pathlib import Path

from tw.dates import parse_date
from tw.dedup import find_duplicates
from tw.extract import extract_json, extract_tables, map_headers
from tw.score import Scorer

FX = Path(__file__).parent / "fixtures"


def test_dates():
    assert parse_date("14-Oct-2026 11:00 AM") == "2026-10-14"
    assert parse_date("03/10/2026") == "2026-10-03"  # day first
    assert parse_date("2026-11-01T05:00:00Z") == "2026-11-01"
    assert parse_date("/Date(1791000000000)/") == "2026-10-03"
    assert parse_date("20-Oct-2026 (Opening 11:30)") == "2026-10-20"
    assert parse_date("30-Oct-2026 12:00 (GMT 0.00)") == "2026-10-30"
    assert parse_date("") is None and parse_date("N/A") is None


def test_header_mapping():
    m = map_headers(["S.No", "Tender No", "Tender Title", "Procuring Agency", "Advertised Date", "Closing Date & Time"])
    assert m == {1: "ref", 2: "title", 3: "org", 4: "published", 5: "closing"}
    m = map_headers(["tenderTitle", "procuringAgencyName", "closingDate", "tenderNo"])
    assert sorted(m.values()) == ["closing", "org", "ref", "title"]


def test_table_extraction_skips_menus_and_finds_links():
    recs = extract_tables((FX / "portal_p1.html").read_text(), "https://portal.example/list")
    assert len(recs) == 3
    r = recs[0]
    assert r["title"] == "Supply of PCR Reagents and Diagnostic Kits"
    assert r["ref"] == "TS-100" and r["org"] == "National Institute of Health"
    assert r["closing"] == "2026-10-14" and r["published"] == "2026-09-20"
    assert r["url"] == "https://portal.example/tender/100"
    assert r["doc_url"] == "https://portal.example/docs/100.pdf"


def test_div_grid_extraction_ungm_style():
    recs = extract_tables((FX / "ungm_rows.html").read_text(), "https://www.ungm.org/Public/Notice")
    assert len(recs) == 2
    assert recs[0]["url"] == "https://www.ungm.org/Public/Notice/290001"
    assert recs[0]["closing"] == "2026-10-30" and recs[0]["org"] == "UNICEF"
    assert recs[0]["ref"] == "RFP/PAK/2026/011"


def test_json_extraction_picks_tender_list_not_menu():
    obj = {"menu": [{"title": "Active Tenders", "href": "/x"}],
           "data": {"items": [{"tenderId": 7, "tenderTitle": "Purchase of Laboratory Chemicals",
                               "procuringAgency": {"name": "CB Lab Karachi"}, "closingDate": "2026-10-19T00:00:00"}]}}
    recs = extract_json(obj, "https://p/", detail_url="https://p/#/tender/{tenderId}")
    assert len(recs) == 1
    assert recs[0]["org"] == "CB Lab Karachi" and recs[0]["closing"] == "2026-10-19"
    assert recs[0]["url"] == "https://p/#/tender/7"


def test_scoring_examples():
    s = Scorer()
    assert s.score("TENDER FOR SUPPLY OF CHEMICALS/DIAGNOSTIC KITS ETC. FOR NIH", "National Institute of Health")["core"]
    assert not s.score("Primary Injection Set", "Islamabad Electric Supply Company")["relevant"]
    assert not s.score("TENDER FOR HIRING SECURITY SERVICES AT NIH, ISLAMABAD", "National Institute of Health")["relevant"]
    assert not s.score("PROCUREMENT OF TOOLS FOR IOT LAB FOR MAKERSPACE PUNJAB PROJECT", "PITB")["relevant"]
    assert s.score("2- Generic Consumable", "CB Lab Karachi")["relevant"]  # vague title, lab buyer
    assert s.score("Next Generation Sequencing Consumables", "UHS")["core"]


def test_duplicates_across_portals():
    base = dict(org="", ref="", published=None, doc_url="")
    ts = [
        dict(base, id="ppra-fed:1", source="ppra-fed", title="Purchase of Lab Equipment for Deptt. of Biological Sciences", closing="2026-10-13", ref="X1"),
        dict(base, id="epads-fed:2", source="epads-fed", title="T-12 Purchase of Lab Equipment for Deptt of Biological Sciences", closing="2026-10-13"),
        dict(base, id="epads-fed:3", source="epads-fed", title="Purchase of Lab Equipment for Deptt. of Biological Sciences", closing="2026-11-30"),
        dict(base, id="ppra-punjab:4", source="ppra-punjab", title="Lot 1 reagents", closing="2026-10-13"),
        dict(base, id="ppra-punjab:5", source="ppra-punjab", title="Lot 2 reagents", closing="2026-10-13"),
    ]
    d = find_duplicates(ts)
    assert d == {"epads-fed:2": "ppra-fed:1"}  # different closing date and same-portal lots stay separate


def test_old_feed_rules_are_valid_json_serialisable():
    s = Scorer()
    json.dumps(s.R)


def test_link_list_pages():
    from tw.extract import extract_links
    recs = extract_links((FX / "uni_tenders.html").read_text(), "https://uni.example.edu.pk/tenders")
    assert len(recs) == 2
    assert recs[0]["doc_url"] == "https://uni.example.edu.pk/uploads/nit-lab-chemicals.pdf"
    assert recs[0]["published"] == "2026-09-28" and recs[0]["closing"] == "2026-10-14"
    assert "PCR kits" in recs[1]["title"]


def test_city_and_institute():
    from tw.places import city_of, institute_of
    assert city_of("", "COMSATS University Islamabad (CUI) - Lahore Campus — COMSATS", "") == "Lahore"
    assert city_of("Karachi central", "Sindh Govt. Hospital", "") == "Karachi"
    assert city_of("", "Pakistan Kidney Liver Institute", "PROCUREMENT OF ICU VENTILATORS") == "Lahore"
    assert city_of("", "Pakistan Kidney Liver Institute", "X-RAY FILMS FOR PKLI & RC RAWALPINDI") == "Rawalpindi"
    assert city_of("", "Regional Office (National Bank of Pakistan)", "UPS at NBP PCSIR LAB, D.I. Khan") == "Dera Ismail Khan"
    assert city_of("", "Ministry of Health", "Supply of ICT equipment") == ""
    assert institute_of("NUML — National University of Modern Languages") == "NUML"
    assert institute_of("FDE (FDE)") == "FDE"
