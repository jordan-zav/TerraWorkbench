"""Audit authored UI strings without importing Qt, QGIS or optional engines.

Technical API IDs, user data, external-library messages and original developer
docstrings are not translated by this check. Runtime construction is tested
separately by qgis_localization_smoke.py.
"""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def load_catalog():
    tree = ast.parse((ROOT / "ui/i18n.py").read_text(encoding="utf-8"))
    # Dictionary construction has no Qt dependencies. Preferences are never read
    # or written: keep definitions, but do not invoke language()/set_language().
    tree.body = [node for node in tree.body if not isinstance(node, ast.ImportFrom)]
    namespace = {}
    exec(compile(tree, "localization-catalog", "exec"), namespace)
    return namespace


def placeholders(value):
    return set(re.findall(r"\{([A-Za-z_]\w*)(?::[^{}]*)?\}", value))


def constant_strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return constant_strings(node.body) + constant_strings(node.orelse)
    return []


def validate_triplet(values):
    if len(values) != 3 or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        return False
    return all(
        "\ufffd" not in value and placeholders(value) == placeholders(values[0])
        for value in values
    )


def audit_data_catalogues():
    errors = []
    count = 0
    for name in (
        "ui/core_parameter_schema.py",
        "ui/core_field_editor.py",
        "ui/core_parameter_form.py",
        "ui/core_job_dialog.py",
        "ui/core_presentation.py",
        "ui/knowledge_content.py",
        "ui/knowledge_methods.py",
    ):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for value in node.values:
                if (
                    isinstance(value, ast.Tuple)
                    and len(value.elts) == 3
                    and all(
                        isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in value.elts
                    )
                ):
                    count += 1
                    if not validate_triplet([e.value for e in value.elts]):
                        errors.append(
                            f"{name}:{value.lineno}: invalid data-driven translations"
                        )
    return count, errors


def audit():
    catalog = load_catalog()
    errors = []
    source_count = set()
    triple_count = 0
    for path in sorted(
        list(ROOT.glob("*.py"))
        + list((ROOT / "qgis_plugin").glob("*.py"))
        + list((ROOT / "algorithms").glob("*.py"))
        + list((ROOT / "ui").glob("*.py"))
    ):
        if path.name == "ui/i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name not in ("text", "tr", "translate"):
                continue
            where = f"{path.relative_to(ROOT)}:{node.lineno}"
            if isinstance(node.args[0], ast.JoinedStr):
                errors.append(where + ": format after translation, not before")
            sources = constant_strings(node.args[0])
            if not sources:
                continue  # separately audited data-driven catalogues
            direct = [constant_strings(arg) for arg in node.args]
            for source in sources:
                source_count.add(source)
                if len(node.args) >= 3 and all(len(v) == 1 for v in direct[:3]):
                    translations = [v[0] for v in direct[:3]]
                    triple_count += 1
                else:
                    spanish = catalog["_ES"].get(source)
                    if len(direct) == 2 and len(direct[1]) == len(sources):
                        spanish = direct[1][sources.index(source)]
                    portuguese = catalog["_PT_EXACT"].get(source)
                    translations = [source, spanish, portuguese]
                for locale, value in zip(("en", "es", "pt"), translations):
                    if not value:
                        errors.append(f"{where}: missing authored {locale}: {source}")
                    elif "\ufffd" in value or placeholders(value) != placeholders(
                        source
                    ):
                        errors.append(
                            f"{where}: invalid text/placeholders in {locale}: {source}"
                        )
    data_count, data_errors = audit_data_catalogues()
    errors.extend(data_errors)
    return {
        "sources": len(source_count),
        "direct_triples": triple_count,
        "data_triples": data_count,
        "errors": errors,
    }


def main():
    report = audit()
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
