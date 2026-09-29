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


def load_settings():
    s = dict(DEFAULTS)
    p = CONFIG_DIR / "settings.yaml"
    if p.exists():
        s.update(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    if os.environ.get("TW_HEADLESS") in ("0", "1"):
        s["headless"] = os.environ["TW_HEADLESS"] == "1"
    return s


def load_sources(only=None, include_disabled=False):
    data = yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text(encoding="utf-8"))
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
