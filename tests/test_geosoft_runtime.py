from pathlib import Path

from qgis_plugin.geosoft_runtime import validate_geosoft_location


def test_validate_geosoft_desktop_application_folder(tmp_path):
    root = tmp_path / "Geosoft" / "Desktop Applications"
    (root / "bin").mkdir(parents=True)
    (root / "python").mkdir()
    (root / "bin" / "omscore.exe").touch()
    (root / "python" / "python.exe").touch()
    runtime = validate_geosoft_location(root)
    assert runtime is not None
    assert runtime.root == root


def test_validate_geosoft_parent_folder_with_nested_install(tmp_path):
    root = tmp_path / "Geosoft" / "Desktop 2026" / "Desktop Applications"
    (root / "bin").mkdir(parents=True)
    (root / "python").mkdir()
    (root / "bin" / "omscore.exe").touch()
    (root / "python" / "python.exe").touch()
    runtime = validate_geosoft_location(tmp_path / "Geosoft")
    assert runtime is not None
    assert Path(runtime.omscore).name.casefold() == "omscore.exe"


def test_connector_locations_are_detected_without_running_executable(tmp_path, monkeypatch):
    from qgis_plugin.geosoft_runtime import find_seequent_connector, gdb_prerequisite_notice

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for key in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        monkeypatch.setenv(key, str(tmp_path / "programs"))
    assert find_seequent_connector() is None
    for path in ("Geosoft_Inc/Geosoft Connect/GeosoftConnect.exe",
                 "Seequent/Seequent Connector/SeequentConnector.exe"):
        executable = tmp_path / path
        executable.parent.mkdir(parents=True)
        executable.touch()
        assert find_seequent_connector() == executable
        executable.unlink()
    for locale in ("en", "es", "pt"):
        notice = gdb_prerequisite_notice(locale)
        assert "Seequent ID" in notice and "XYZ" in notice and "CSV" in notice
        assert "seequent.com" in notice


def test_bridge_adds_managed_packages_only_for_matching_python(tmp_path, monkeypatch):
    """A desktop GX Python must never import QGIS' compiled wheels."""
    import sys

    from qgis_plugin import geosoft_bridge

    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    matching = tmp_path / "deps" / version
    other = tmp_path / "deps" / "2.7"
    matching.mkdir(parents=True)
    other.mkdir(parents=True)
    added = []
    monkeypatch.setattr(geosoft_bridge.site, "addsitedir", added.append)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("TERRAWORKBENCH_DEPENDENCY_PATH", str(other))
    geosoft_bridge.activate_managed_packages()
    assert added == []
    monkeypatch.setenv("TERRAWORKBENCH_DEPENDENCY_PATH", str(matching))
    geosoft_bridge.activate_managed_packages()
    assert added == [str(matching)] and str(matching) in sys.path
