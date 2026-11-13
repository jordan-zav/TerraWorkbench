"""Public GX Developer reader for one-time open archive conversion (no QGIS)."""

from contextlib import contextmanager
import importlib.metadata
import inspect
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np


class GXAccessRequired(RuntimeError):
    """Conversion requires external sign-in/services; no license is reserved."""


class GXArchiveReader:
    """Adapt documented GX channel APIs without resampling or float promotion."""

    def __init__(self, database, gdb_module, utility):
        self.database, self.gdb, self.utility = database, gdb_module, utility

    def inventory(self):
        """Read both name lists independently, before requesting any metadata."""
        result = {"channels": [], "lines": [], "errors": []}
        for field, read in (
            ("channels", self.database.list_channels),
            ("lines", lambda: self.database.list_lines(False)),
        ):
            try:
                result[field] = list(read())
            except Exception as error:
                result["errors"].append({"field": field, "error": f"{type(error).__name__}: {error}"})
        self.inventory_snapshot = result
        return result

    def catalogue(self):
        """Collect complete details, internal metadata and documented properties."""
        db = self.database
        unavailable = []

        def metadata(name, read):
            try:
                return read()
            except Exception as error:
                unavailable.append({"field": name, "error": f"{type(error).__name__}: {error}"})
                return None

        channels = []
        channel_errors = []
        inventory = self.inventory()
        declared_channels = inventory["channels"]
        channel_errors.extend({"line": None, "channel": None,
                               "reason": item["field"] + ": " + item["error"]}
                              for item in inventory["errors"])
        for name in declared_channels:
            try:
                details = dict(db.channel_details(name))
                dtype = np.dtype(db.channel_dtype(name))
                width = db.channel_width(name)
                dummy = np.asarray(self.utility.gx_dummy(dtype), dtype=dtype).item()
                channels.append(
                    {
                        **details,
                        "name": name,
                        "dtype": dtype.str,
                        "array_width": width,
                        "dummy": dummy,
                        "extras": details.copy(),
                    }
                )
            except Exception as error:
                channel_errors.append(
                    {
                        "line": None,
                        "channel": name,
                        "reason": f"Channel metadata unreadable: {error}",
                    }
                )
        lines = []
        for name in inventory["lines"]:
            detail = dict(db.line_details(name))
            detail.update(
                name=name,
                selected=self.gdb.Line(db, name).selected,
                kind={
                    self.gdb.LINE_TYPE_NORMAL: "traverse",
                    self.gdb.LINE_TYPE_TIE: "tie",
                }.get(detail.get("type"), "other"),
            )
            lines.append({**detail, "extras": detail.copy()})
        def coordinate_details():
            cs = db.coordinate_system
            return {"name": cs.name, "esri_wkt": cs.esri_wkt, "gx_json": cs.json}

        coordinate = metadata("coordinate_system", coordinate_details) or {
            "name": None, "esri_wkt": None, "gx_json": None,
        }
        if coordinate["esri_wkt"]:
            try:
                from pyproj import CRS

                coordinate["proj_wkt"] = CRS.from_wkt(coordinate["esri_wkt"]).to_wkt()
            except Exception as error:
                coordinate["proj_wkt_unavailable"] = str(error)
        extras = {}
        # Public read-only properties, including geometry, pass through the robust
        # metadata encoder. Native handles and duplicate source dictionaries are excluded.
        for name, member in inspect.getmembers(type(db)):
            if (
                isinstance(member, property)
                and not name.startswith("_")
                and name
                not in {
                    "gxdb",
                    "gxobj",
                    "metadata",
                    "coordinate_system",
                    "xyz_channels",
                }
            ):
                extras[name] = metadata("extras." + name, lambda: getattr(db, name))
        xyz = metadata("xyz_channels", lambda: db.xyz_channels) or ()
        return {
            "channels": channels,
            "declared_channels": declared_channels,
            "channel_metadata_errors": channel_errors,
            "lines": lines,
            "database_metadata": metadata("database_metadata", lambda: db.metadata),
            "gx_metadata": metadata("gx_metadata", lambda: db.get_gx_metadata().meta_dict()),
            "coordinate_system": coordinate,
            "extras": extras,
            "xyz_channels": xyz,
            "x_field": xyz[0] if xyz else None,
            "y_field": xyz[1] if len(xyz) > 1 else None,
            "metadata_unavailable": unavailable,
            "metadata_complete": not unavailable,
            "inventory": inventory,
        }

    def read(self, line, channel):
        """Return raw native values and fiducials, including original float dummies."""
        db = self.database
        width = db.channel_width(channel)
        if width == 1:
            with db.read_channel_vv(line, channel) as vector:
                return vector.get_data(float_dummies_to_nan=False)
        with db.read_channel_va(line, channel) as vector:
            # GXva.get_data replaces float dummies with NaN. GXVA's documented
            # public NumPy accessor preserves both actual NaNs and raw dummies.
            if not vector.length:
                return np.empty((0, width), dtype=vector.dtype), vector.fid
            raw = vector.gxva.get_array_np(0, 0, vector.length, width, vector.dtype)
            return raw.reshape(-1, width), vector.fid


@contextmanager
def gx_archive_reader(source):
    """Open a copied GDB read-only, without explicit sign-in or checkout calls.

    All GX auxiliary files stay outside the source directory. The native SDK
    may display its own checkout window; this adapter never operates it.
    """
    if os.name != "nt":
        raise GXAccessRequired(
            "GDB conversion requires Windows; converted archives open on any platform"
        )
    from .geosoft_bridge import import_gxpy

    options = gx_context_options()
    gdb, gx = import_gxpy()
    from geosoft import gxapi
    from geosoft.gxpy import utility

    source = Path(source).resolve()
    with gx_working_directory(options):
        try:
            context = gx.GXpy(**options)
        except Exception as error:
            raise GXAccessRequired(str(error)) from error
        with context:
            # Read access is determined by the read-only API, not is_signed_in().
            # A failed read can leave the native handle alive in the traceback;
            # never let temp cleanup mask the real error.
            with tempfile.TemporaryDirectory(
                prefix="tw-gdb-reader-", ignore_cleanup_errors=True
            ) as folder:
                copied = Path(folder) / source.name
                shutil.copyfile(source, copied)
                native = gxapi.GXDB.open_read_only(str(copied), "SUPER", "")
                with gdb.Geosoft_gdb(db=native) as database:
                    yield GXArchiveReader(database, gdb, utility)


@contextmanager
def gx_working_directory(options):
    """Align native relative paths and Python I/O inside the conversion child."""
    folder = options.get("temp_dir")
    if not folder:
        yield
        return
    folder = Path(folder).resolve()
    previous = Path.cwd()
    saved = {key: os.environ.get(key) for key in ("TEMP", "TMP")}
    try:
        os.environ.update(TEMP=str(folder), TMP=str(folder))
        os.chdir(folder)
        yield
    finally:
        os.chdir(previous)
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def gxpy_version():
    """Report the installed public Python package version without loading GX."""
    extra = os.environ.get("TERRAWORKBENCH_GEOSOFT_SITE")
    if extra:
        for distribution in importlib.metadata.distributions(path=[extra]):
            if distribution.metadata.get("Name", "").casefold() == "geosoft":
                return distribution.version
    return importlib.metadata.version("geosoft")


def gx_context_options():
    """Use managed redistributables with writable session folders, never registry discovery."""
    if os.environ.get("TERRAWORKBENCH_GX_DESKTOP") == "1":
        # Explicit legacy bridge: the bundled Oasis Python owns native discovery.
        return {}
    from .geosoft_runtime import managed_gx_runtime
    import importlib.util

    root = os.environ.get("TERRAWORKBENCH_GX_REDIST")
    if not root:
        spec = importlib.util.find_spec("geosoft")
        site = (
            Path(next(iter(spec.submodule_search_locations))).parent
            if spec
            else Path(".")
        )
        root = managed_gx_runtime(site)
    if not root or not (Path(root) / "bin/geodist.dll").is_file():
        raise GXAccessRequired(
            "Prepare GDB conversion support in TerraWorkbench's dependency manager; no manual GX Developer or Oasis montaj installation is needed"
        )
    from .gx_runtime_setup import ensure_runtime_configuration

    try:
        config = ensure_runtime_configuration(root)
    except (OSError, ValueError, UnicodeError) as error:
        raise GXAccessRequired("GX_REDIST_CONFIG: " + str(error)) from error
    from .gx_runtime_check import missing_frameworks

    if any(item["major"] == "6" for item in missing_frameworks(root)):
        raise GXAccessRequired("GX_DOTNET6: Microsoft.NETCore.App / Microsoft.WindowsDesktop.App 6")
    return {
        "suppress_progress": True,
        "redist_override": True,
        "redist_dir": str(root),
        "user_dir": config["user_dir"],
        "temp_dir": config["temp_dir"],
    }


def convert_gdb_archive(
    source,
    destination,
    *,
    verify=True,
    reader_factory=gx_archive_reader,
    engine_version=None,
):
    """Convert an immutable GDB through the public reader and check its identity."""
    if __package__ == "qgis_plugin":
        from terraworkbench_core.gdb_archive import (
            convert_database,
            file_sha256,
            source_provenance,
        )
    else:
        from ..terraworkbench_core.gdb_archive import (
            convert_database,
            file_sha256,
            source_provenance,
        )
    from .metadata_utils import plugin_version
    import json
    import sqlite3

    source, destination = Path(source).resolve(), Path(destination).resolve()
    provenance = source_provenance(
        source, engine_version or gxpy_version(), plugin_version()
    )
    try:
        with reader_factory(source) as reader:
            report = convert_database(reader, destination, provenance, verify=verify)
    except Exception as error:
        failure = {
            "status": "failed",
            "verified": False,
            "lines": None,
            "channels": None,
            "samples": None,
            "differences": None,
            "provenance": provenance,
            "error": f"{type(error).__name__}: {error}",
        }
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.with_name(destination.name + ".failure.json").write_text(
            json.dumps(failure, indent=2), encoding="utf-8"
        )
        raise
    if file_sha256(source) != provenance["source_sha256"]:
        report.update(
            status="incomplete",
            verified=False,
            data_verified=False,
            error="Source changed during conversion",
        )
        (Path(destination) / "verification.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        with sqlite3.connect(Path(destination) / "catalog.sqlite") as catalogue:
            for identity, raw in catalogue.execute(
                "SELECT id, metadata FROM databases"
            ).fetchall():
                metadata = json.loads(raw)
                metadata["gdb_archive_verified"] = False
                catalogue.execute(
                    "UPDATE databases SET metadata=? WHERE id=?",
                    (json.dumps(metadata), identity),
                )
    reasons = [report.get("error", "")] + [
        item["reason"] for item in report["unreadable"] + report["differences"]
    ]
    if any(
        any(
            word in reason.casefold()
            for word in (
                "license",
                "licence",
                "subscription",
                "checkout",
                "sign-in",
                "entitlement",
            )
        )
        for reason in reasons
    ):
        report["access_required"] = True
        (Path(destination) / "verification.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    return report
