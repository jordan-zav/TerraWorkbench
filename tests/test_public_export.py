"""Manifest and ZIP boundaries must reject private material, including regressions."""

import json
import hashlib
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import package_plugin
from scripts.export_public import check_imports, export
from scripts.public_files import content_findings, read_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_keeps_runtime_index_and_public_export_keeps_provenance(tmp_path):
    manifest = read_manifest(ROOT)
    included = {p.relative_to(ROOT).as_posix() for p in package_plugin.package_files()}
    excluded = {p for p in manifest if not package_plugin.runtime_document(p)}
    assert excluded
    assert "docs/manuals/_meta/coverage.json" in included
    assert all(p not in included for p in excluded)
    files, _ = export(tmp_path / "public")
    assert excluded <= set(files)
    for relative in excluded:
        assert (tmp_path / "public" / relative).read_bytes() == (ROOT / relative).read_bytes()
    # Runtime navigation metadata is hash-free; retain it byte for byte.
    import re
    assert not re.search(r"[a-f0-9]{64}", (ROOT / "docs/manuals/_meta/coverage.json").read_text())


@pytest.mark.parametrize("cells,percent", [(9, 1), (100, 10), (123, 17.5), (10000, 35)])
def test_equivalent_source_holdout_matches_previous_implementation(cells, percent):
    import ast
    import numpy as np

    source = ast.parse((ROOT / "algorithms/equivalent_sources.py").read_text())
    branch = next(node for node in ast.walk(source) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "holdout_percent > 0.0")
    # Execute the real sampling statements without importing the QGIS adapter.
    statements = ast.Module(body=branch.body[:5], type_ignores=[])
    values = {"np": np, "cells": cells, "holdout_percent": percent}
    exec(compile(statements, "holdout", "exec"), values)
    random = np.random.default_rng(0)
    count = max(1, int(round(cells * percent / 100.0)))
    expected = np.sort(random.choice(cells, count, replace=False))
    np.testing.assert_array_equal(values["holdout"], expected)
    training = np.ones(cells, dtype=bool)
    training[expected] = False
    np.testing.assert_array_equal(values["training"], training)


def test_public_zip_rejects_unlisted_editorial_and_local_content(tmp_path, monkeypatch):
    monkeypatch.setattr(package_plugin, "DIST_DIR", tmp_path / "dist")
    archive = package_plugin.build_archive()
    assert not package_plugin.validate_archive(archive, package_plugin.current_version())
    files = set(read_manifest(ROOT))
    with ZipFile(archive) as bundle:
        assert all(name.removeprefix("TerraWorkbench/") in files for name in bundle.namelist())
        assert not any(("docs/" + "publication/") in name for name in bundle.namelist())
    with ZipFile(archive, "a") as bundle:
        bundle.writestr("TerraWorkbench/docs/" + "publication/draft.md", b"private draft")
        bundle.writestr("TerraWorkbench/unlisted.txt", ("N" + ":/private/session").encode())
    errors = package_plugin.validate_archive(archive, package_plugin.current_version())
    assert any("outside public manifest" in message for message in errors)
    assert any("local_location" in message for message in errors)


def test_public_export_resolves_imports_and_retains_confirmed_tellus(tmp_path):
    destination = tmp_path / "public"
    files, _ = export(destination)
    assert not check_imports(destination, files)
    findings = [finding for relative in files for finding in content_findings(relative, (destination / relative).read_bytes())]
    assert not findings, findings
    catalogue = json.loads((destination / "scripts/public_processing_sources.json").read_text(encoding="utf-8"))
    assert all(value.get("rights_confirmed", True) for value in catalogue.values())
    from scripts.tellus_a9 import TELLUS_A9_ATTRIBUTION

    assert catalogue["tellus"]["rights_confirmed"] is True
    assert catalogue["tellus"]["enabled_by_default"] is True
    assert catalogue["tellus"]["attribution"] == TELLUS_A9_ATTRIBUTION
    assert "scripts/tellus_a9.py" in files
    assert "scripts/private_tellus.py" not in files
    with pytest.raises(ValueError, match="new output"):
        export(destination)


@pytest.mark.parametrize("entry", ["../outside", "AGENTS.md", "docs/" + "publication/draft.md", "assets/branding/logo.psd"])
def test_manifest_refuses_forbidden_paths_even_if_added_by_accident(tmp_path, entry):
    (tmp_path / "public_manifest.txt").write_text(entry + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_manifest(tmp_path)


def test_unconfirmed_case_requires_explicit_development_opt_in(tmp_path, monkeypatch):
    from scripts import benchmark_public_processing as benchmark

    # Retain the generic rights gate even though A9 is now confirmed.
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({"blocked": {"enabled_by_default": False,
                                             "rights_confirmed": False}}))
    monkeypatch.setattr(benchmark, "MANIFEST", sources)
    monkeypatch.setattr(benchmark, "CASE_DATASETS", {"restricted": ("blocked",)})
    with pytest.raises(ValueError, match="rights are unconfirmed"):
        benchmark.run(tmp_path / "cache", tmp_path / "run", offline=True,
                      cases=["restricted"])


def test_default_campaign_never_fetches_unconfirmed_inputs(tmp_path, monkeypatch):
    from scripts import benchmark_public_processing as benchmark

    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({"open": {"enabled_by_default": True},
                                   "blocked": {"enabled_by_default": False}}))
    monkeypatch.setattr(benchmark, "MANIFEST", sources)
    monkeypatch.setattr(benchmark, "CASE_DATASETS", {"ok": ("open",), "restricted": ("blocked",)})
    monkeypatch.setattr(benchmark, "CASES", {"ok": lambda *_: {"passed": True},
                                            "restricted": lambda *_: pytest.fail("Restricted case ran")})
    fetched = []

    def fetch(cache, source, offline=False):
        assert source["enabled_by_default"]
        fetched.append(source)
        return tmp_path / "open.bin"

    monkeypatch.setattr(benchmark, "fetch", fetch)
    report = benchmark.run(tmp_path / "cache", tmp_path / "run", offline=True)
    assert set(report["cases"]) == {"ok"}
    assert len(fetched) == 1


def test_archive_provenance_never_requires_git_or_inherits_an_ancestor(tmp_path, monkeypatch):
    from scripts import public_files

    manifest = tmp_path / "public_manifest.txt"
    manifest.write_bytes(b"public source snapshot\n")

    def refuse_git(*args, **kwargs):
        pytest.fail("An archive must not query Git in an ancestor directory")

    monkeypatch.setattr(public_files.subprocess, "run", refuse_git)
    record = public_files.repository_provenance(tmp_path)
    assert record["mode"] == "archive"
    assert record["commit"] is None and record["dirty"] is None
    assert record["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_confirmed_tellus_routes_by_default_without_opt_in(tmp_path, monkeypatch):
    from scripts import benchmark_public_processing as benchmark
    from scripts.tellus_a9 import TELLUS_A9_ATTRIBUTION

    source = json.loads(benchmark.MANIFEST.read_text(encoding="utf-8"))["tellus"]
    assert source["rights_confirmed"] and source["enabled_by_default"]
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({"tellus": source}), encoding="utf-8")
    monkeypatch.setattr(benchmark, "MANIFEST", sources)
    monkeypatch.setattr(benchmark, "CASE_DATASETS", {"radiometry": ("tellus",)})
    monkeypatch.setattr(benchmark, "CASES", {"radiometry": lambda *_: {"passed": True}})
    monkeypatch.setattr(benchmark, "fetch", lambda *_a, **_kw: tmp_path / "pinned.zip")
    report = benchmark.run(tmp_path / "cache", tmp_path / "run", offline=True)
    assert report["cases"]["radiometry"]["status"] == "passed"
    assert report["datasets"]["tellus"]["attribution"] == TELLUS_A9_ATTRIBUTION
