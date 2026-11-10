"""Check full trilingual manuals, source references and scoped evidence."""

import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs/manuals"
LOCALES = ("es", "en", "pt")


def check():
    from scripts.build_manual_reference import products
    from scripts.build_manual_figures import asset_sha256
    from scripts.build_manual_localization import product
    from scripts.check_documentation import check as check_links

    errors = []
    for name, expected in products().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            errors.append("Outdated generated reference: " + name)
    record = product()
    recorded = MANUAL / "_meta/localization.json"
    if (
        not recorded.exists()
        or json.loads(recorded.read_text(encoding="utf-8")) != record
    ):
        errors.append(
            "Outdated translation/source hashes: review and regenerate localization record"
        )
    chapters = record["chapters"]
    figures = 0
    for locale in LOCALES:
        localized_figures = 0
        for path in (MANUAL / locale).glob("*.md"):
            content = path.read_text(encoding="utf-8")
            if any(character in content for character in (chr(96), chr(180), chr(12))):
                errors.append(
                    "Forbidden document character: " + str(path.relative_to(ROOT))
                )
            if re.search(
                r"(?<![A-Za-z])[A-Za-z]:[\\/]|C:[/]+Users/|Woodlawn|Mitchinson", content
            ):
                errors.append(
                    "Private/local case marker: " + str(path.relative_to(ROOT))
                )
            if path.name[:2].isdigit():
                if "README.md)" not in content or any(
                    f"../{key}/{path.name}" not in content for key in LOCALES
                ):
                    errors.append(
                        "Missing chapter/language navigation: "
                        + str(path.relative_to(ROOT))
                    )
                localized_figures += len(
                    re.findall(r"^(?:Figura|Figure) \d+\.", content, re.M)
                )
        if localized_figures != 6:
            errors.append(
                f"Expected six numbered figures in {locale}, got {localized_figures}"
            )
        figures += localized_figures
        assets = MANUAL / "assets" / locale
        manifest = json.loads((assets / "figuras.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if asset_sha256(assets / name) != expected:
                errors.append(f"Figure hash differs: {locale}/{name}")
        for path in assets.glob("*.png"):
            header = path.read_bytes()[:24]
            if (
                not header.startswith(b"\x89PNG\r\n\x1a\n")
                or min(struct.unpack(">II", header[16:24])) < 200
            ):
                errors.append("Invalid/small PNG: " + str(path.relative_to(ROOT)))
    if len(chapters) != 28:
        errors.append("Expected 28 chapters per locale")
    for chapter in chapters:
        source = chapter["versions"]["es"]
        for locale in ("en", "pt"):
            translated = chapter["versions"][locale]
            for field in (
                "source_modules",
                "external_urls",
                "images",
                "sections",
                "table_rows",
            ):
                if translated[field] != source[field]:
                    errors.append(
                        f"Translation {field} differs: {locale}/{chapter['file']}"
                    )
            if (
                translated["words"] < source["words"] * 0.5
                or translated["sections"] < source["sections"] - 1
            ):
                errors.append(
                    f"Translation appears incomplete: {locale}/{chapter['file']}"
                )
    if list(MANUAL.rglob("*.pdf")):
        errors.append("PDFs do not belong to this Markdown manual")
    examples = json.loads((MANUAL / "_meta/examples.json").read_text(encoding="utf-8"))
    for case in examples["cases"]:
        source = ROOT / case["source"]
        if (
            hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            != case["source_sha256_lf"]
        ):
            errors.append("Teaching example changed since execution: " + case["id"])
    captures = json.loads((MANUAL / "_meta/captures.json").read_text(encoding="utf-8"))
    for filename, expected in captures["files"].items():
        if hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() != expected:
            errors.append("Capture hash differs: " + filename)
    for filename, expected in captures["ui_sources_sha256_lf"].items():
        if (
            hashlib.sha256(
                (ROOT / filename).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            != expected
        ):
            errors.append("Capture UI source changed: " + filename)
    identifiers = None
    for locale in LOCALES:
        catalog = json.loads(
            (ROOT / f"docs/reference/catalogues/qgis_{locale}.json").read_text(
                encoding="utf-8"
            )
        )
        current = [entry["id"] for entry in catalog["algorithms"]]
        if len(current) != len(set(current)) or (
            identifiers is not None and current != identifiers
        ):
            errors.append("QGIS catalogue IDs differ or duplicate: " + locale)
        identifiers = current
    links = check_links()
    errors.extend(links["errors"])
    return {
        "chapters": len(chapters),
        "locales": list(LOCALES),
        "numbered_figures": figures,
        "local_links_checked": links["links"],
        "errors": errors,
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT))
    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report["errors"]))
