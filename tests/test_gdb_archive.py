"""Exact native round trips, independent reads and explicit failure reports."""

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from qgis_plugin.gdb_archive_gx import GXArchiveReader
from terraworkbench_core.gdb_archive import (
    attach_archive,
    convert_database,
    open_archive,
)
from terraworkbench_core.survey_store import SurveyStore


class FakeVector:
    def __init__(self, raw, fid):
        self.raw, self.fid, self.dtype, self.length = (
            raw.copy(),
            fid,
            raw.dtype,
            len(raw),
        )
        self.gxva = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get_data(self, *, float_dummies_to_nan):
        assert float_dummies_to_nan is False
        return self.raw.copy(), self.fid

    def get_array_np(self, start, column, count, width, dtype):
        assert dtype == self.dtype
        return self.raw[start : start + count, column : column + width].copy()


class FakeGDB:
    coordinate_system = SimpleNamespace(
        name="UTM 10N", esri_wkt="EPSG:32610", json='{"original":true}'
    )
    xyz_channels = ("X", "Y", None)
    metadata = {
        "LINE_DIRECTION": 90.0,
        "LINE_SPACING": 100.0,
        "custom": {"date": "2026-11-12", "extra": [1, "ñ"]},
    }
    custom_property = property(lambda self: {"unknown_property": "preserved"})

    def __init__(self):
        self.values = {
            f"i{bits}": np.array([1, 2, np.iinfo(f"int{bits}").min], dtype=f"int{bits}")
            for bits in (8, 16, 32, 64)
        }
        self.values["i64"][0] = 2**60 + 3
        self.values.update(
            {
                "X": np.array([500000.0, 500010.0, 500020.0]),
                "Y": np.array([6000000.0, 6000010.0, 6000020.0]),
                "f32": np.array(
                    [0x80000000, 0x7FC01234, 0x7FC05678], dtype="uint32"
                ).view("float32"),
                "f64": np.array([-0.0, 1.23456789012345, -1e32], dtype="float64"),
                "text": np.array(["á\x00B", "", " 001 "], dtype="U10"),
                "spectrum": np.arange(3 * 256, dtype="float32").reshape(3, 256),
            }
        )
        self.values["spectrum"][1, 4] = np.float32(-1e32)
        self.values["spectrum"][2, 10] = np.array([0x7FC01234], dtype="uint32").view(
            "float32"
        )[0]
        self.values["short"] = np.array([10, -32768], dtype="int16")
        self.values["LINE"] = np.array([9, 8, 7], dtype="int8")
        self.calls = {}
        self.corrupt = False
        self.corrupt_float = False
        self.unreadable = False

    def list_channels(self):
        return dict.fromkeys(self.values)

    def channel_dtype(self, name):
        return self.values[name].dtype

    def channel_width(self, name):
        return 256 if name == "spectrum" else 1

    def channel_details(self, name):
        return {
            "name": name,
            "label": "alias " + name,
            "unit": "nT",
            "description": "original description",
            "decimal": 3,
            "format": 1,
            "protect": True,
            "class": name if name in ("X", "Y") else "DATA",
            "array": self.channel_width(name),
            "unknown_attribute": {"preserve": "everything"},
        }

    def list_lines(self, select=True):
        return {"L100": 1, "T200": 2}

    def line_details(self, name):
        return {
            "name": name,
            "type": 2 if name == "T200" else 1,
            "number": 200 if name == "T200" else 100,
            "flight": 3,
            "date": 20261112,
            "version": 2,
            "extra_line_attribute": "original",
        }

    def get_gx_metadata(self):
        return SimpleNamespace(meta_dict=lambda: {"internal": {"all": "metadata"}})

    def _vector(self, line, name):
        key = (line, name)
        self.calls[key] = self.calls.get(key, 0) + 1
        if self.unreadable and name == "spectrum":
            raise ValueError("Simulated inaccessible channel")
        raw = self.values[name].copy()
        if self.corrupt and self.calls[key] > 1 and name == "i64":
            raw[0] += 1
        if self.corrupt_float and self.calls[key] > 1 and name == "f32":
            raw.view("uint32")[0] ^= np.uint32(0x80000000)
        fid = (100.125, 0.25) if name in ("short", "spectrum") else (1000.0, 1.0)
        return FakeVector(raw, fid)

    read_channel_vv = _vector
    read_channel_va = _vector


def reader(db):
    def dummy(dtype):
        dtype = np.dtype(dtype)
        return (
            ""
            if dtype.kind == "U"
            else -1e32
            if dtype.kind == "f"
            else np.iinfo(dtype).min
        )

    return GXArchiveReader(
        db,
        SimpleNamespace(
            LINE_TYPE_NORMAL=1,
            LINE_TYPE_TIE=2,
            Line=lambda db, name: SimpleNamespace(selected=name != "T200"),
        ),
        SimpleNamespace(gx_dummy=dummy),
    )


def archive(tmp_path, **flags):
    db = FakeGDB()
    for key, value in flags.items():
        setattr(db, key, value)
    root = tmp_path / "source.twarchive"
    result = convert_database(
        reader(db), root, {"source_path": "synthetic.gdb", "source_sha256": "simulated"}
    )
    return root, db, result


def test_native_round_trip_and_metadata(tmp_path):
    root, db, report = archive(tmp_path)
    assert report["verified"], report
    assert report["differences"] == report["unreadable"] == []
    assert report["lines"] == 2 and report["array_channels"] == 1
    assert report["samples"] == 6
    assert set(db.calls.values()) == {2}
    store, database_id, meta = open_archive(root)
    assert meta["database_metadata"] == db.metadata
    assert meta["extras"]["custom_property"]["unknown_property"] == "preserved"
    assert meta["lines"][1]["kind"] == "tie" and meta["lines"][1]["selected"] is False
    assert meta["channels"][0]["extras"]["unknown_attribute"] == {
        "preserve": "everything"
    }
    assert meta["alignment"][-2]["length"] == 2
    assert "spectrum" not in meta["map_columns"] and "short" not in meta["map_columns"]
    assert {row["channel"] for row in meta["map_omissions"]} == {"spectrum", "short"}
    with store._connection() as connection:
        assert (
            connection.execute("SELECT count(*) FROM gdb_channel_lines").fetchone()[0]
            == len(db.values) * 2
        )
        pair = connection.execute(
            "SELECT fid_start, fid_increment, sample_count FROM gdb_channel_lines WHERE channel='short' LIMIT 1"
        ).fetchone()
        assert tuple(pair) == (100.125, 0.25, 2)
    batch = next(
        store.batches(database_id, ["i64", "f32", "text", "spectrum", "CHANNEL_LINE"])
    )
    assert batch["i64"].type.bit_width == 64
    assert batch["i64"].to_pylist()[0] == 2**60 + 3
    assert batch["i64"].to_pylist()[2] is None
    assert batch["text"].to_pylist()[:3] == ["á\x00B", None, " 001 "]
    assert batch["spectrum"].type.list_size == 256
    assert batch["spectrum"].to_pylist()[1][4] is None
    np.testing.assert_array_equal(
        batch["f32"].to_numpy().view("uint32")[:3], db.values["f32"].view("uint32")
    )
    assert open_archive(root / "databases/samples.parquet")[1] == database_id
    assert open_archive(root / "catalog.sqlite")[1] == database_id
    destination = SurveyStore(tmp_path / "other", create=True)
    attached = attach_archive(destination, root)
    assert (
        next(destination.batches(attached, ["spectrum"]))["spectrum"].type.list_size
        == 256
    )


@pytest.mark.parametrize(
    "flag,key",
    [
        ("corrupt", "differences"),
        ("corrupt_float", "differences"),
        ("unreadable", "unreadable"),
    ],
)
def test_independent_verification_refuses_data_loss(tmp_path, flag, key):
    root, _, report = archive(tmp_path, **{flag: True})
    assert not report["verified"] and report[key]
    with pytest.raises(ValueError, match="not verified"):
        open_archive(root)


def test_geosoft_blocked_and_artifact_integrity(tmp_path):
    root, _, result = archive(tmp_path)
    assert result["verified"]
    code = """
import sys
try:
    import winreg
    original_open = winreg.OpenKey
    def deny_geosoft_registry(root, path, *args, **kwargs):
        if 'geosoft' in str(path).casefold():
            raise AssertionError('Forbidden Geosoft registry access')
        return original_open(root, path, *args, **kwargs)
    winreg.OpenKey = deny_geosoft_registry
except ImportError:
    pass
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'geosoft', 'qgis', 'PyQt5', 'PyQt6'}:
            raise AssertionError('Forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from terraworkbench_core.gdb_archive import open_archive
store, database, _ = open_archive(sys.argv[1])
assert next(store.batches(database, ['spectrum']))['spectrum'].type.list_size == 256
"""
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith(
            (
                "GEOSOFT",
                "GX_",
                "SEEQUENT",
                "TERRAWORKBENCH_GX",
                "TERRAWORKBENCH_GEOSOFT",
            )
        )
    }
    environment["PATH"] = (
        str(Path(sys.executable).parent)
        + os.pathsep
        + str(Path(os.environ.get("SystemRoot", "/usr")) / "System32")
    )
    subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
    )
    with (root / "databases/samples.parquet").open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        open_archive(root)


def test_unverified_is_never_accepted_as_lossless(tmp_path):
    root = tmp_path / "unverified"
    result = convert_database(
        reader(FakeGDB()), root, {"source_path": "fake.gdb"}, verify=False
    )
    assert result["status"] == "unverified" and not result["verified"]
    with pytest.raises(ValueError, match="not verified"):
        open_archive(root)


def test_batch_continues_after_failure_and_handles_same_stems(tmp_path, monkeypatch):
    from scripts import convert_gdb_archive as cli

    source = tmp_path / "inputs"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir()
    for p in (source / "a/data.gdb", source / "b/data.gdb"):
        p.write_bytes(b"fake")
    calls = []

    def convert(path, destination, **options):
        calls.append(destination)
        if len(calls) == 1:
            raise ValueError("Simulated damaged input")
        return {"verified": True, "status": "verified"}

    monkeypatch.setattr(cli, "convert_file", convert)
    out = tmp_path / "batch"
    assert cli.main(["--input", str(source), "--output", str(out)]) == 1
    results = json.loads((out / "batch-report.json").read_text())
    assert len(results) == 2 and results[1]["verified"]
    assert calls[0] != calls[1]


def test_license_request_stops_batch_without_accepting(tmp_path, monkeypatch):
    from scripts import convert_gdb_archive as cli
    from qgis_plugin.gdb_archive_gx import GXAccessRequired

    for name in ("a.gdb", "b.gdb"):
        (tmp_path / name).write_bytes(b"fake")

    def convert(*args, **kwargs):
        raise GXAccessRequired("Simulated license reservation request")

    monkeypatch.setattr(cli, "convert_file", convert)
    out = tmp_path / "output"
    assert cli.main(["--input", str(tmp_path), "--output", str(out)]) == 1
    results = json.loads((out / "batch-report.json").read_text())
    assert len(results) == 1 and "batch_stopped" in results[0]


def test_connector_notice_is_complete_in_three_languages(tmp_path, monkeypatch):
    from qgis_plugin.geosoft_runtime import (
        conversion_notice,
        find_seequent_connector,
        SEEQUENT_CONNECTOR_URL,
    )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "programs"))
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "programs"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "programs"))
    assert find_seequent_connector() is None
    for locale in ("en", "es", "pt"):
        notice = conversion_notice(locale, connector_missing=True)
        assert SEEQUENT_CONNECTOR_URL in notice
        assert "Seequent ID" in notice and "Oasis montaj" in notice


def test_managed_runtime_setup_pins_download_and_keeps_licenses(tmp_path, monkeypatch):
    import hashlib
    import zipfile
    import requests
    from qgis_plugin import gx_runtime_setup as setup
    from qgis_plugin.geosoft_runtime import managed_gx_runtime

    monkeypatch.setattr(setup.sys, "platform", "win32")

    archive = tmp_path / "vendor.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "GeosoftRedist/bin/geodist.dll", b"simulated binary, never executed"
        )
    monkeypatch.setattr(setup, "GX_REDIST_BYTES", archive.stat().st_size)
    monkeypatch.setattr(
        setup, "GX_REDIST_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest()
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b"Vendor license terms"

    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response())
    parent = tmp_path / "dependencies"
    root = setup.prepare_runtime(parent / "_gx_runtime", archive=archive)
    assert managed_gx_runtime(parent) == root
    assert (parent / "_gx_runtime/LICENSE.txt").read_text() == "Vendor license terms"
    assert setup.prepare_runtime(parent / "_gx_runtime", archive=archive) == root


def test_runtime_setup_rejects_platform_hash_and_traversal(tmp_path, monkeypatch):
    import hashlib
    import zipfile
    from qgis_plugin import gx_runtime_setup as setup

    monkeypatch.setattr(setup.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows"):
        setup.prepare_runtime(tmp_path / "linux")
    assert not (tmp_path / "linux").exists()
    monkeypatch.setattr(setup.sys, "platform", "win32")
    archive = tmp_path / "vendor.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.dll", b"unsafe")
    monkeypatch.setattr(setup, "GX_REDIST_BYTES", archive.stat().st_size)
    with pytest.raises(ValueError, match="SHA-256"):
        setup.prepare_runtime(tmp_path / "bad-hash", archive=archive)
    monkeypatch.setattr(
        setup, "GX_REDIST_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="Unsafe"):
        setup.prepare_runtime(tmp_path / "bad-path", archive=archive)
    assert not (tmp_path / "outside.dll").exists()


def test_runtime_checksum_resource_is_required_and_validated(tmp_path, monkeypatch):
    from qgis_plugin import gx_runtime_setup as setup

    expected = setup.GX_REDIST_SHA256
    assert len(bytes.fromhex(expected)) == 32
    monkeypatch.setattr(setup, "__file__", str(tmp_path / "qgis_plugin/setup.py"))
    with pytest.raises(FileNotFoundError):
        setup._runtime_checksum()
    resource = tmp_path / "assets/runtime/SHA256SUMS"
    resource.parent.mkdir(parents=True)
    filename = setup.GX_REDIST_URL.rsplit("/", 1)[-1]
    resource.write_text(f"{expected}  {filename}\n", encoding="ascii")
    assert setup._runtime_checksum() == expected
    for value in ("0" * 63, "z" * 64):
        resource.write_text(f"{value}  {filename}\n", encoding="ascii")
        with pytest.raises(ValueError, match="checksum"):
            setup._runtime_checksum()
    resource.write_text(f"{expected}  other.zip\n", encoding="ascii")
    with pytest.raises(ValueError, match="checksum"):
        setup._runtime_checksum()


def test_context_configuration_never_discovers_desktop_registry(tmp_path, monkeypatch):
    from qgis_plugin.gdb_archive_gx import gx_context_options

    root = tmp_path / "managed"
    (root / "bin").mkdir(parents=True)
    (root / "bin/geodist.dll").write_bytes(b"simulated")
    monkeypatch.setenv("TERRAWORKBENCH_GX_REDIST", str(root))
    options = gx_context_options()
    assert options["redist_override"] is True
    assert options["redist_dir"] == str(root)
    assert "key" not in options


def test_unknown_metadata_is_explicit_without_blocking_sample_verification(tmp_path):
    db = FakeGDB()
    db.metadata = {"unsupported": object()}
    result = convert_database(
        reader(db), tmp_path / "bad-metadata", {"source_path": "fake.gdb"}
    )
    assert result["verified"] and not result["metadata_complete"]
    assert any(item["type"] == "object" and item["lossy"] for item in result["metadata_conversions"])


def test_channel_metadata_failure_reports_the_original_channel_name(tmp_path):
    db = FakeGDB()
    original = db.channel_details

    def channel_details(name):
        if name == "spectrum":
            raise ValueError("Simulated missing channel metadata")
        return original(name)

    db.channel_details = channel_details
    result = convert_database(
        reader(db), tmp_path / "missing-metadata", {"source_path": "fake.gdb"}
    )
    assert not result["verified"] and result["channels"] == len(db.values)
    assert any(
        row["channel"] == "spectrum" and "metadata" in row["reason"]
        for row in result["unreadable"]
    )


def test_missing_database_metadata_does_not_prevent_exact_sample_verification(tmp_path):
    db = FakeGDB()

    def inaccessible_metadata():
        raise FileNotFoundError("simulated missing GX meta_temporary")

    db.get_gx_metadata = inaccessible_metadata
    result = convert_database(reader(db), tmp_path / "missing-metadata", {"source_path": "fake.gdb"})
    assert result["verified"] and result["data_verified"] and not result["metadata_complete"]
    assert result["channels"] == len(db.values) and not result["differences"]
    assert result["metadata_unavailable"] == [{"field": "gx_metadata", "error": "FileNotFoundError: simulated missing GX meta_temporary"}]
    manifest = json.loads((tmp_path / "missing-metadata/archive.json").read_text())
    assert manifest["gx_metadata"] is None and not manifest["metadata_complete"]
    assert manifest["metadata_unavailable"] == result["metadata_unavailable"]
    open_archive(tmp_path / "missing-metadata")


def test_empty_gx_catalogue_retains_metadata_error_without_claiming_verification(tmp_path):
    db = FakeGDB()
    db.values = {}

    def unavailable():
        raise FileNotFoundError("exact native metadata diagnostic")

    db.get_gx_metadata = unavailable
    result = convert_database(reader(db), tmp_path / "empty", {"source_path": "fake.gdb"})
    assert not result["verified"] and not result["data_verified"]
    assert not result["metadata_complete"]
    assert result["metadata_unavailable"][0]["error"] == "FileNotFoundError: exact native metadata diagnostic"


def test_name_inventory_precedes_metadata_and_survives_metadata_failure():
    db = FakeGDB()
    events = []
    channels, lines, details = db.list_channels, db.list_lines, db.channel_details
    db.list_channels = lambda: events.append("channels") or channels()
    db.list_lines = lambda select: events.append("lines") or lines(select)
    db.channel_details = lambda name: events.append("channel_metadata") or details(name)

    def metadata():
        events.append("gx_metadata")
        raise FileNotFoundError("meta_mock")

    db.get_gx_metadata = metadata
    source = reader(db)
    catalogue = source.catalogue()
    assert events[:2] == ["channels", "lines"]
    assert len(source.inventory_snapshot["channels"]) == len(db.values)
    assert len(source.inventory_snapshot["lines"]) == 2
    assert not catalogue["metadata_complete"]
    assert catalogue["metadata_unavailable"][0]["error"] == "FileNotFoundError: meta_mock"


@pytest.mark.parametrize("failed", ["channels", "lines"])
def test_inventory_attempts_both_lists_when_one_fails(failed):
    db = FakeGDB()

    def error(*args):
        raise RuntimeError("native inventory diagnostic")

    if failed == "channels":
        db.list_channels = error
    else:
        db.list_lines = error
    result = reader(db).inventory()
    assert result[failed] == []
    other = "lines" if failed == "channels" else "channels"
    assert result[other]
    assert result["errors"] == [{"field": failed, "error": "RuntimeError: native inventory diagnostic"}]


def test_geometry_properties_are_serialized_without_exclusion(tmp_path):
    class Point:
        xyz = (1.0, 2.0, 3.0)
        coordinate_system = SimpleNamespace(name="EPSG:32610", esri_wkt="WKT")

    class GeometryDatabase(FakeGDB):
        extent_minimum = property(lambda self: Point())
        extent_maximum = property(lambda self: Point())
        centroid = property(lambda self: Point())

    result = convert_database(reader(GeometryDatabase()), tmp_path / "geometry", {"source_path": "fake.gdb"})
    assert result["verified"] and result["metadata_complete"]
    manifest = json.loads((tmp_path / "geometry/archive.json").read_text())
    for name in ("extent_minimum", "extent_maximum", "centroid"):
        assert manifest["extras"][name]["coordinates"] == [1.0, 2.0, 3.0]
    assert any(item["path"] == "extras.centroid" and item["type"] == "Point" for item in result["metadata_conversions"])


def test_unknown_metadata_retains_inventory_counts(tmp_path):
    db = FakeGDB()
    db.metadata = {"unsupported": object()}
    result = convert_database(reader(db), tmp_path / "unsupported", {"source_path": "fake.gdb"})
    assert result["verified"] and not result["metadata_complete"]
    assert result["channels"] == len(db.values) and result["lines"] == 2
    assert result["samples"] == 6


def test_coordinate_metadata_failure_cannot_block_samples(tmp_path):
    class Database(FakeGDB):
        @property
        def coordinate_system(self):
            raise RuntimeError("coordinate metadata unavailable")

    result = convert_database(reader(Database()), tmp_path / "no-crs", {"source_path": "fake.gdb"})
    assert result["verified"] and not result["metadata_complete"]
    assert result["samples"] == 6
    assert result["metadata_unavailable"] == [{"field": "coordinate_system", "error": "RuntimeError: coordinate metadata unavailable"}]


def test_source_identity_is_retained_and_source_changes_are_rejected(tmp_path):
    from contextlib import contextmanager
    from qgis_plugin.gdb_archive_gx import convert_gdb_archive
    from terraworkbench_core.gdb_archive import file_sha256

    source = tmp_path / "fake.gdb"
    source.write_bytes(b"immutable synthetic source")
    original_hash = file_sha256(source)

    @contextmanager
    def factory(path):
        yield reader(FakeGDB())

    root = tmp_path / "archive"
    result = convert_gdb_archive(
        source, root, reader_factory=factory, engine_version="simulated"
    )
    assert result["verified"], result
    meta = json.loads((root / "archive.json").read_text(encoding="utf-8"))
    assert meta["provenance"]["source_sha256"] == original_hash
    assert meta["provenance"]["gxpy_version"] == "simulated"

    @contextmanager
    def changing_factory(path):
        yield reader(FakeGDB())
        path.write_bytes(b"source changed during conversion")

    result = convert_gdb_archive(
        source,
        tmp_path / "changed",
        reader_factory=changing_factory,
        engine_version="simulated",
    )
    assert not result["verified"] and "Source changed" in result["error"]


def test_access_failure_retains_exact_diagnostic_without_claiming_zero_differences(
    tmp_path,
):
    from contextlib import contextmanager
    from qgis_plugin.gdb_archive_gx import GXAccessRequired, convert_gdb_archive

    source = tmp_path / "fake.gdb"
    source.write_bytes(b"synthetic")

    @contextmanager
    def unavailable(path):
        raise GXAccessRequired("Simulated Seequent checkout canceled")
        yield

    with pytest.raises(GXAccessRequired):
        convert_gdb_archive(
            source,
            tmp_path / "archive",
            reader_factory=unavailable,
            engine_version="simulated",
        )
    failure = json.loads((tmp_path / "archive.failure.json").read_text())
    assert failure["error"] == "GXAccessRequired: Simulated Seequent checkout canceled"
    assert failure["differences"] is None and failure["channels"] is None
