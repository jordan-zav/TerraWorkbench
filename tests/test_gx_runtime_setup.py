"""Managed GX configuration and upgrades, without executing vendor code."""

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from qgis_plugin import gx_runtime_setup as setup
from qgis_plugin import gx_runtime_check as check


def fake_vendor(tmp_path, monkeypatch):
    archive = tmp_path / "vendor.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("GeosoftRedist/bin/geodist.dll", b"never executed")
    monkeypatch.setattr(setup.sys, "platform", "win32")
    monkeypatch.setattr(setup, "GX_REDIST_BYTES", archive.stat().st_size)
    monkeypatch.setattr(setup, "GX_REDIST_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    import requests

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield archive.read_bytes() if self.archive else b"vendor terms"

    def get(url, **kwargs):
        result = Response()
        result.archive = url == setup.GX_REDIST_URL
        return result

    monkeypatch.setattr(requests, "get", get)
    return archive


def test_full_release_pin():
    assert setup.GX_REDIST_URL.endswith("RELEASE_2024.2.0_26_20241130_redist_full.zip")
    assert setup.GX_REDIST_BYTES == 362081059
    resource = Path(setup.__file__).resolve().parents[1] / "assets/runtime/SHA256SUMS"
    assert resource.read_text().split()[0] == setup.GX_REDIST_SHA256


def test_configuration_has_absolute_writable_paths_spaces_and_crlf(tmp_path):
    target = tmp_path / "profile with spaces" / "_gx_runtime"
    root = target / "install-test/files/GeosoftRedist"
    root.mkdir(parents=True)
    result = setup.ensure_runtime_configuration(root)
    expected = f"{target / 'user'}\r\n{target / 'temp'}\r\n".encode("utf-8")
    assert (root / "geosoft.redist").read_bytes() == expected
    assert not expected.startswith(b"\xef\xbb\xbf")
    assert setup.validate_runtime_configuration(root) == result
    assert all(Path(p).is_absolute() and Path(p).is_dir() for p in result.values())


def test_existing_runtime_repairs_configuration_without_reinstall(tmp_path, monkeypatch):
    archive = fake_vendor(tmp_path, monkeypatch)
    target = tmp_path / "deps with spaces/_gx_runtime"
    root = setup.prepare_runtime(target, archive=archive)
    marker = (target / "installed.json").read_bytes()
    (root / "geosoft.redist").unlink()
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: pytest.fail("must not extract again"))
    assert setup.prepare_runtime(target) == root
    assert (target / "installed.json").read_bytes() == marker
    assert setup.validate_runtime_configuration(root)["user_dir"] == str(target / "user")


def test_upgrade_preserves_old_runtime_until_explicit_confirmation(tmp_path, monkeypatch):
    archive = fake_vendor(tmp_path, monkeypatch)
    target = tmp_path / "_gx_runtime"
    old = target / "install-old/files/GeosoftRedist"
    (old / "bin").mkdir(parents=True)
    (old / "bin/geodist.dll").write_bytes(b"previous version")
    (target / "installed.json").write_text(json.dumps({"root": old.relative_to(target).as_posix(),
                                                     "archive_sha256": "old checksum"}))
    root = setup.prepare_runtime(target, archive=archive)
    assert root != old and (old / "bin/geodist.dll").read_bytes() == b"previous version"
    assert setup.validate_runtime_configuration(root)
    assert archive.exists(), "caller-owned ZIP must be preserved"
    assert setup.previous_runtime_folders(target) == [target / "install-old"]
    with pytest.raises(PermissionError):
        setup.remove_previous_runtime(target, target / "install-old")
    assert old.exists()
    with pytest.raises(ValueError):
        setup.remove_previous_runtime(target, root, confirmed=True)
    setup.remove_previous_runtime(target, target / "install-old", confirmed=True)
    assert not old.exists() and root.exists()
    assert setup.previous_runtime_folders(target) == []


def test_owned_download_removed_after_verified_extraction(tmp_path, monkeypatch):
    fake_vendor(tmp_path, monkeypatch)
    root = setup.prepare_runtime(tmp_path / "_gx_runtime")
    assert not list((tmp_path / "_gx_runtime").rglob("download.zip"))
    assert (root / "bin/geodist.dll").is_file()


@pytest.mark.parametrize("data", [b"one\ntwo\n", b"\xef\xbb\xbfone\r\ntwo\r\n", b"missing\r\nmissing\r\n"])
def test_bad_configuration_fails_before_native_loader(tmp_path, data, monkeypatch):
    (tmp_path / "geosoft.redist").write_bytes(data)
    monkeypatch.setattr(check.ctypes, "WinDLL", lambda *a, **k: pytest.fail("native loader must not run"), raising=False)
    report = check.check_runtime(tmp_path)
    assert not report["ok"] and report["error_code"] == "invalid_redist_configuration"


def test_unwritable_configuration_fails_before_context(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    (root / "bin").mkdir(parents=True)
    (root / "bin/geodist.dll").write_bytes(b"mock")
    monkeypatch.setenv("TERRAWORKBENCH_GX_REDIST", str(root))

    def denied(*args, **kwargs):
        raise PermissionError("simulated denied write")

    monkeypatch.setattr(setup.tempfile, "TemporaryFile", denied)
    from qgis_plugin.gdb_archive_gx import GXAccessRequired, gx_context_options
    with pytest.raises(GXAccessRequired, match="GX_REDIST_CONFIG: simulated denied write"):
        gx_context_options()


def test_missing_net6_blocks_context_but_not_configuration_repair(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    (root / "bin").mkdir(parents=True)
    (root / "bin/geodist.dll").write_bytes(b"mock")
    monkeypatch.setenv("TERRAWORKBENCH_GX_REDIST", str(root))
    monkeypatch.setattr(check, "missing_frameworks", lambda p: [{"name": "Microsoft.NETCore.App", "major": "6"}])
    from qgis_plugin.gdb_archive_gx import GXAccessRequired, gx_context_options
    with pytest.raises(GXAccessRequired, match="GX_DOTNET6"):
        gx_context_options()
    assert setup.validate_runtime_configuration(root)


def test_sanitized_environment_excludes_desktop_discovery(tmp_path):
    env = check.clean_environment(tmp_path, {"PATH": "C:/Program Files/Geosoft/Desktop Applications/bin",
                                           "GEOSOFT_PATH": "desktop", "GX_USER": "desktop",
                                           "SystemRoot": "C:/Windows"})
    assert "GEOSOFT_PATH" not in env and "GX_USER" not in env
    assert "Desktop Applications" not in env["PATH"]
    assert env["TERRAWORKBENCH_GX_REDIST"] == str(tmp_path.resolve())


def test_explicit_desktop_bridge_retains_installed_gx_discovery(monkeypatch):
    from qgis_plugin.gdb_archive_gx import gx_context_options

    monkeypatch.setenv("TERRAWORKBENCH_GX_DESKTOP", "1")
    assert gx_context_options() == {}


def test_read_only_access_is_not_inferred_from_checkout_flag(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import sys
    from qgis_plugin import gdb_archive_gx as adapter, geosoft_bridge as bridge

    original = tmp_path / "original.gdb"
    original.write_bytes(b"synthetic read-only database")
    events = []

    @contextmanager
    def context(**options):
        events.append("context")
        yield

    def open_read_only(path, user, password):
        assert Path(path) != original and Path(path).read_bytes() == original.read_bytes()
        events.append("read_only")
        return "native database"

    @contextmanager
    def database(*, db):
        assert db == "native database"
        yield "database wrapper"

    monkeypatch.setattr(adapter, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(adapter, "gx_context_options", lambda: events.append("configuration") or {})
    monkeypatch.setattr(adapter, "gx_working_directory", lambda options: context_directory())

    @contextmanager
    def context_directory():
        events.append("working_directory")
        yield
    monkeypatch.setattr(bridge, "import_gxpy", lambda: (
        SimpleNamespace(Geosoft_gdb=database), SimpleNamespace(GXpy=context)))
    api = SimpleNamespace(GXDB=SimpleNamespace(open_read_only=open_read_only),
                          GXSYS=SimpleNamespace(is_signed_in=lambda: False))
    monkeypatch.setitem(sys.modules, "geosoft", SimpleNamespace(gxapi=api))
    monkeypatch.setitem(sys.modules, "geosoft.gxpy", SimpleNamespace(utility=object()))
    with adapter.gx_archive_reader(original) as reader:
        assert reader.database == "database wrapper"
    assert events == ["configuration", "working_directory", "context", "read_only"]
    assert original.read_bytes() == b"synthetic read-only database"


def test_conversion_process_aligns_cwd_temp_and_tmp_before_gxpy(tmp_path):
    import os
    from qgis_plugin.gdb_archive_gx import gx_working_directory

    folder = tmp_path / "GX temporary with spaces"
    folder.mkdir()
    previous, temp, tmp = Path.cwd(), os.environ.get("TEMP"), os.environ.get("TMP")
    with pytest.raises(RuntimeError, match="native mock"):
        with gx_working_directory({"temp_dir": str(folder)}):
            assert Path.cwd() == folder
            assert os.environ["TEMP"] == os.environ["TMP"] == str(folder)
            raise RuntimeError("native mock")
    assert Path.cwd() == previous
    assert os.environ.get("TEMP") == temp and os.environ.get("TMP") == tmp

def test_portable_dotnet_download_and_reuse(tmp_path, monkeypatch):
    import hashlib
    import io
    import zipfile
    from unittest.mock import Mock
    import requests
    from qgis_plugin import gx_runtime_setup as setup

    for key in ("DOTNET_ROOT", "DOTNET_ROOT_X64"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "programs"))
    target = tmp_path / "_gx_runtime"
    assets = {}
    for framework, (_, name, _) in zip(setup.DOTNET_FRAMEWORKS, setup.DOTNET_ASSETS):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr(f"shared/{framework}/6.0.36/framework.dll", b"fixture")
            bundle.writestr("dotnet.exe", b"fixture")
            bundle.writestr("LICENSE.txt", b"MIT")
        assets[name] = stream.getvalue()
    checksums = {name: hashlib.sha512(data).hexdigest() for name, data in assets.items()}
    monkeypatch.setattr(setup, "dotnet_checksums", lambda: checksums)
    monkeypatch.setattr(setup, "DOTNET_ASSETS", tuple((family, name, len(assets[name]))
                                                    for family, name, _ in setup.DOTNET_ASSETS))

    def response(url, **kwargs):
        result = requests.Response()
        result.status_code = 200
        result.raw = io.BytesIO(assets[url.rsplit("/", 1)[-1]])
        return result

    download = Mock(side_effect=response)
    monkeypatch.setattr(requests, "get", download)
    system = tmp_path / "programs/dotnet"
    for framework in setup.DOTNET_FRAMEWORKS:
        (system / "shared" / framework / "6.0.36").mkdir(parents=True)
    assert setup.prepare_dotnet(target) == system
    assert not download.called
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "empty"))
    first = next(iter(checksums))
    correct = checksums[first]
    checksums[first] = "0" * 128
    import pytest
    with pytest.raises(ValueError, match="SHA-512"):
        setup.prepare_dotnet(target)
    assert not (target / "dotnet6.json").exists()
    checksums[first] = correct
    root = setup.prepare_dotnet(target)
    assert root.parent == target and download.call_count == 3
    assert setup.prepare_dotnet(target) == root and download.call_count == 3
    assert setup.dotnet_environment(target) == {
        "DOTNET_ROOT": str(root), "DOTNET_ROOT_X64": str(root),
        "DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_DISABLE_GUI_ERRORS": "1",
    }


def test_runtime_extraction_rejects_traversal(tmp_path):
    import zipfile
    import pytest
    from qgis_plugin.gx_runtime_setup import extract_runtime_zip

    archive = tmp_path / "test.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.dll", b"fixture")
    with pytest.raises(ValueError, match="Unsafe"):
        extract_runtime_zip(archive, tmp_path / "output")
    assert not (tmp_path / "escape.dll").exists()
