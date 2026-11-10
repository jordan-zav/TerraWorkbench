"""Generate equivalent portable Markdown manuals from the authored UI source."""

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def content_module():
    spec = importlib.util.spec_from_file_location(
        "tw_knowledge_content", ROOT / "ui/knowledge_content.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(locale):
    content = content_module()
    index = content.LANGUAGES.index(locale)
    title = (
        "TerraWorkbench practical handbook",
        "Manual práctico de TerraWorkbench",
        "Manual prático do TerraWorkbench",
    )[index]
    note = (
        "The same chapters, equations and primary links are available in English, Spanish and Portuguese. Historical potential-field references remain available separately. This handbook describes assumptions and QA; it is not a claim of complete discipline coverage or field validation.",
        "Los mismos capítulos, ecuaciones y enlaces primarios están disponibles en inglés, español y portugués. Las referencias históricas de campos potenciales se conservan por separado. Este manual documenta supuestos y controles; no afirma cobertura completa ni validación de campo.",
        "Os mesmos capítulos, equações e links primários estão disponíveis em inglês, espanhol e português. As referências históricas de campos potenciais são preservadas separadamente. Este manual documenta hipóteses e controles; não afirma cobertura completa nem validação de campo.",
    )[index]
    chapters = []
    for chapter in content.CHAPTERS:
        chapters.append(
            "#" + content.chapter_text(chapter[0], locale).replace("\n## ", "\n### ")
        )
    return "# " + title + "\n\n" + note + "\n\n" + "\n\n".join(chapters) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failed = []
    content = content_module()
    manifest = {
        "schema_version": 1,
        "scope": "Method context, not independent validation or license audit",
        "references": {
            key: {"title": title, "url": url}
            for key, (title, url) in content.REFERENCES.items()
        },
        "methods": content.METHOD_REFERENCES,
    }
    manifest_path = ROOT / "docs/handbook/handbook_sources.json"
    expected_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if (
            not manifest_path.is_file()
            or manifest_path.read_text(encoding="utf-8") != expected_manifest
        ):
            failed.append(str(manifest_path))
    else:
        manifest_path.write_text(expected_manifest, encoding="utf-8")
    for locale in ("en", "es", "pt"):
        path = ROOT / "docs/handbook" / ("handbook_" + locale + ".md")
        expected = render(locale)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                failed.append(str(path))
        else:
            path.write_text(expected, encoding="utf-8")
    if failed:
        print("Handbook exports differ: " + ", ".join(failed))
        return 1
    print("Handbooks: EN/ES/PT synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
