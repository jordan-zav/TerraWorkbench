"""Small checks that do not require a running QGIS instance."""

from pathlib import Path
import ast
import configparser
import hashlib
import json
import re
from packaging.requirements import Requirement
import pytest

from delimited_text import detect_delimited_layout, regular_coordinate_axes


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_declares_processing_provider():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "metadata.txt", encoding="utf-8")
    assert parser["general"]["hasprocessingprovider"] == "yes"
    assert re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", parser["general"]["version"]
    )
    assert not parser["general"].get("plugin_dependencies", "").strip()
    assert parser["general"]["qgismaximumversion"] == "3.99"
    assert parser["general"]["experimental"] == "True"
    assert "requirements.txt" in parser["general"]["about"]
    assert parser["general"]["author"] == "Jordan Zavaleta (GisGeo Dev)"
    assert parser["general"]["email"] == "jordanzav@gisgeo.dev"


def test_required_plugin_files_exist():
    for name in (
        "__init__.py",
        "metadata.txt",
        "metadata_utils.py",
        "i18n.py",
        "settings_dialog.py",
        "qgis_compat.py",
        "workflow_dock.py",
        "plugin.py",
        "provider.py",
        "spectral.py",
        "line_processing.py",
        "microlevel.py",
        "inversion_core.py",
        "gravity_corrections.py",
        "LICENSE",
    ):
        assert (ROOT / name).is_file()


def test_runtime_versions_are_derived_from_metadata():
    provider = (ROOT / "provider.py").read_text(encoding="utf-8")
    dialog = (ROOT / "dependency_dialog.py").read_text(encoding="utf-8")
    assert "return plugin_version()" in provider
    assert "PLUGIN_VERSION = plugin_version()" in dialog


def test_every_static_processing_label_has_a_spanish_translation():
    translation_tree = ast.parse((ROOT / "i18n.py").read_text(encoding="utf-8"))
    translation_dict = next(
        node.value
        for node in translation_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_ES" for target in node.targets)
    )
    translated = {key.value for key in translation_dict.keys}
    processing_strings = set()
    for path in (ROOT / "algorithms").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                processing_strings.add(node.args[0].value)
    assert processing_strings <= translated

    portuguese_exact = next(
        ast.literal_eval(node.value)
        for node in translation_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_PT_EXACT"
            for target in node.targets
        )
    )
    portuguese_replacements = next(
        ast.literal_eval(node.value)
        for node in translation_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_PT_REPLACEMENTS"
            for target in node.targets
        )
    )

    def portuguese(source):
        if source in portuguese_exact:
            return portuguese_exact[source]
        result = source
        for english, translated_text in portuguese_replacements:
            result = result.replace(english, translated_text)
        return result

    assert all(portuguese(source) != source for source in processing_strings)


def test_embedded_dependency_manager_replaces_external_qpip_dependency():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "metadata.txt", encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    manager = (ROOT / "embedded_qpip" / "manager.py").read_text(encoding="utf-8")
    assert not parser["general"].get("plugin_dependencies", "").strip()
    assert "--progress-bar" in manager
    assert '"raw"' in manager
    assert "active QGIS user profile" in manager
    plugin = (ROOT / "plugin.py").read_text(encoding="utf-8")
    assert plugin.index(
        "show_dependency_dialog(self.iface.mainWindow())"
    ) < plugin.index("        self.initProcessing()")
    for name in (
        "__init__.py",
        "manager.py",
        "install_progress.py",
        "pip_progress.py",
        "NOTICE.md",
        "LICENSE.qpip",
    ):
        assert (ROOT / "embedded_qpip" / name).is_file()
        assert f'"embedded_qpip/{name}"' in packager


def test_filter_stack_is_registered_and_packaged():
    plugin = (ROOT / "plugin.py").read_text(encoding="utf-8")
    dock = (ROOT / "workflow_dock.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    assert "FilterStackDock" in plugin
    assert "RightDockWidgetArea" in plugin
    assert '"DragDropMode", "InternalMove"' in dock
    assert "self.settings_button, 0, 2" in dock
    assert "self.up_button" not in dock
    assert "self.down_button" not in dock
    assert '"workflow_dock.py"' in packager


def test_user_knowledge_base_is_clickable_and_packaged():
    dock = (ROOT / "workflow_dock.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    knowledge_root = ROOT / "docs" / "knowledge_base"
    sources = json.loads((knowledge_root / "sources.json").read_text(encoding="utf-8"))
    assert "KnowledgeBaseDialog" in dock
    assert "setOpenExternalLinks(True)" in dock
    assert "FilterInfoDialog" in dock
    assert 'info_button.setText("ⓘ")' in dock
    assert "setItemWidget(item, row)" in dock
    assert len(sources["sources"]) >= 20
    assert all(source["url"].startswith("https://") for source in sources["sources"])
    for name in (
        "README.md",
        "geofisica_potencial_referencia.md",
        "potential_fields_reference_en.md",
        "potential_fields_reference_pt.md",
        "repositorios_referencia.md",
        "roadmap_cobertura.md",
        "sources.json",
    ):
        assert (knowledge_root / name).is_file()
        assert f'"docs/knowledge_base/{name}"' in packager


def test_redistributable_sample_data_is_packaged_separately():
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    sample_root = ROOT / "sample_data" / "synthetic"
    manifest = json.loads((sample_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "CC0-1.0"
    for name in (
        "synthetic_magnetic_anomaly.tif",
        "synthetic_gravity_anomaly.tif",
        "synthetic_dem.tif",
        "synthetic_survey_points.csv",
    ):
        assert (sample_root / name).is_file()
        assert f'"sample_data/synthetic/{name}"' in packager
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    installer = (ROOT / "install_update_open_qgis.bat").read_text(encoding="utf-8")
    assert "sample_data/local_private/" in gitignore
    assert "local_private" in installer
    notice = ROOT / "sample_data" / "nrcan" / "NOTICE.md"
    assert notice.is_file()
    notice_text = notice.read_text(encoding="utf-8")
    assert "https://geophysical-data.canada.ca/portal" in notice_text
    assert "Open Government Licence - Canada" in notice_text
    assert "infogdc-infocdg@nrcan-rncan.gc.ca" in notice_text
    nrcan_manifest = json.loads(
        (ROOT / "sample_data" / "nrcan" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert nrcan_manifest["license"] == "Open Government Licence - Canada"
    assert len(nrcan_manifest["files"]) == 4
    for entry in nrcan_manifest["files"]:
        path = ROOT / "sample_data" / "nrcan" / entry["path"]
        assert path.is_file()
        assert path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert f'"sample_data/nrcan/{entry["path"]}"' in packager


def test_standalone_geosoft_reader_is_declared_before_oasis_fallback():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    bridge = (ROOT / "geosoft_bridge.py").read_text(encoding="utf-8")
    dock = (ROOT / "workflow_dock.py").read_text(encoding="utf-8")
    licenses = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    assert 'geosoft>=2024.2,<2025; platform_system == "Windows"' in requirements
    assert "TERRAWORKBENCH_GEOSOFT_SITE" in bridge
    assert dock.index('find_spec("geosoft")') < dock.index("find_geosoft_runtime(")
    assert "BSD-2-Clause" in licenses


def test_local_reference_data_is_configurable_and_not_hardcoded():
    dock = (ROOT / "workflow_dock.py").read_text(encoding="utf-8")
    settings = (ROOT / "settings_dialog.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(
        encoding="utf-8"
    )
    assert "KEY_LOCAL_DATA" in dock
    assert "refresh_local_data_menu" in dock
    assert "localTestDataDirectory" in settings
    assert "sample_data/local_private" not in packager
    combined = (dock + settings + packager).casefold()
    assert "n:\\0. projects" not in combined
    assert "i:\\gdrive" not in combined


def test_exploration_upward_continuations_are_configurable():
    magnetic = (ROOT / "algorithms" / "magnetic_filters.py").read_text(
        encoding="utf-8"
    )
    gravity = (ROOT / "algorithms" / "gravity_filters.py").read_text(
        encoding="utf-8"
    )
    for source in (magnetic, gravity):
        assert 'HEIGHT = "HEIGHT"' in source
        assert "height_displacement=height" in source
        assert "Upward continuation (configurable)" in source


def test_configurable_filter_ids_are_neutral():
    magnetic = (ROOT / "algorithms" / "magnetic_filters.py").read_text(
        encoding="utf-8"
    )
    gravity = (ROOT / "algorithms" / "gravity_filters.py").read_text(
        encoding="utf-8"
    )
    plugin = (ROOT / "plugin.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'return "mag_upward_continuation"' in magnetic
    assert 'return "grav_upward_continuation"' in gravity
    assert 'return "mag_directional_horizontal_gradient"' in magnetic
    combined = "\n".join((magnetic, gravity, plugin, readme)).casefold()
    assert "uc" + "500" not in combined
    assert "45" + "hg" not in combined
    assert "addalgorithmalias" not in plugin.casefold()


def test_inversion_dependencies_are_declared_for_embedded_manager_and_packaged():
    base = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    optional = (ROOT / "requirements-inversion.txt").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    assert "simpeg" not in base.casefold()
    assert "discretize" not in base.casefold()
    assert "choclo" not in base.casefold()
    assert "simpeg" in optional.casefold()
    assert "discretize" in optional.casefold()
    assert "choclo" in optional.casefold()
    assert '"requirements-inversion.txt"' in packager


def test_canonical_requirements_are_parseable_and_complete():
    requirements = []
    for raw_line in (
        (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if line and not line.startswith(("#", "-")):
            requirements.append(Requirement(line))
    names = {requirement.name.casefold() for requirement in requirements}
    assert names == {
        "harmonica",
        "ppigrf",
        "defusedxml",
        "geosoft",
    }


def test_delimited_layout_accepts_scientific_notation_and_common_delimiters():
    assert detect_delimited_layout("500000 6200000 1.23e-4\n") == (None, False)
    assert detect_delimited_layout("500000;6200000;NaN\n") == (";", False)
    assert detect_delimited_layout("easting,northing,tmi\n") == (",", True)


def test_regular_grid_rejects_duplicate_or_missing_coordinate_pairs():
    east, north, _dx, _dy = regular_coordinate_axes(
        [0, 1, 0, 1], [0, 0, 1, 1]
    )
    assert east.tolist() == [0, 1]
    assert north.tolist() == [0, 1]

    with pytest.raises(ValueError, match="duplicate"):
        regular_coordinate_axes([0, 0, 0, 1], [0, 0, 1, 0])
