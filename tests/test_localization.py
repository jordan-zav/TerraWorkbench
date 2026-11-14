"""Host-free language coverage, handbook parity and stable API-ID checks."""

import ast
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_i18n_has_no_question_marks_inside_words():
    """Catch lossy shell encoding, while allowing punctuation and regex syntax."""
    source = (ROOT / "ui/i18n.py").read_bytes()
    assert not source.startswith(b'\xef\xbb\xbf')
    content = source.decode('utf-8')
    assert not re.search(r'[^\W\d_]\?[^\W\d_]', content), 'Question mark inside a word in i18n.py'
    assert 'Prévia ao vivo' in content
    assert '"Preview": "Prévia"' in content


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def literal_assignment(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )


def test_authored_ui_translations_and_placeholders():
    checker = load_file("tw_localization_check", ROOT / "scripts/check_localization.py")
    report = checker.audit()
    assert report["sources"] >= 500
    assert report["direct_triples"] >= 100
    assert not report["errors"], "\n".join(report["errors"])


def test_core_titles_cover_exact_registered_ids_and_families():
    operations = literal_assignment(
        ROOT / "terraworkbench_core/operations.py", "_OPERATIONS"
    )
    titles = literal_assignment(ROOT / "ui/core_presentation.py", "OPERATION_TITLES")
    families = literal_assignment(ROOT / "ui/core_presentation.py", "CHAPTER_BY_FAMILY")
    domains = literal_assignment(ROOT / "ui/core_presentation.py", "DOMAIN_TITLES")
    assert {entry[2] for entry in operations.values()} <= set(domains)
    assert set(titles) == set(operations)
    for key, translations in titles.items():
        assert key.split(".")[0] in families
        assert len(translations) == 3 and all(t.strip() for t in translations)


def test_handbook_has_equivalent_sections_equations_and_links():
    handbook = load_file("tw_handbook", ROOT / "ui/knowledge_content.py")
    assert len(handbook.CHAPTERS) >= 15
    assert len({c[0] for c in handbook.CHAPTERS}) == len(handbook.CHAPTERS)
    for chapter_id, titles, bodies, equation, references in handbook.CHAPTERS:
        assert len(titles) == len(bodies) == 3
        assert references and all(key in handbook.REFERENCES for key in references)
        documents = [
            handbook.chapter_text(chapter_id, lang) for lang in handbook.LANGUAGES
        ]
        assert all(len(body.split()) >= 55 for body in bodies)
        links = [re.findall(r"https://[^)]+", doc) for doc in documents]
        assert links[0] == links[1] == links[2]
        assert all(equation in doc for doc in documents)
        assert all("\ufffd" not in doc for doc in documents)
        for body in bodies:
            assert 0.55 < len(body) / len(bodies[0]) < 1.8


def test_new_ui_resources_are_packaged():
    packager = (ROOT / "scripts/package_plugin.py").read_text(encoding="utf-8")
    for name in (
        "ui/knowledge_content.py",
        "ui/knowledge_methods.py",
        "ui/core_presentation.py",
        "ui/core_parameter_schema.py",
        "ui/core_field_editor.py",
        "ui/depth_grid_parameter_form.py",
        "ui/npz_inspector.py",
        "ui/parameter_json.py",
    ):
        assert f'"{name}"' in packager


def test_detailed_methods_are_equivalent_and_visible_in_each_language():
    handbook = load_file("tw_detailed_handbook", ROOT / "ui/knowledge_content.py")
    assert len(handbook.METHODS) >= 25
    assert len({m[0] for m in handbook.METHODS}) == len(handbook.METHODS)
    for _, chapter, titles, notes, formula, parameters in handbook.METHODS:
        assert parameters and len(titles) == len(notes) == 3
        assert all(len(note.split()) >= 45 for note in notes)
        for index, locale in enumerate(handbook.LANGUAGES):
            doc = handbook.chapter_text(chapter, locale)
            assert titles[index] in doc and notes[index] in doc
            assert formula in doc and all(name in doc for name in parameters)


def test_portable_handbooks_match_the_ui_source():
    exporter = load_file("tw_handbook_export", ROOT / "scripts/export_handbook.py")
    for locale in ("en", "es", "pt"):
        path = ROOT / "docs/handbook" / f"handbook_{locale}.md"
        text = path.read_text(encoding="utf-8")
        assert text == exporter.render(locale)
        assert "\x60" not in text and "\u00b4" not in text


def test_method_sources_have_complete_scope_and_render_in_both_formats():
    handbook = load_file("tw_citation_handbook", ROOT / "ui/knowledge_content.py")
    assert set(handbook.METHOD_REFERENCES) == {m[0] for m in handbook.METHODS}
    for method_id, chapter, *_ in handbook.METHODS:
        keys = handbook.METHOD_REFERENCES[method_id]
        assert keys and len(keys) == len(set(keys))
        for locale in handbook.LANGUAGES:
            sources = handbook.method_sources(method_id, locale)
            markdown = handbook.chapter_text(chapter, locale)
            html = handbook.chapter_html(chapter, locale)
            assert sources in markdown
            assert sources.split("\n\n", 1)[0] in html
            for key in keys:
                url = handbook.REFERENCES[key][1]
                assert url.startswith("https://") and url in markdown and url in html
    assert "well_survey" in handbook.METHOD_REFERENCES["borehole_depth"]
    assert set(handbook.METHOD_REFERENCES["werner_spi_spectrum"]) == {
        "werner",
        "spi",
        "spectral_depth",
    }


def test_citation_manifest_matches_the_authored_content():
    import json

    handbook = load_file("tw_manifest_handbook", ROOT / "ui/knowledge_content.py")
    manifest = json.loads(
        (ROOT / "docs/handbook/handbook_sources.json").read_text(encoding="utf-8")
    )
    assert manifest["methods"] == {
        key: list(value) for key, value in handbook.METHOD_REFERENCES.items()
    }
    assert manifest["references"] == {
        key: {"title": title, "url": url}
        for key, (title, url) in handbook.REFERENCES.items()
    }
