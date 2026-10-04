"""Page layouts that defeated the reader on the office PC's first real run.

Of the 28 portals, 15 reported "no tender list was recognised". The captured pages showed
three separate faults, each reproduced here with the structure of the page that exposed it:

  * Punjab PPRA publishes a hundred tenders in a Telerik RadGrid: a data table with a pager
    table inside it, wrapped in three layout tables, whose <thead> holds the column names
    followed by an empty filter row, and whose first column is called "Procurement Title" but
    holds the stage of the notice while the real subject sits in "Procurement Name".
  * The KP health department and UNDP publish theirs as a list of links, which the automatic
    strategy never tried.
  * Reading a page's links finds tenders on those pages, but on a portal's front page it also
    found the office address and a software vendor's URL, so stray links must be dropped.
"""
from tw.extract import extract_links, extract_tables

# ------------------------------------------------------------------ Telerik RadGrid

TENDERS = [
    ("Addendum", "SUPPLY AND INSTALLATION OF HAEMATOLOGY ANALYSERS FOR THE DISTRICT HEADQUARTER "
                 "HOSPITAL, INCLUDING THREE YEARS OF REAGENTS", "Goods",
     "04 Oct 2026", "07 Oct 2026", "Primary and Secondary Healthcare Department", "Active"),
    ("Tender", "OUTSOURCING OF SOLID WASTE MANAGEMENT SERVICES FOR TEHSIL FAISALABAD URBAN-II AREAS",
     "Services", "02 Oct 2026", "16 Oct 2026", "Lahore Waste Management Company", "Active"),
    ("Corrigendum", "PROCUREMENT OF ELISA KITS AND LABORATORY CONSUMABLES FOR THE PUBLIC HEALTH "
                    "LABORATORY", "Goods", "01 Oct 2026", "20 Oct 2026",
     "Punjab Health Facilities Management Company", "Active"),
    ("Tender", "CONSTRUCTION OF A BLOOD BANK BUILDING AT THE TEACHING HOSPITAL", "Works",
     "30 Sep 2026", "21 Oct 2026", "Communication and Works Department", "Active"),
]


def _radgrid():
    """The shape of eproc.punjab.gov.pk: wrapper tables, a thead with a blank filter row,
    duplicate "title" headers, a pager table inside the data table, and the link label
    "( View Tender Detail )" sitting inside the title cell."""
    rows = ""
    for i, (stage, name, kind, pub, close, dept, status) in enumerate(TENDERS):
        rows += (f"<tr><td>{stage}</td>"
                 f"<td>{name} ( <a href='/TenderDetail.aspx?id={i}'>View Tender Detail</a> )</td>"
                 f"<td>{kind}</td><td>{pub}</td><td>{close}</td><td>{dept}</td><td>{status}</td>"
                 f"<td><a href='/notice/{i}.pdf'>Notice</a></td>"
                 f"<td><a href='/BiddingDocuments/{i}.pdf'>Download</a></td></tr>")
    return f"""<html><body>
      <table><tr><td>              <!-- page layout -->
        <table><tr><td>            <!-- panel layout -->
          <table><tr><td>          <!-- grid wrapper -->
            <table id="rdgrdManageTender" class="rgMasterTable">
              <thead>
                <tr class="rgHeader"><th>Procurement Title</th><th>Procurement Name</th>
                  <th>Type</th><th>Publish Date</th><th>Close Date</th><th>Department</th>
                  <th>Status</th><th>Tender Notice</th><th>Bidding Document</th></tr>
                <tr class="rgFilterRow"><td></td><td></td><td></td><td></td><td></td>
                  <td></td><td></td><td></td><td></td></tr>
              </thead>
              <tbody>{rows}</tbody>
              <tfoot><tr><td colspan="9">
                <table class="rgPager"><tr><td>1</td><td><a href="#">2</a></td></tr></table>
              </td></tr></tfoot>
            </table>
          </td></tr></table>
        </td></tr></table>
      </td></tr></table></body></html>"""


def test_the_data_grid_is_found_inside_its_wrappers():
    recs = extract_tables(_radgrid(), "https://eproc.punjab.gov.pk/ActiveTenders.aspx")
    assert len(recs) == len(TENDERS), "the grid inside the layout tables was missed"


def test_the_real_subject_is_used_as_the_title():
    """Not "Addendum"/"Tender"/"Corrigendum", which is what the first "title" column holds."""
    recs = extract_tables(_radgrid(), "https://eproc.punjab.gov.pk/ActiveTenders.aspx")
    titles = [r["title"] for r in recs]
    assert any("HAEMATOLOGY ANALYSERS" in t for t in titles), titles
    assert not any(t in ("Addendum", "Tender", "Corrigendum") for t in titles), titles


def test_the_link_label_is_not_part_of_the_title():
    recs = extract_tables(_radgrid(), "https://eproc.punjab.gov.pk/ActiveTenders.aspx")
    assert all("View Tender Detail" not in r["title"] for r in recs)


def test_the_other_columns_survive():
    recs = extract_tables(_radgrid(), "https://eproc.punjab.gov.pk/ActiveTenders.aspx")
    r = next(x for x in recs if "ELISA KITS" in x["title"])
    assert r["org"] == "Punjab Health Facilities Management Company"
    assert r["type"] == "Goods"
    assert r["published"] == "2026-10-01"
    assert r["closing"] == "2026-10-20"
    assert r["doc_url"].endswith(".pdf")


def test_the_pager_is_not_read_as_a_tender():
    recs = extract_tables(_radgrid(), "https://eproc.punjab.gov.pk/ActiveTenders.aspx")
    assert all("1" != r["title"] for r in recs)


def test_an_ordinary_table_is_unaffected():
    """The common case must keep working: one table, one header row, one title column."""
    html = ("<html><body><table>"
            "<tr><th>S.No</th><th>Tender Title</th><th>Procuring Agency</th><th>Closing Date</th></tr>"
            "<tr><td>1</td><td>Supply of laboratory reagents and controls</td>"
            "<td>Services Hospital</td><td>14-10-2026</td></tr>"
            "<tr><td>2</td><td>Annual maintenance of PCR thermal cyclers</td>"
            "<td>Services Hospital</td><td>21-10-2026</td></tr>"
            "</table></body></html>")
    recs = extract_tables(html, "https://example.test/")
    assert [r["title"] for r in recs] == ["Supply of laboratory reagents and controls",
                                          "Annual maintenance of PCR thermal cyclers"]
    assert recs[0]["org"] == "Services Hospital" and recs[0]["closing"] == "2026-10-14"


def test_a_short_title_column_is_kept_when_there_is_no_better_one():
    """The refinement must not invent a better column where none exists."""
    html = ("<html><body><table>"
            "<tr><th>Tender Title</th><th>Closing Date</th></tr>"
            "<tr><td>ELISA kits</td><td>14-10-2026</td></tr>"
            "<tr><td>PCR plates</td><td>21-10-2026</td></tr>"
            "</table></body></html>")
    recs = extract_tables(html, "https://example.test/")
    assert [r["title"] for r in recs] == ["ELISA kits", "PCR plates"]


# ------------------------------------------------------------------ pages that are link lists

def _news_list():
    """healthkp.gov.pk/news/tenders: every notice is a link to a detail page, each followed
    by an "Attachment : Download" link."""
    items = [
        (1257, "EVALUATION AGAINST MANDATORY CRITERIA IN RESPECT OF PROCUREMENT OF CONSULTANCY SERVICES"),
        (1255, "PROCUREMENT OF SERVICES FOR ACQUIRING VEHICLES ON A RENTAL BASIS"),
        (1256, "BID SOLICITATION DOCUMENTS (BSD) FOR NATIONAL COMPETITIVE BIDDING FOR MEDICAL EQUIPMENT"),
        (1254, "Invitation for bids for the renovation of the district laboratory"),
    ]
    body = "".join(
        f"<li><a href='/news/view/{i}'>{t}</a>"
        f"<a href='/public/uploads/news-{i}-notice.pdf'>Attachment : Download</a></li>"
        for i, t in items)
    return ("<html><body><a href='/news/tenders'>TENDERS</a>"
            f"<ul>{body}</ul></body></html>")


def test_a_list_of_links_is_read_as_tenders():
    recs = extract_links(_news_list(), "https://www.healthkp.gov.pk/news/tenders")
    titles = [r["title"] for r in recs]
    assert any("CONSULTANCY SERVICES" in t for t in titles)
    assert any("renovation of the district laboratory" in t for t in titles)


def test_a_bare_label_is_not_a_tender():
    recs = extract_links(_news_list(), "https://www.healthkp.gov.pk/news/tenders")
    assert all(r["title"].strip().lower() not in ("tenders", "attachment : download")
               for r in recs), [r["title"] for r in recs]


def test_a_repeated_field_label_is_stripped_and_the_reference_kept():
    """UNDP repeats its field labels inside each row: "Title <subject> Ref No <ref> ..."."""
    rows = "".join(
        f"<div class='row'>Title Procurement of laboratory equipment for lot {i} "
        f"Ref No UNDP-PAK-0080{i} Deadline : 18-Oct-2026 "
        f"<a href='/view_negotiation.cfm?nego_id=503{i}'>&raquo;</a></div>" for i in range(1, 5))
    recs = extract_links(f"<html><body>{rows}</body></html>", "https://procurement-notices.undp.org/")
    assert recs, "nothing was read"
    r = recs[0]
    assert r["title"].startswith("Procurement of laboratory equipment"), r["title"]
    assert r["ref"] == "UNDP-PAK-00801", r["ref"]
    assert r["closing"] == "2026-10-18"


def test_stray_links_on_a_front_page_are_not_tenders():
    """The exact false tenders this fallback produced: BPPRA's office address (its line
    mentions tenders) and the software vendor's URL on the Indus Hospital page."""
    html = ("<html><body>"
            "<div><a href='https://www.google.com/maps/place/Balochistan+Public+Procurement'>"
            "House # 2 Arbab Town Joint Road, Quetta-Pakistan</a> Tenders e-PPs</div>"
            "<div><a href='http://www.devexpress.com/purchase'>www.devexpress.com/purchase</a>"
            " - To purchase a license for these tender grids</div>"
            "<div><a href='https://bppra.gob.pk'>2026 Balochistan Public Procurement "
            "Regulatory Authority</a></div>"
            "</body></html>")
    assert extract_links(html, "https://www.bppra.gob.pk/") == []


def test_a_handful_of_pdf_notices_still_counts():
    """A small institution publishes two PDFs and nothing else; those must survive."""
    html = ("<html><body><ul>"
            "<li><a href='/docs/tender-reagents.pdf'>Tender notice: supply of reagents</a></li>"
            "<li><a href='/docs/tender-glassware.pdf'>Tender notice: supply of glassware</a></li>"
            "</ul></body></html>")
    recs = extract_links(html, "https://uhs.edu.pk/")
    assert len(recs) == 2, recs
