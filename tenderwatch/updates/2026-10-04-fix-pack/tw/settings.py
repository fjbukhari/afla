"""Load config/settings.yaml (optional) and config/sources.yaml."""
import os
import sys

import yaml

from . import CONFIG_DIR, DATA_DIR

DEFAULTS = {
    # On Windows we drive the Microsoft Edge that is already installed, so no browser download is needed.
    "browser_channel": "msedge" if sys.platform == "win32" else "",
    "headless": True,
    "page_delay_seconds": 2.5,
    "page_timeout_seconds": 60,
    "max_pages": 25,
    "profile_dir": str(DATA_DIR / "browser-profile"),
    "dashboard_port": 8766,
    "keep_closed_days": 60,
    "team": [],
    "catalogue_url": "https://www.jb-scientific.com/catalogue/jbs-catalog.html",
    "read_documents": True,
    "email": {},
}


def _read_yaml(path, what):
    """Read a settings file, and explain a typo instead of printing a Python traceback.

    These files are edited by hand in Notepad, and one stray character - a dash left behind
    when pasting, a missing colon, a tab instead of spaces - stopped the program with twenty
    lines of Python ending in "could not find expected ':'". That says nothing about which
    file, which line, or what to do about it.
    """
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        lines = text.splitlines()

        def show(mark):
            if mark is None:
                return ""
            n = mark.line + 1
            if mark.line < len(lines):
                return f"\n  line {n}: {lines[mark.line]!r}"
            return f"\n  line {n}"

        # YAML reports two places: where it gave up (problem_mark) and where the thing it could
        # not finish began (context_mark). The mistake is almost always at the second one - the
        # stray dash was on line 45 and the complaint pointed at line 46 - so that is shown first.
        ctx, prob = getattr(e, "context_mark", None), getattr(e, "problem_mark", None)
        where = show(ctx) + show(prob) if ctx is not None and (
            prob is None or ctx.line != prob.line) else show(prob or ctx)
        problem = getattr(e, "problem", None) or "the file could not be read"
        raise SystemExit(
            f"\nThere is a mistake in {what}:\n  {path}{where}\n"
            f"  the problem: {problem}\n\n"
            "Open that file in Notepad and look at the lines above. The usual causes are a stray\n"
            "character left behind when pasting (a dash, a bullet, a smart quote), a missing\n"
            "colon after a name, or a tab where there should be spaces - YAML allows spaces only.\n"
            "Each setting is  name: value , and a setting inside another is indented two spaces:\n\n"
            "    website:\n"
            "      api_url: https://www.jb-scientific.com/catalogue/staff/tenders/api.php\n\n"
            "Delete the offending line if you are not sure what it was meant to be, save, and\n"
            "run the command again. Nothing else is changed until this file reads correctly."
        ) from None


def load_settings():
    s = dict(DEFAULTS)
    p = CONFIG_DIR / "settings.yaml"
    if p.exists():
        s.update(_read_yaml(p, "your settings file"))
    if os.environ.get("TW_HEADLESS") in ("0", "1"):
        s["headless"] = os.environ["TW_HEADLESS"] == "1"
    return s


def load_sources(only=None, include_disabled=False):
    data = _read_yaml(CONFIG_DIR / "sources.yaml", "the list of portals")
    out = []
    for s in data["sources"]:
        if only and s["id"] not in only:
            continue
        if not only and s.get("enabled", True) is False and not include_disabled:
            continue
        out.append(s)
    if only:
        missing = set(only) - {s["id"] for s in out}
        if missing:
            raise SystemExit(f"Unknown source id(s): {', '.join(sorted(missing))}. See config/sources.yaml")
    return out
