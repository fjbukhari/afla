"""A typo in a hand-edited settings file must be explained, not thrown as a traceback.

Reported from the office PC: `tw push`, after the website lines were pasted into
config\\settings.yaml, ended in twenty-five lines of Python finishing with

    yaml.scanner.ScannerError: while scanning a simple key
      in "<unicode string>", line 45, column 1:
        —

A stray em dash had come along with the paste. The cause is a single character on one line of
one file, and the person reading the screen is not a Python programmer.
"""
import pytest

from tw import settings as S

PASTED_WITH_A_DASH = """\
headless: true
page_delay_seconds: 2.5

—

website:
  api_url: https://www.jb-scientific.com/catalogue/staff/tenders/api.php
"""

TAB_INSTEAD_OF_SPACES = "website:\n\tapi_url: https://example.test/api.php\n"
MISSING_COLON = "headless: true\nwebsite\n  api_url: https://example.test/api.php\n"


@pytest.mark.parametrize("bad", [PASTED_WITH_A_DASH, TAB_INSTEAD_OF_SPACES, MISSING_COLON])
def test_a_typo_is_explained_in_plain_words(tmp_path, monkeypatch, bad):
    p = tmp_path / "settings.yaml"
    p.write_text(bad, encoding="utf-8")
    monkeypatch.setattr(S, "CONFIG_DIR", tmp_path)
    with pytest.raises(SystemExit) as e:
        S.load_settings()
    msg = str(e.value)
    assert "settings.yaml" in msg
    assert "Notepad" in msg
    assert "Traceback" not in msg and "yaml.scanner" not in msg


def test_the_message_names_the_line_that_is_wrong(tmp_path, monkeypatch):
    p = tmp_path / "settings.yaml"
    p.write_text(PASTED_WITH_A_DASH, encoding="utf-8")
    monkeypatch.setattr(S, "CONFIG_DIR", tmp_path)
    with pytest.raises(SystemExit) as e:
        S.load_settings()
    msg = str(e.value)
    # YAML complains about line 6, where it gave up; the dash that caused it is on line 4,
    # and that is the line the person has to delete, so it must be the one shown.
    assert "line 4" in msg, msg
    assert "—" in msg, msg


def test_a_good_file_still_loads(tmp_path, monkeypatch):
    p = tmp_path / "settings.yaml"
    p.write_text("headless: false\nwebsite:\n  api_url: https://example.test/api.php\n", encoding="utf-8")
    monkeypatch.setattr(S, "CONFIG_DIR", tmp_path)
    st = S.load_settings()
    assert st["headless"] is False
    assert st["website"]["api_url"] == "https://example.test/api.php"
    assert st["max_pages"] == S.DEFAULTS["max_pages"]      # defaults still applied


def test_a_broken_portal_list_is_explained_too(tmp_path, monkeypatch):
    (tmp_path / "sources.yaml").write_text("sources:\n  - id: x\n   name: bad indent\n", encoding="utf-8")
    monkeypatch.setattr(S, "CONFIG_DIR", tmp_path)
    with pytest.raises(SystemExit) as e:
        S.load_sources()
    assert "portals" in str(e.value) and "sources.yaml" in str(e.value)
