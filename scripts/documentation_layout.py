"""Canonical documentation locations shared by generators and validators."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MANUALS = DOCS / "manuals"
META = MANUALS / "_meta"
API = DOCS / "reference/api"
LOCALES = ("es", "en", "pt")


def chapters():
    return json.loads((META / "coverage.json").read_text(encoding="utf-8"))


def relative(target, parent):
    return os.path.relpath(target, parent).replace("\\", "/")
