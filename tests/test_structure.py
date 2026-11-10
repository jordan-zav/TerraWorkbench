"""Small checks that do not require a running QGIS instance."""

from pathlib import Path
import ast
import configparser
import json
import re
from packaging.requirements import Requirement
import pytest

from qgis_plugin.delimited_text import detect_delimited_layout, regular_coordinate_axes


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
    assert parser["general"]["experimental"] == "False"
    assert "requirements/base.txt" in parser["general"]["about"]
    assert parser["general"]["author"] == "Jordan Zavaleta (GisGeo Dev)"
    assert parser["general"]["email"] == "jordanzav@gisgeo.dev"


def test_required_plugin_files_exist():
    for name in (
        "__init__.py",
        "metadata.txt",
        "qgis_plugin/metadata_utils.py",
        "ui/i18n.py",
        "ui/settings_dialog.py",
        "qgis_plugin/qgis_compat.py",
        "ui/workflow_dock.py",
        "qgis_plugin/plugin.py",
        "qgis_plugin/provider.py",
        "compat/spectral.py",
        "compat/line_processing.py",
        "qgis_plugin/microlevel.py",
        "compat/inversion_core.py",
        "compat/gravity_corrections.py",
        "compat/radiometry.py",
        "qgis_plugin/crs_utils.py",
        "compat/survey_corrections.py",
        "compat/preprocessing.py",
        "LICENSE",
    ):
        assert (ROOT / name).is_file()


def test_runtime_versions_are_derived_from_metadata():
    provider = (ROOT / "qgis_plugin/provider.py").read_text(encoding="utf-8")
    dialog = (ROOT / "ui/dependency_dialog.py").read_text(encoding="utf-8")
    assert "return plugin_version()" in provider
    assert "PLUGIN_VERSION = plugin_version()" in dialog


def test_every_static_processing_label_has_a_spanish_translation():
    translation_tree = ast.parse((ROOT / "ui/i18n.py").read_text(encoding="utf-8"))
    translation_dict = next(
        node.value
        for node in translation_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_ES" for target in node.targets)
    )
    translated = {key.value for key in translation_dict.keys}
    # Whole-string additions are also authored catalogue entries. Audit runtime
    # updates instead of assuming every entry lives in the first literal.
    for node in translation_tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "_ES"
                and node.value.func.attr == "update"
                and node.value.args and isinstance(node.value.args[0], ast.Dict)):
            translated.update(key.value for key in node.value.args[0].keys)
    # The paired new-process catalogue extends both ES and PT at runtime.
    paired = next(node.value for node in translation_tree.body
                  if isinstance(node, ast.Assign) and any(
                      isinstance(target, ast.Name) and target.id == "_BASIC_PROCESSING_TRANSLATIONS"
                      for target in node.targets))
    for key, value in zip(paired.keys, paired.values):
        assert len(value.elts) == 2 and all(isinstance(item, ast.Constant) and item.value for item in value.elts)
        translated.add(key.value)
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

    portuguese_exact.update({key.value: ast.literal_eval(value)[1]
                             for key, value in zip(paired.keys, paired.values)})
    for node in translation_tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "_PT_EXACT"
                and node.value.func.attr == "update"
                and node.value.args and isinstance(node.value.args[0], ast.Dict)):
            portuguese_exact.update(ast.literal_eval(node.value.args[0]))

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
    plugin = (ROOT / "qgis_plugin/plugin.py").read_text(encoding="utf-8")
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
    plugin = (ROOT / "qgis_plugin/plugin.py").read_text(encoding="utf-8")
    dock = (ROOT / "ui/workflow_dock.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    assert "FilterStackDock" in plugin
    assert "RightDockWidgetArea" in plugin
    assert '"DragDropMode", "InternalMove"' in dock
    assert "self.settings_button, 0, 2" in dock
    assert "self.up_button" not in dock
    assert "self.down_button" not in dock
    assert '"ui/workflow_dock.py"' in packager


def test_user_knowledge_base_is_clickable_and_packaged():
    dock = (ROOT / "ui/workflow_dock.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    knowledge_root = ROOT / "docs" / "handbook"
    sources = json.loads((knowledge_root / "sources.json").read_text(encoding="utf-8"))
    assert "KnowledgeBaseDialog" in dock
    assert "setOpenExternalLinks(True)" in dock
    assert "FilterInfoDialog" in dock
    assert 'info_button.setText("i")' in dock
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
        assert f'"docs/handbook/{name}"' in packager


def test_redistributable_sample_data_is_packaged_separately():
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    sample_root = ROOT / "sample_data" / "synthetic"
    manifest = json.loads((sample_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "CC0-1.0"
    for name in (
        "synthetic_magnetic_anomaly.tif",
        "synthetic_gravity_anomaly.tif",
        "synthetic_dem.tif",
        "synthetic_potassium.tif",
        "synthetic_equivalent_uranium.tif",
        "synthetic_equivalent_thorium.tif",
        "synthetic_survey_points.csv",
    ):
        assert (sample_root / name).is_file()
        assert f'"sample_data/synthetic/{name}"' in packager
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    installer = (ROOT / "scripts/install_update_open_qgis.bat").read_text(encoding="utf-8")
    assert "sample_data/local_private/" in gitignore
    assert "local_private" in installer
    from scripts.package_plugin import package_files
    assert not any("nrcan" in path.relative_to(ROOT).parts for path in package_files())
    assert "refresh_bundled_reference_actions" in (ROOT / "ui/workflow_dock.py").read_text(encoding="utf-8")


def test_standalone_geosoft_reader_is_declared_before_installed_fallback():
    requirements = (ROOT / "requirements/base.txt").read_text(encoding="utf-8")
    bridge = (ROOT / "qgis_plugin/geosoft_bridge.py").read_text(encoding="utf-8")
    dock = (ROOT / "ui/workflow_dock.py").read_text(encoding="utf-8")
    licenses = (ROOT / "docs/legal/THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    assert 'geosoft>=2024.2,<2025; platform_system == "Windows"' in requirements
    assert "TERRAWORKBENCH_GEOSOFT_SITE" in bridge
    assert dock.index('find_spec("geosoft")') < dock.index("find_geosoft_runtime(")
    assert "BSD-2-Clause" in licenses


def test_local_reference_data_is_configurable_and_not_hardcoded():
    dock = (ROOT / "ui/workflow_dock.py").read_text(encoding="utf-8")
    settings = (ROOT / "ui/settings_dialog.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(
        encoding="utf-8"
    )
    assert "KEY_LOCAL_DATA" in dock
    assert "refresh_local_data_menu" in dock
    assert "localTestDataDirectory" in settings
    assert "sample_data/local_private" not in packager
    combined = (dock + settings + packager).casefold()
    assert ("n" + ":\\0. projects") not in combined
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
    plugin = (ROOT / "qgis_plugin/plugin.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'return "mag_upward_continuation"' in magnetic
    assert 'return "grav_upward_continuation"' in gravity
    assert 'return "mag_directional_horizontal_gradient"' in magnetic
    combined = "\n".join((magnetic, gravity, plugin, readme)).casefold()
    assert "uc" + "500" not in combined
    assert "45" + "hg" not in combined
    assert "addalgorithmalias" not in plugin.casefold()


def test_inversion_dependencies_are_declared_for_embedded_manager_and_packaged():
    base = (ROOT / "requirements/base.txt").read_text(encoding="utf-8")
    optional = (ROOT / "requirements/inversion.txt").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    assert "simpeg" not in base.casefold()
    assert "discretize" not in base.casefold()
    assert "choclo" not in base.casefold()
    assert "simpeg" in optional.casefold()
    assert "discretize" in optional.casefold()
    assert "choclo" in optional.casefold()
    assert '"requirements/inversion.txt"' in packager


def test_canonical_requirements_are_parseable_and_complete():
    requirements = []
    for raw_line in (
        (ROOT / "requirements/base.txt").read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if line and not line.startswith(("#", "-")):
            requirements.append(Requirement(line))
    names = {requirement.name.casefold() for requirement in requirements}
    assert names == {
        "numba",
        "harmonica",
        "ppigrf",
        "defusedxml",
        "geosoft",
        "scipy",
        "pyarrow",
        "scikit-image",
        "pywavelets",
        "pyproj",
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
