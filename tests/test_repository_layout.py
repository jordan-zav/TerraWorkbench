"""Packaged imports and resource paths survive the repository UI split."""

import ast
import importlib.util
from pathlib import Path
from zipfile import ZipFile

from scripts import package_plugin

ROOT = Path(__file__).resolve().parents[1]


def test_root_has_only_the_qgis_python_entry_point():
    assert {path.name for path in ROOT.glob("*.py")} == {"__init__.py"}


def test_relative_imports_resolve_to_packaged_python_modules():
    packaged = {
        path.relative_to(ROOT).as_posix()
        for path in package_plugin.package_files()
        if path.suffix == ".py"
    }
    for relative in sorted(packaged):
        path = ROOT / relative
        package = list(path.relative_to(ROOT).parent.parts)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (
                not isinstance(node, ast.ImportFrom)
                or not node.level
                or not node.module
            ):
                continue
            assert node.level <= len(package) + 1, (relative, node.lineno)
            base = package[: len(package) - node.level + 1]
            module = "/".join(base + node.module.split("."))
            assert module + ".py" in packaged or module + "/__init__.py" in packaged, (
                relative,
                node.lineno,
                module,
            )


def test_installed_ui_paths_find_bundled_resources(tmp_path, monkeypatch):
    monkeypatch.setattr(package_plugin, "DIST_DIR", tmp_path / "dist")
    archive = package_plugin.build_archive()
    assert not package_plugin.validate_archive(
        archive, package_plugin.current_version()
    )
    installed = tmp_path / "installed"
    with ZipFile(archive) as bundle:
        bundle.extractall(installed)
    helper = installed / "TerraWorkbench/ui/_paths.py"
    spec = importlib.util.spec_from_file_location("tw_installed_ui_paths", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PLUGIN_ROOT == installed / "TerraWorkbench"
    for relative in (
        "assets/branding/terraworkbench-logo.png",
        "assets/branding/terraworkbench-icon.png",
        "assets/legacy/icon.svg",
        "docs/handbook/README.md",
        "sample_data/workflows/gravity_layer.json",
        "qgis_plugin/geosoft_bridge.py",
    ):
        assert (module.PLUGIN_ROOT / relative).is_file()
