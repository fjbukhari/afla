"""Work out the city of a tender and a clean institute name, for the dashboard filters."""
import re

# Canonical city -> spellings/abbreviations seen on portals. Longer names are listed before
# the cities they contain (e.g. "Dera Ismail Khan" before "Khan...") by matching longest first.
CITIES = {
    "Islamabad": ["islamabad", "isb", "chak shahzad", "nilore"],
    "Rawalpindi": ["rawalpindi", "rwp", "pindi", "chaklala", "gujar khan"],
    "Wah Cantt / Taxila": ["wah cantt", "wah", "taxila"],
    "Lahore": ["lahore", "lhr", "raiwind"],
    "Karachi": ["karachi", "khi", "malir", "korangi", "landhi", "gadani"],
    "Peshawar": ["peshawar", "pesh"],
    "Quetta": ["quetta"],
    "Faisalabad": ["faisalabad", "fsd", "lyallpur"],
    "Multan": ["multan"],
    "Hyderabad": ["hyderabad", "hyd", "kotri"],
    "Gujranwala": ["gujranwala"],
    "Sialkot": ["sialkot"],
    "Bahawalpur": ["bahawalpur"],
    "Sargodha": ["sargodha"],
    "Sukkur": ["sukkur"],
    "Larkana": ["larkana"],
    "Nawabshah": ["nawabshah", "shaheed benazirabad", "benazirabad"],
    "Jamshoro": ["jamshoro"],
    "Mirpur Khas": ["mirpur ?khas"],
    "Thatta": ["thatta"],
    "Abbottabad": ["abbottabad", "abbotabad"],
    "Mardan": ["mardan"],
    "Swat": ["swat", "saidu sharif", "mingora"],
    "Kohat": ["kohat"],
    "Bannu": ["bannu"],
    "Dera Ismail Khan": ["dera ismail khan", "d\\.? ?i\\.? ?khan"],
    "Dera Ghazi Khan": ["dera ghazi khan", "d\\.? ?g\\.? ?khan"],
    "Mansehra": ["mansehra"],
    "Nowshera": ["nowshera"],
    "Charsadda": ["charsadda"],
    "Swabi": ["swabi"],
    "Haripur": ["haripur"],
    "Chitral": ["chitral"],
    "Sahiwal": ["sahiwal"],
    "Okara": ["okara"],
    "Kasur": ["kasur"],
    "Sheikhupura": ["sheikhupura"],
    "Jhang": ["jhang"],
    "Gujrat": ["gujrat"],
    "Jhelum": ["jhelum"],
    "Chakwal": ["chakwal"],
    "Attock": ["attock"],
    "Mianwali": ["mianwali"],
    "Rahim Yar Khan": ["rahim ?yar ?khan", "r\\.? ?y\\.? ?khan"],
    "Muzaffargarh": ["muzaffargarh"],
    "Vehari": ["vehari"],
    "Khanewal": ["khanewal"],
    "Narowal": ["narowal"],
    "Hafizabad": ["hafizabad"],
    "Toba Tek Singh": ["toba tek singh"],
    "Bhakkar": ["bhakkar"],
    "Layyah": ["layyah"],
    "Gwadar": ["gwadar"],
    "Turbat": ["turbat", "kech"],
    "Khuzdar": ["khuzdar"],
    "Gilgit": ["gilgit"],
    "Skardu": ["skardu"],
    "Chilas": ["chilas", "diamer"],
    "Muzaffarabad": ["muzaffarabad"],
    "Mirpur (AJK)": ["mirpur(?! ?khas)"],
    "Kotli": ["kotli"],
    "Rawalakot": ["rawalakot"],
    "Tarbela": ["tarbela"],
    "Kamra": ["kamra"],
}
_CITY_RX = sorted(((c, re.compile(r"(?<![a-z])(?:" + "|".join(v) + r")(?![a-z])", re.I)) for c, v in CITIES.items()),
                  key=lambda x: -max(len(v) for v in CITIES[x[0]]))


# Home city of buyers whose names do not mention one (used only when nothing else names a city)
HOME = [
    (r"\bPKLI\b|Pakistan Kidney (and|&)? ?Liver", "Lahore"), (r"\bNIH\b|National Institutes? of Health", "Islamabad"),
    (r"\bPIMS\b|Pakistan Institute of Medical Sciences", "Islamabad"), (r"\bSZABMU\b|Shaheed Zulfiqar Ali Bhutto Medical", "Islamabad"),
    (r"\bNUST\b|National University of Sciences", "Islamabad"), (r"\bQAU\b|Quaid-?i-?Azam University", "Islamabad"),
    (r"\bDRAP\b|Drug Regulatory Authority", "Islamabad"), (r"\bNUMS\b|National University of Medical Sciences", "Rawalpindi"),
    (r"\bAFIP\b|Armed Forces Institute of Pathology", "Rawalpindi"), (r"\bAFIC\b|\bAFIRM\b", "Rawalpindi"),
    (r"\bAKU\b|Aga Khan University", "Karachi"), (r"\bDUHS\b|Dow University", "Karachi"), (r"\bJSMU\b|Jinnah Sindh Medical", "Karachi"),
    (r"\bSIUT\b", "Karachi"), (r"\bNICVD\b|\bNICH\b|\bJPMC\b|Jinnah Postgraduate", "Karachi"), (r"ICCBS|\bKIBGE\b|\bPCMD\b", "Karachi"),
    (r"Indus Hospital", "Karachi"), (r"\bUHS\b|University of Health Sciences", "Lahore"), (r"\bKEMU\b|King Edward Medical", "Lahore"),
    (r"Shaukat Khanum|\bSKMCH", "Lahore"), (r"\bUVAS\b|University of Veterinary", "Lahore"), (r"\bPFSA\b|Punjab Forensic", "Lahore"),
    (r"University of the Punjab|Punjab University", "Lahore"), (r"\bPIC\b|Punjab Institute of Cardiology", "Lahore"),
    (r"\bKMU\b|Khyber Medical University|Lady Reading|\bLRH\b|Khyber Teaching|Hayatabad Medical", "Peshawar"),
    (r"\bLUMHS\b|Liaquat University of Medical", "Jamshoro"), (r"\bNIBGE\b|\bNIAB\b|\bUAF\b|University of Agriculture,? Faisalabad", "Faisalabad"),
    (r"\bNIFA\b", "Peshawar"), (r"\bBUITEMS\b|Bolan Medical|University of Balochistan", "Quetta"),
]
HOME = [(re.compile(p, re.I), c) for p, c in HOME]


def city_of(location="", org="", title=""):
    """First city named in the location, then the buyer, then the title; else the buyer's known home city."""
    c = _named_city(location, org, title)
    if c:
        return c
    for rx, city in HOME:
        if rx.search(org or "") or rx.search(title or ""):
            return city
    return ""


def _named_city(location, org, title):
    # In a buyer's name the last city wins ("COMSATS University Islamabad - Lahore Campus" -> Lahore);
    # in a location or title the first one does.
    for text, last in ((location, False), (re.split(r"\s+[—–]\s+", org or "")[0], True), (title, False)):
        if not text:
            continue
        hits = [(m.start(), city) for city, rx in _CITY_RX for m in rx.finditer(text)]
        if hits:
            return (max if last else min)(hits)[1]
    return ""


def institute_of(org):
    """'Buyer — Ministry' and 'Buyer (Buyer)' -> 'Buyer'; keeps short acronyms: 'NIH (National Institute of Health)'."""
    o = re.split(r"\s+[—–]\s+", org or "")[0].strip()
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", o)
    if m and m.group(1):
        a, b = m.group(1).strip(), m.group(2).strip()
        if a.lower() == b.lower() or b.lower() in a.lower():
            o = a
        elif a.lower() in b.lower():
            o = b
    return re.sub(r"\s+", " ", o).strip(" ,.-")
