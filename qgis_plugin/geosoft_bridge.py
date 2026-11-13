"""Executed by a Geosoft Python runtime to inventory/export a GDB."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import site
import sys
import types

import numpy as np


def import_gxpy():
    """Import gxpy in QGIS Python, which intentionally ships without Tk."""
    extra_path = os.environ.get("TERRAWORKBENCH_GEOSOFT_SITE", "").strip()
    if extra_path and extra_path not in sys.path:
        sys.path.insert(0, extra_path)
    # GX Developer 2024.2 supports current QGIS Python but predates NumPy 2,
    # where np.float_ was removed. Keep the alias local to this bridge process.
    if not hasattr(np, "float_"):
        np.float_ = np.float64
    try:
        import tkinter.ttk  # noqa: F401
    except ImportError:
        tkinter = types.ModuleType("tkinter")
        ttk = types.ModuleType("tkinter.ttk")
        tkinter.ttk = ttk
        sys.modules.setdefault("tkinter", tkinter)
        sys.modules.setdefault("tkinter.ttk", ttk)
    from geosoft.gxpy import gdb, gx

    return gdb, gx


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extract-all", action="store_true")
    parser.add_argument("--max-lines", type=int)
    parser.add_argument("--open-archive", action="store_true")
    return parser.parse_args()


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def activate_managed_packages():
    """Expose the profile's managed packages after the host's own stack."""
    folder = os.environ.get("TERRAWORKBENCH_DEPENDENCY_PATH", "").strip()
    if not folder or not os.path.isdir(folder):
        return
    # Packages are built per Python minor version; a desktop GX Python must
    # never load QGIS' compiled wheels.
    if os.path.basename(os.path.normpath(folder)) != f"{sys.version_info.major}.{sys.version_info.minor}":
        return
    known = set(sys.path)
    site.addsitedir(folder)
    # addsitedir appends; keep host-first ordering like the plugin process.
    if folder not in known and folder not in sys.path:
        sys.path.append(folder)


def main():
    activate_managed_packages()
    options = arguments()
    options.input = options.input.resolve()
    options.output = options.output.resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if options.open_archive:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from qgis_plugin.gdb_archive_gx import convert_gdb_archive

        report = convert_gdb_archive(options.input, options.output / (options.input.stem + ".twarchive"))
        print(json.dumps(report), flush=True)
        if not report["verified"]:
            print(json.dumps(report), file=sys.stderr, flush=True)
        return 0 if report["verified"] else 1
    from qgis_plugin.gdb_archive_gx import gx_context_options, gx_working_directory

    context_options = gx_context_options()
    gdb, gx = import_gxpy()
    options.output.mkdir(parents=True, exist_ok=True)
    manifest_path = options.output / f"{options.input.stem}_inventory.json"
    csv_path = options.output / f"{options.input.stem}_all_channels.csv"
    channels_path = options.output / f"{options.input.stem}_channels.csv"
    lines_path = options.output / f"{options.input.stem}_lines.csv"
    manifest = {
        "source": str(options.input),
        "source_format": "Geosoft GeoDatabase",
        "conversion_engine": os.environ.get(
            "TERRAWORKBENCH_GEOSOFT_ENGINE",
            "Geosoft GX Developer public runtime",
        ),
        "channels": [],
        "lines": [],
        "channels_csv": str(channels_path),
        "lines_csv": str(lines_path),
    }
    with gx_working_directory(context_options), gx.GXpy(**context_options):
        database = gdb.Geosoft_gdb.open(str(options.input))
        try:
            channels = list(database.list_channels().keys())
            lines = list(database.list_lines(False).keys())
            if options.max_lines:
                lines = lines[: options.max_lines]
            coordinate_system = database.coordinate_system
            manifest["coordinate_system"] = {
                "name": json_safe(coordinate_system.name),
                "wkt": json_safe(coordinate_system.esri_wkt),
                "json": json_safe(coordinate_system.json),
            }
            manifest["database_metadata"] = json_safe(database.metadata)
            for channel in channels:
                detail = database.channel_details(channel)
                manifest["channels"].append(
                    {
                        "name": channel,
                        "source_format": "Geosoft GeoDatabase",
                        **{str(key): json_safe(value) for key, value in detail.items()},
                    }
                )
            for line in lines:
                detail = database.line_details(line)
                manifest["lines"].append(
                    {
                        "name": line,
                        "source_format": "Geosoft GeoDatabase",
                        **{str(key): json_safe(value) for key, value in detail.items()},
                        "kind": {
                            gdb.LINE_TYPE_NORMAL: "traverse",
                            gdb.LINE_TYPE_TIE: "tie",
                        }.get(detail.get("type"), "other")
                        if detail.get("type") is not None
                        else None,
                    }
                )
            print(
                f"Inventory: {len(lines)} lines, {len(channels)} channels", flush=True
            )
            for path, rows in (
                (channels_path, manifest["channels"]),
                (lines_path, manifest["lines"]),
            ):
                fields = sorted({key for row in rows for key in row})
                with path.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            if options.extract_all:
                header = None
                writer = None
                written = 0
                with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                    for index, line in enumerate(lines, start=1):
                        values, returned, fiducial = database.read_line(
                            line, channels=channels, dtype=np.float64
                        )
                        if values.size == 0:
                            continue
                        returned = list(returned)
                        if header is None:
                            header = returned
                            writer = csv.writer(stream)
                            writer.writerow(
                                ["SOURCE_FORMAT", "LINE", "FIDUCIAL", *header]
                            )
                        column_indices = {
                            name: offset for offset, name in enumerate(returned)
                        }
                        start, increment = fiducial
                        for row_index, row in enumerate(values):
                            writer.writerow(
                                [
                                    "Geosoft GeoDatabase",
                                    line,
                                    start + row_index * increment,
                                    *[
                                        row[column_indices[name]]
                                        if name in column_indices
                                        else ""
                                        for name in header
                                    ],
                                ]
                            )
                        written += values.shape[0]
                        print(f"Line {index}/{len(lines)}: {line}", flush=True)
                manifest["csv"] = str(csv_path)
                manifest["records"] = written
                available = {name.casefold(): name for name in (header or [])}
                wkt = manifest["coordinate_system"]["wkt"] or ""
                if "GEOGCS" in wkt.upper():
                    x_choices = ("LONG", "LONGITUDE", "LON", "P_LONG")
                    y_choices = ("LAT", "LATITUDE", "P_LAT")
                else:
                    x_choices = ("EASTING", "X", "UTM_E", "UTME")
                    y_choices = ("NORTHING", "Y", "UTM_N", "UTMN")
                manifest["x_field"] = next(
                    (
                        available[name.casefold()]
                        for name in x_choices
                        if name.casefold() in available
                    ),
                    "",
                )
                manifest["y_field"] = next(
                    (
                        available[name.casefold()]
                        for name in y_choices
                        if name.casefold() in available
                    ),
                    "",
                )
        finally:
            database.close()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Manifest: {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
