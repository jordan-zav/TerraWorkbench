from pathlib import Path

from geosoft_runtime import validate_geosoft_location


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
    root = tmp_path / "Seequent" / "Oasis 2026" / "Desktop Applications"
    (root / "bin").mkdir(parents=True)
    (root / "python").mkdir()
    (root / "bin" / "omscore.exe").touch()
    (root / "python" / "python.exe").touch()
    runtime = validate_geosoft_location(tmp_path / "Seequent")
    assert runtime is not None
    assert Path(runtime.omscore).name.casefold() == "omscore.exe"
