"""Build the trilingual manual's source inventory without importing engines.

Use --check in CI. Chapter coverage, public syntactic definitions, registered
operations and source hashes are derived from AST, not guessed from old counts.
The inventory is documentation, not a stability or validation certificate.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs/manuals"
META = MANUAL / "_meta"
REFERENCE = ROOT / "docs/reference/api"


def clean(text):
    return text.replace(chr(96), "").replace(chr(180), "")


def definition(node, module, notes, prefix=""):
    name = prefix + node.name
    if isinstance(node, ast.FunctionDef):
        signature = name + "(" + ast.unparse(node.args) + ")"
    else:
        signature = "class " + name
    source_description = ast.get_docstring(node)
    description = source_description or notes.get(module + "." + name)
    if not description:
        raise ValueError("Missing API documentation: " + module + "." + name)
    description = clean(description)
    return {
        "name": name,
        "line": node.lineno,
        "signature": signature,
        "description": description,
        "description_origin": "source_docstring"
        if source_description
        else "authored_manual_note",
        "fields": [
            clean(ast.unparse(field))
            for field in node.body
            if isinstance(field, ast.AnnAssign)
        ]
        if isinstance(node, ast.ClassDef)
        else [],
        "summary": description.split("\n\n")[0].replace("\n", " "),
    }


def products():
    chapters = json.loads((META / "coverage.json").read_text(encoding="utf-8"))
    notes_by_locale = {
        locale: json.loads(
            (REFERENCE / "notes" / (locale + ".json")).read_text(encoding="utf-8")
        )
        for locale in ("es", "en", "pt")
    }
    if any(
        set(value) != set(notes_by_locale["en"]) for value in notes_by_locale.values()
    ):
        raise ValueError("API note keys differ between languages")
    notes = notes_by_locale["en"]
    mapping = {}
    for chapter in chapters:
        if not all(
            (MANUAL / locale / chapter["file"]).is_file()
            for locale in ("es", "en", "pt")
        ):
            raise ValueError("Missing chapter: " + chapter["file"])
        for module in chapter["modules"]:
            if module in mapping:
                raise ValueError("Duplicate module ownership: " + module)
            mapping[module] = chapter
    paths = sorted((ROOT / "terraworkbench_core").glob("*.py"))
    if set(mapping) != {p.stem for p in paths}:
        raise ValueError(
            "Chapter/module coverage differs: "
            + str(set(mapping) ^ {p.stem for p in paths})
        )
    tree = ast.parse(
        (ROOT / "terraworkbench_core/operations.py").read_text(encoding="utf-8")
    )
    registry = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_OPERATIONS" for t in n.targets)
    )
    modules = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        members = []
        for node in tree.body:
            if isinstance(
                node, (ast.FunctionDef, ast.ClassDef)
            ) and not node.name.startswith("_"):
                members.append(definition(node, path.stem, notes))
                if isinstance(node, ast.ClassDef):
                    for method in node.body:
                        if isinstance(method, ast.FunctionDef) and (
                            not method.name.startswith("_") or method.name == "__init__"
                        ):
                            members.append(
                                definition(method, path.stem, notes, node.name + ".")
                            )
        operations = [
            {"id": key, "function": value[1], "domain": value[2], "extra": value[4]}
            for key, value in sorted(registry.items())
            if value[0] == path.stem
        ]
        available = {item["name"] for item in members}
        if any(op["function"] not in available for op in operations):
            raise ValueError("Registered function absent from AST: " + path.stem)
        modules.append(
            {
                "module": path.stem,
                "chapter": mapping[path.stem]["file"],
                "source_sha256": hashlib.sha256(
                    path.read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest(),
                "description": clean(
                    ast.get_docstring(tree) or "Infraestructura del paquete."
                ),
                "summary": clean(
                    (ast.get_docstring(tree) or "Infraestructura del paquete.")
                    .split("\n\n")[0]
                    .replace("\n", " ")
                ),
                "definitions": members,
                "operations": operations,
            }
        )
    used_notes = {
        m["module"] + "." + d["name"]
        for m in modules
        for d in m["definitions"]
        if d["description_origin"] == "authored_manual_note"
    }
    if used_notes != set(notes):
        raise ValueError(
            "Unused or missing authored API notes: " + str(used_notes ^ set(notes))
        )
    inventory = {
        "schema_version": 1,
        "scope": "AST inventory; not all definitions are stable user API or registered GUI processes",
        "source_hash_scheme": "sha256 UTF-8 source with LF newlines",
        "module_count": len(modules),
        "registered_operation_count": len(registry),
        "definition_count": sum(len(m["definitions"]) for m in modules),
        "modules": modules,
    }
    from scripts.documentation_layout import relative

    labels = {
        "es": (
            "Referencia de API e inventario verificable",
            "Índice del manual",
            "Módulo",
            "Capítulo",
            "Definiciones",
            "Operaciones registradas",
            "Fuente",
            "Operación",
            "Función",
            "Dominio",
            "Extra opcional",
            "Campos anotados en la clase",
            "Nota editorial basada en la implementación; no equivale a una nueva prueba científica.",
        ),
        "en": (
            "API reference and verifiable inventory",
            "Manual contents",
            "Module",
            "Chapter",
            "Definitions",
            "Registered operations",
            "Source",
            "Operation",
            "Function",
            "Domain",
            "Optional extra",
            "Annotated class fields",
            "Editorial implementation note; not a new scientific validation.",
        ),
        "pt": (
            "Referência de API e inventário verificável",
            "Índice do manual",
            "Módulo",
            "Capítulo",
            "Definições",
            "Operações registradas",
            "Fonte",
            "Operação",
            "Função",
            "Domínio",
            "Extra opcional",
            "Campos anotados na classe",
            "Nota editorial baseada na implementação; não é nova validação científica.",
        ),
    }
    introductions = {
        "es": "Documento generado desde el código. Las firmas, IDs y docstrings originales conservan su idioma técnico; las notas editoriales y navegación se localizan. Una dataclass puede generar un constructor: los campos anotados no implican que todos sean argumentos. Los defaults no son parámetros físicos recomendados. Las definiciones no equivalen a métodos científicos independientes ni garantizan API estable.",
        "en": "Generated from source. Signatures, IDs and original docstrings retain their technical language; editorial notes and navigation are localised. Dataclasses may generate constructors: annotated fields are not necessarily constructor arguments. Defaults are not recommended physical parameters. Definitions are not independent scientific-method counts or stable-API guarantees.",
        "pt": "Documento gerado do código. Assinaturas, IDs e docstrings originais preservam idioma técnico; notas editoriais e navegação são localizadas. Dataclasses podem gerar construtores: campos anotados não são necessariamente argumentos. Defaults não são parâmetros físicos recomendados. Definições não contam métodos científicos independentes nem garantem API estável.",
    }
    inventory["schema_version"] = 2
    inventory["editorial_note_language"] = "en"
    results = {
        "docs/reference/api/core_inventory.json": json.dumps(
            inventory, ensure_ascii=False, indent=2
        )
        + "\n"
    }
    for locale in ("es", "en", "pt"):
        L = labels[locale]
        lines = [
            "# " + L[0],
            "",
            "[English](en.md) · [Español](es.md) · [Português](pt.md)",
            "",
            "["
            + L[1]
            + "]("
            + relative(MANUAL / locale / "README.md", REFERENCE)
            + ")",
            "",
            introductions[locale],
            "",
            f"{inventory['module_count']} {L[2].lower()} · {inventory['definition_count']} {L[4].lower()} · {inventory['registered_operation_count']} {L[5].lower()}.",
            "",
            f"| {L[2]} | {L[3]} | {L[4]} | {L[5]} |",
            "| --- | --- | ---: | ---: |",
        ]
        for m in modules:
            lines.append(
                f"| {m['module']} | [{m['chapter'].split('_', 1)[0]}]({relative(MANUAL / locale / m['chapter'], REFERENCE)}) | {len(m['definitions'])} | {len(m['operations'])} |"
            )
        for m in modules:
            lines += [
                "",
                "## " + m["module"],
                "",
                m["description"],
                "",
                f"[{L[6]}]({relative(ROOT / 'terraworkbench_core' / (m['module'] + '.py'), REFERENCE)}) · [{L[3]}]({relative(MANUAL / locale / m['chapter'], REFERENCE)})",
                "",
            ]
            if m["operations"]:
                lines += [
                    f"| {L[7]} | {L[8]} | {L[9]} | {L[10]} |",
                    "| --- | --- | --- | --- |",
                ]
                lines += [
                    f"| {op['id']} | {op['function']} | {op['domain']} | {op['extra'] or 'base'} |"
                    for op in m["operations"]
                ]
                lines.append("")
            for item in m["definitions"]:
                description = item["description"]
                if item["description_origin"] == "authored_manual_note":
                    description = clean(
                        notes_by_locale[locale][m["module"] + "." + item["name"]]
                    )
                lines += [
                    "### " + item["name"],
                    "",
                    "    " + clean(item["signature"]),
                    "",
                    description,
                    "",
                ]
                if item["description_origin"] == "authored_manual_note":
                    lines += [L[12], ""]
                if item["fields"]:
                    lines += (
                        [L[11] + ":", ""]
                        + ["    " + field for field in item["fields"]]
                        + [""]
                    )
        results["docs/reference/api/" + locale + ".md"] = (
            "\n".join(lines).rstrip() + "\n"
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    import sys

    sys.path.insert(0, str(ROOT))
    for name, expected in products().items():
        path = ROOT / name
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                raise SystemExit("Stale manual reference: " + name)
        else:
            path.write_text(expected, encoding="utf-8")
    print("Manual reference and complete Core chapter coverage verified")


if __name__ == "__main__":
    main()
