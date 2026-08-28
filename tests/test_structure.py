"""Small checks that do not require a running QGIS instance."""

from pathlib import Path
import configparser
import re
from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_declares_processing_provider():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "metadata.txt", encoding="utf-8")
    assert parser["general"]["hasprocessingprovider"] == "yes"
    assert re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", parser["general"]["version"]
    )
    assert parser["general"]["plugin_dependencies"] == "qpip"
    assert "requirements.txt" in parser["general"]["about"]


def test_required_plugin_files_exist():
    for name in (
        "__init__.py",
        "metadata.txt",
        "metadata_utils.py",
        "qgis_compat.py",
        "workflow_dock.py",
        "plugin.py",
        "provider.py",
        "spectral.py",
        "line_processing.py",
        "microlevel.py",
        "inversion_core.py",
        "LICENSE",
    ):
        assert (ROOT / name).is_file()


def test_runtime_versions_are_derived_from_metadata():
    provider = (ROOT / "provider.py").read_text(encoding="utf-8")
    dialog = (ROOT / "dependency_dialog.py").read_text(encoding="utf-8")
    assert "return plugin_version()" in provider
    assert "PLUGIN_VERSION = plugin_version()" in dialog


def test_filter_stack_is_registered_and_packaged():
    plugin = (ROOT / "plugin.py").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    assert "FilterStackDock" in plugin
    assert "RightDockWidgetArea" in plugin
    assert '"workflow_dock.py"' in packager


def test_inversion_dependencies_are_declared_for_qpip_and_packaged():
    base = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    optional = (ROOT / "requirements-inversion.txt").read_text(encoding="utf-8")
    packager = (ROOT / "scripts" / "package_plugin.py").read_text(encoding="utf-8")
    assert "simpeg" in base.casefold()
    assert "discretize" in base.casefold()
    assert "choclo" in base.casefold()
    assert "simpeg" in optional.casefold()
    assert '"requirements-inversion.txt"' in packager


def test_canonical_requirements_are_qpip_parseable_and_complete():
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
        "simpeg",
        "discretize",
        "choclo",
    }
