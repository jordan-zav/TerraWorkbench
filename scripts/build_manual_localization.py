"""Freeze chapter/source parity for the three complete manuals."""

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs/manuals"
LOCALES = ("es", "en", "pt")


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def product():
    chapters = json.loads((MANUAL / "_meta/coverage.json").read_text(encoding="utf-8"))
    records = []
    for chapter in chapters:
        versions = {}
        for locale in LOCALES:
            path = MANUAL / locale / chapter["file"]
            content = path.read_text(encoding="utf-8")
            versions[locale] = {
                "sha256_lf": digest(path),
                "words": len(content.split()),
                "sections": len(re.findall(r"^## ", content, re.M)),
                "images": len(re.findall(r"!\[", content)),
                "table_rows": len(re.findall(r"^\|", content, re.M)),
                "source_modules": sorted(
                    set(re.findall(r"terraworkbench_core/([\w]+\.py)", content))
                ),
                "external_urls": sorted(set(re.findall(r"https?://[^\s)]+", content))),
            }
        records.append({"file": chapter["file"], "versions": versions})
    return {
        "schema_version": 1,
        "scope": "28 complete chapters per locale; translated prose and editorial notes; original API docstrings and historical reports retain their language",
        "hash_scheme": "sha256 of UTF-8 files normalized to LF",
        "source_locale": "es",
        "review": "Authored translations share chapter IDs, figures, implementation targets and scientific caveats. Structural checks detect drift; they do not certify translation semantics.",
        "chapters": records,
        "supporting_documents": {
            f"{locale}/{name}": digest(MANUAL / locale / name)
            for locale in LOCALES
            for name in ("README.md", "fuentes.md")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = MANUAL / "_meta/localization.json"
    expected = json.dumps(product(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            raise SystemExit(
                "Manual localization record is stale; review translations and regenerate"
            )
    else:
        target.write_text(expected, encoding="utf-8")


if __name__ == "__main__":
    main()
