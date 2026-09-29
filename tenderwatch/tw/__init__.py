"""Tender Watch 2: collects tenders from public and logged-in procurement portals."""
from pathlib import Path

__version__ = "2.0.0"

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
