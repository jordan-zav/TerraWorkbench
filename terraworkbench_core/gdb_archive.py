"""Typed open survey archives with independent, exact source verification.

The writer accepts a reader protocol (catalogue/read); it never imports Geosoft,
Qt or QGIS. SurveyStore format 1 is extended with additive archive tables.
"""

from datetime import date, datetime, time, timezone
import base64
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import numpy as np

from .survey_store import SurveyStore, _arrow, _now

ARCHIVE_VERSION = 1


def encode_metadata(value, *, conversions=None):
    """Represent metadata safely and record typed conversions and unknown values.

    Sample arrays use the separate native-data path. Unknown metadata never
    aborts conversion or silently claims complete, lossless metadata.
    """
    changes = [] if conversions is None else conversions

    def note(path, item, representation, lossy=False, **details):
        changes.append({"path": path, "type": type(item).__name__,
                        "representation": representation, "lossy": lossy, **details})

    def unknown(item, path, reason=None):
        try:
            description = repr(item)
        except Exception as error:
            description = "<repr failed: " + type(error).__name__ + ": " + str(error) + ">"
        note(path, item, "type/repr", True, **({"error": reason} if reason else {}))
        return {"type": type(item).__name__, "repr": description}

    def encode(item, path, ancestors):
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, np.datetime64):
            note(path, item, "ISO date")
            return np.datetime_as_string(item)
        if isinstance(item, np.generic):
            note(path, item, "Python scalar", dtype=item.dtype.str)
            scalar = item.item()
            if isinstance(scalar, np.generic):
                return unknown(item, path, "NumPy scalar has no Python scalar equivalent")
            return encode(scalar, path, ancestors)
        if isinstance(item, float):
            if not np.isfinite(item) or (item == 0 and np.signbit(item)):
                return {"$float64": base64.b64encode(np.float64(item).tobytes()).decode()}
            return item
        if isinstance(item, (datetime, date, time)):
            note(path, item, "ISO date/time")
            return item.isoformat()
        if isinstance(item, bytes):
            return {"$bytes": base64.b64encode(item).decode()}
        if id(item) in ancestors or len(ancestors) > 40:
            return unknown(item, path, "Cyclic or excessively nested metadata")
        ancestors = ancestors | {id(item)}
        if isinstance(item, np.ndarray):
            note(path, item, "list", True, dtype=item.dtype.str, shape=list(item.shape))
            return encode(item.tolist(), path, ancestors)
        if isinstance(item, dict):
            if all(isinstance(k, str) for k in item):
                return {k: encode(v, path + "." + k if path else k, ancestors) for k, v in item.items()}
            return {"$mapping": [[encode(k, path + ".key", ancestors), encode(v, path + ".value", ancestors)] for k, v in item.items()]}
        if isinstance(item, (tuple, list)):
            values = [encode(v, path + "[" + str(i) + "]", ancestors) for i, v in enumerate(item)]
            return {"$tuple": values} if isinstance(item, tuple) else values
        try:
            if hasattr(item, "xyz"):
                coordinates = item.xyz
            elif hasattr(item, "p0") and hasattr(item, "p1"):
                coordinates = [getattr(point, "xyz", point) for point in (item.p0, item.p1)]
            elif hasattr(item, "pp"):
                coordinates = item.pp
            else:
                return unknown(item, path)
            def coordinate_lists(values):
                if isinstance(values, np.ndarray):
                    values = values.tolist()
                if isinstance(values, (tuple, list)):
                    return [coordinate_lists(v) for v in values]
                return values

            coordinates = coordinate_lists(coordinates)
            result = {"type": type(item).__name__, "coordinates": encode(coordinates, path + ".coordinates", ancestors)}
            cs = getattr(item, "coordinate_system", None)
            if cs is not None:
                reference = {}
                for label, attributes in (("name", ("name",)), ("wkt", ("esri_wkt", "wkt"))):
                    for attribute in attributes:
                        try:
                            text = getattr(cs, attribute, None)
                            if isinstance(text, str) and text:
                                reference[label] = text
                                break
                        except Exception as error:
                            note(path + ".coordinate_system." + attribute, cs, "unavailable", True, error=str(error))
                if isinstance(cs, str):
                    reference["name"] = cs
                if reference:
                    result["coordinate_system"] = reference
            note(path, item, "coordinates and coordinate system")
            return result
        except Exception as error:
            return unknown(item, path, type(error).__name__ + ": " + str(error))

    return encode(value, "", frozenset())


def file_sha256(path):
    """Hash a source or artifact using bounded reads."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _type(channel):
    pa, _ = _arrow()
    dtype = np.dtype(channel["dtype"])
    if dtype.kind == "U":
        result = pa.string()
    elif dtype.kind in "iuf" and dtype.itemsize in (1, 2, 4, 8):
        result = pa.from_numpy_dtype(dtype.newbyteorder("="))
    else:
        raise ValueError(f"Unsupported native channel type: {dtype}")
    width = channel["array_width"]
    return pa.list_(result, width) if width > 1 else result


def _samples(reader, line, channel):
    values, fid = reader.read(line, channel["name"])
    values = np.asarray(values)
    dtype = np.dtype(channel["dtype"])
    width = channel["array_width"]
    if values.dtype != dtype:
        raise ValueError(f"Native type changed: {values.dtype} != {dtype}")
    if values.shape != ((len(values), width) if width > 1 else (len(values),)):
        raise ValueError("Channel array width does not match its metadata")
    if len(fid) != 2 or not np.isfinite(fid).all() or fid[1] == 0:
        raise ValueError("Invalid channel fiducial start/increment")
    dummy = np.asarray(channel["dummy"], dtype=dtype).item()
    mask = (
        np.isnan(values) if dtype.kind == "f" and np.isnan(dummy) else values == dummy
    )
    return values, np.asarray(mask, dtype=bool), (float(fid[0]), float(fid[1]))


def _column(values, mask, channel, rows):
    pa, _ = _arrow()
    dtype = np.dtype(channel["dtype"])
    width = channel["array_width"]
    shape = (rows, width) if width > 1 else (rows,)
    padded = np.zeros(shape, dtype=dtype)
    nulls = np.ones(shape, dtype=bool)
    padded[: len(values)], nulls[: len(values)] = values, mask
    field_type = _type(channel)
    flat_type = field_type.value_type if width > 1 else field_type
    flat_values = (
        padded.reshape(-1).tolist() if dtype.kind == "U" else padded.reshape(-1)
    )
    flat = pa.array(
        flat_values, mask=nulls.reshape(-1), type=flat_type, from_pandas=False
    )
    return pa.FixedSizeListArray.from_arrays(flat, width) if width > 1 else flat


def _compare(column, raw, mask, channel):
    pa, _ = _arrow()
    column = column.combine_chunks().slice(0, len(raw))
    if channel["array_width"] > 1:
        column = column.values
    nulls = column.is_null().to_numpy(zero_copy_only=False)
    expected = mask.reshape(-1)
    if not np.array_equal(nulls, expected):
        return "null/dummy positions differ"
    dtype = np.dtype(channel["dtype"])
    if dtype.kind == "U":
        actual = np.array(column.fill_null("").to_pylist(), dtype=dtype)
        equal = np.array_equal(actual[~nulls], raw.reshape(-1)[~expected])
    else:
        actual = column.fill_null(pa.scalar(0, type=column.type)).to_numpy(
            zero_copy_only=False
        )
        # Comparing bytes preserves signed zero and non-dummy NaN payloads.
        native = dtype.newbyteorder("=")
        equal = (
            actual[~nulls].astype(native, copy=False).tobytes()
            == raw.reshape(-1)[~expected].astype(native, copy=False).tobytes()
        )
    return None if equal else "native values/bits differ"


def convert_database(reader, output, provenance, *, verify=True, canceled=None):
    """Archive all channels/lines and verify a second independent source read.

    A failed conversion leaves a diagnostic archive marked incomplete. Existing
    destinations are never overwritten. Memory use is bounded by one source line.
    """
    pa, pq = _arrow()
    root = Path(output).resolve()
    if root.exists():
        raise FileExistsError(root)
    store = SurveyStore(root, create=True)
    report = {
        "schema_version": ARCHIVE_VERSION,
        "status": "incomplete",
        "verified": False,
        "data_verified": False,
        "differences": [],
        "unreadable": [],
        "lines": 0,
        "channels": 0,
        "samples": 0,
        "array_channels": 0,
        "channel_samples": 0,
        "verify_requested": verify,
    }
    manifest = {
        "format": "TerraWorkbench GDB open archive",
        "schema_version": ARCHIVE_VERSION,
        "survey_store_version": 1,
        "provenance": encode_metadata(provenance),
    }
    try:
        catalogue = reader.catalogue()
        channels, lines = catalogue["channels"], catalogue["lines"]
        report["unreadable"].extend(catalogue.get("channel_metadata_errors", []))
        report.update(
            metadata_unavailable=catalogue.get("metadata_unavailable", []),
            metadata_complete=catalogue.get("metadata_complete", True),
            lines=len(lines),
            channels=len(catalogue.get("declared_channels", channels)),
            array_channels=sum(c["array_width"] > 1 for c in channels),
        )
        names = [c["name"] for c in channels]
        if not channels or not lines or len(set(names)) != len(names):
            raise ValueError("Archive requires unique channels and at least one line")
        used = {"LINE", "FIDUCIAL", *names}
        for channel in channels:
            field = channel["name"]
            if field in {"LINE", "FIDUCIAL"}:
                field = "CHANNEL_" + field
                while field in used:
                    field = "CHANNEL_" + field
            channel["archive_field"] = field
            used.add(field)
        conversions = []
        manifest.update(encode_metadata(catalogue, conversions=conversions))
        report["metadata_conversions"] = conversions
        report["metadata_complete"] = report["metadata_complete"] and not any(item["lossy"] for item in conversions)
        manifest["metadata_conversions"] = conversions
        manifest["metadata_complete"] = report["metadata_complete"]
        schema = pa.schema(
            [("LINE", pa.string()), ("FIDUCIAL", pa.float64())]
            + [(c["archive_field"], _type(c)) for c in channels]
        )
        path = root / "databases/samples.parquet"
        alignment = []
        line_records = []
        row_group = 0
        with pq.ParquetWriter(
            path, schema, compression="zstd", use_dictionary=False
        ) as writer:
            for line in lines:
                if canceled and canceled():
                    raise InterruptedError("Archive conversion canceled")
                data = {}
                for channel in channels:
                    try:
                        data[channel["name"]] = _samples(reader, line["name"], channel)
                    except Exception as error:
                        report["unreadable"].append(
                            {
                                "line": line["name"],
                                "channel": channel["name"],
                                "reason": str(error),
                            }
                        )
                rows = max((len(v[0]) for v in data.values()), default=0)
                ref = catalogue.get("x_field")
                ref = ref if ref in data else next(iter(data), None)
                ref_values, _, fid = data[ref] if ref else ([], [], (0.0, 1.0))
                fids = fid[0] + np.arange(rows, dtype=np.float64) * fid[1]
                arrays = [
                    pa.array([line["name"]] * rows),
                    pa.array(fids, mask=np.arange(rows) >= len(ref_values)),
                ]
                for channel in channels:
                    name = channel["name"]
                    if name in data:
                        raw, nulls, pair = data[name]
                    else:
                        raw = np.empty(
                            (0, channel["array_width"])
                            if channel["array_width"] > 1
                            else (0,),
                            dtype=channel["dtype"],
                        )
                        nulls, pair = np.ones(raw.shape, dtype=bool), (0.0, 1.0)
                    arrays.append(_column(raw, nulls, channel, rows))
                    alignment.append(
                        {
                            "line": line["name"],
                            "channel": name,
                            "start": pair[0],
                            "increment": pair[1],
                            "length": len(raw),
                        }
                    )
                    report["channel_samples"] += len(raw)
                groups = list(range(row_group, row_group + (rows + 65535) // 65536))
                if rows:
                    writer.write_table(
                        pa.Table.from_arrays(arrays, schema=schema),
                        row_group_size=65536,
                    )
                row_group += len(groups)
                line_records.append(
                    {
                        **line,
                        "row_offset": report["samples"],
                        "rows": rows,
                        "reference_channel": ref,
                        "fid_start": fid[0],
                        "fid_increment": fid[1],
                        "row_groups": groups,
                    }
                )
                report["samples"] += rows
        manifest["alignment"] = alignment
        manifest["line_layout"] = encode_metadata(line_records)
        by_pair = {
            (row["line"], row["channel"]): (
                row["start"],
                row["increment"],
                row["length"],
            )
            for row in alignment
        }
        map_columns, map_omissions = ["LINE", "FIDUCIAL"], []
        for channel in channels:
            reason = None
            if channel["array_width"] > 1:
                reason = "Array values remain in Parquet"
            elif any(
                line["reference_channel"] is not None
                and by_pair[(line["name"], channel["name"])]
                != by_pair[(line["name"], line["reference_channel"])]
                for line in line_records
            ):
                reason = "Different fiducials/length; values remain in Parquet without resampling"
            if reason:
                map_omissions.append({"channel": channel["name"], "reason": reason})
            else:
                map_columns.append(channel["archive_field"])
        manifest.update(map_columns=map_columns, map_omissions=map_omissions)
        if verify:
            with pq.ParquetFile(path) as archive:
                for line in line_records:
                    for channel in channels:
                        if canceled and canceled():
                            raise InterruptedError("Archive verification canceled")
                        try:
                            raw, mask, fid = _samples(reader, line["name"], channel)
                            item = next(
                                a
                                for a in alignment
                                if a["line"] == line["name"]
                                and a["channel"] == channel["name"]
                            )
                            if (len(raw), *fid) != (
                                item["length"],
                                item["start"],
                                item["increment"],
                            ):
                                raise ValueError(
                                    "Source sample count/fiducials changed"
                                )
                            field = channel["archive_field"]
                            column = archive.read_row_groups(
                                line["row_groups"], columns=[field]
                            )[field]
                            difference = _compare(column, raw, mask, channel)
                            if difference:
                                raise ValueError(difference)
                        except Exception as error:
                            report["differences"].append(
                                {
                                    "line": line["name"],
                                    "channel": channel["name"],
                                    "reason": str(error),
                                }
                            )
        report["verified"] = bool(
            verify and not report["differences"] and not report["unreadable"]
        )
        report["data_verified"] = report["verified"]
        report["status"] = (
            "verified"
            if report["verified"]
            else "incomplete"
            if verify
            else "unverified"
        )
        manifest["parquet_sha256"] = file_sha256(path)
        database_id = _register(store, manifest, path, schema, report)
        manifest["database_id"] = database_id
    except Exception as error:
        report.update(verified=False, status="incomplete")
        report["error"] = f"{type(error).__name__}: {error}"
    _json(root / "archive.json", manifest)
    _json(root / "verification.json", report)
    return report


def _register(store, manifest, path, schema, report):
    database_id = uuid.uuid4().hex
    fields = {c["name"]: c["archive_field"] for c in manifest["channels"]}
    metadata = {
        "source_format": manifest["format"],
        "crs": manifest.get("coordinate_system", {}).get("proj_wkt")
        or manifest.get("coordinate_system", {}).get("esri_wkt"),
        "x_field": fields.get(manifest.get("x_field")),
        "y_field": fields.get(manifest.get("y_field")),
        "line_field": "LINE",
        "line_metadata": {line["name"]: line for line in manifest["lines"]},
        "gdb_archive_schema": ARCHIVE_VERSION,
        "gdb_archive_verified": report["verified"],
        "database_metadata": manifest.get("database_metadata"),
        "gx_metadata": manifest.get("gx_metadata"),
        "archive_provenance": manifest["provenance"],
        "gdb_map_columns": manifest.get("map_columns"),
        "gdb_map_omissions": manifest.get("map_omissions", []),
    }
    with store._connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS gdb_archives(database_id TEXT PRIMARY KEY, schema_version INTEGER, metadata_json TEXT);
            CREATE TABLE IF NOT EXISTS gdb_channels(database_id TEXT, name TEXT, alias_json TEXT, unit_json TEXT,
                description_json TEXT, native_type TEXT, array_width INTEGER, decimals_json TEXT,
                format_json TEXT, dummy_json TEXT, class_json TEXT, protection_json TEXT, extras_json TEXT,
                metadata_json TEXT, PRIMARY KEY(database_id,name));
            CREATE TABLE IF NOT EXISTS gdb_lines(database_id TEXT, name TEXT, number_json TEXT, type_json TEXT,
                version_json TEXT, flight_json TEXT, date_json TEXT, fid_start REAL, fid_increment REAL,
                selection_json TEXT, extras_json TEXT, metadata_json TEXT, PRIMARY KEY(database_id,name));
            CREATE TABLE IF NOT EXISTS gdb_channel_lines(database_id TEXT, line TEXT, channel TEXT, fid_start REAL,
                fid_increment REAL, sample_count INTEGER, PRIMARY KEY(database_id,line,channel));
        """)
        base = Path(manifest["provenance"].get("source_path", "GDB open archive")).stem
        name, suffix = base, 2
        names = {row[0] for row in db.execute("SELECT name FROM databases")}
        while name in names:
            name, suffix = f"{base} ({suffix})", suffix + 1
        db.execute(
            "INSERT INTO databases VALUES(?,?,?,?,?,?)",
            (
                database_id,
                name,
                report["samples"],
                manifest["provenance"].get("source_path", ""),
                json.dumps(metadata),
                _now(),
            ),
        )
        db.execute(
            "INSERT INTO gdb_archives VALUES(?,?,?)",
            (database_id, ARCHIVE_VERSION, json.dumps(manifest)),
        )
        for field in schema:
            channel_id = uuid.uuid4().hex
            detail = next(
                (c for c in manifest["channels"] if c["archive_field"] == field.name),
                {},
            )
            db.execute(
                "INSERT INTO channels VALUES(?,?,?,?)",
                (channel_id, database_id, field.name, detail.get("unit") or ""),
            )
            db.execute(
                "INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    channel_id,
                    1,
                    path.relative_to(store.root).as_posix(),
                    field.name,
                    str(field.type),
                    json.dumps(
                        {
                            "operation": "gdb_open_archive",
                            "schema_version": ARCHIVE_VERSION,
                        }
                    ),
                    _now(),
                ),
            )
            if detail:
                db.execute(
                    "INSERT INTO gdb_channels VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        database_id,
                        field.name,
                        json.dumps(detail.get("alias", detail.get("label"))),
                        json.dumps(detail.get("unit")),
                        json.dumps(detail.get("description")),
                        detail["dtype"],
                        detail["array_width"],
                        json.dumps(detail.get("decimal")),
                        json.dumps(detail.get("format")),
                        json.dumps(detail.get("dummy")),
                        json.dumps(detail.get("class")),
                        json.dumps(detail.get("protect")),
                        json.dumps(detail.get("extras")),
                        json.dumps(detail),
                    ),
                )
        for line in manifest["line_layout"]:
            db.execute(
                "INSERT INTO gdb_lines VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    database_id,
                    line["name"],
                    json.dumps(line.get("number")),
                    json.dumps(line.get("type")),
                    json.dumps(line.get("version")),
                    json.dumps(line.get("flight")),
                    json.dumps(line.get("date")),
                    line["fid_start"],
                    line["fid_increment"],
                    json.dumps(line.get("selected")),
                    json.dumps(line.get("extras")),
                    json.dumps(line),
                ),
            )
        db.executemany(
            "INSERT INTO gdb_channel_lines VALUES(?,?,?,?,?,?)",
            [
                (
                    database_id,
                    a["line"],
                    a["channel"],
                    a["start"],
                    a["increment"],
                    a["length"],
                )
                for a in manifest["alignment"]
            ],
        )
        store._event(db, database_id, "gdb_open_archive", report)
    return database_id


def open_archive(path, *, require_verified=True, check_integrity=True):
    """Open a folder, JSON, SQLite or Parquet archive entry without Geosoft.

    The return value is (SurveyStore, database_id, manifest). Unverified or
    incomplete conversions are refused by default, even when readable.
    """
    root = Path(path).resolve()
    if root.is_file():
        root = root.parent.parent if root.suffix.lower() == ".parquet" else root.parent
    manifest = json.loads((root / "archive.json").read_text(encoding="utf-8"))
    report = json.loads((root / "verification.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != ARCHIVE_VERSION:
        raise ValueError("Unsupported GDB open archive schema")
    if require_verified and (not report["verified"] or report["status"] != "verified"):
        raise ValueError(
            "Archive conversion was not verified; inspect verification.json"
        )
    if (
        check_integrity
        and file_sha256(root / "databases/samples.parquet")
        != manifest["parquet_sha256"]
    ):
        raise ValueError("Archive Parquet checksum differs")
    return SurveyStore(root), manifest["database_id"], manifest


def source_provenance(path, gxpy_version, terraworkbench_version):
    """Record the immutable source identity and conversion software versions."""
    path = Path(path).resolve()
    info = path.stat()
    return {
        "source_path": str(path),
        "source_bytes": info.st_size,
        "source_mtime_ns": info.st_mtime_ns,
        "source_sha256": file_sha256(path),
        "source_date_utc": datetime.fromtimestamp(
            info.st_mtime, timezone.utc
        ).isoformat(),
        "converted_utc": _now(),
        "gxpy_version": gxpy_version,
        "terraworkbench_version": terraworkbench_version,
        "schema_version": ARCHIVE_VERSION,
    }


def attach_archive(store, path, canceled=None):
    """Add a verified archive to an existing SurveyStore without changing its API."""
    source, _, manifest = open_archive(path)
    if canceled and canceled():
        raise InterruptedError("Archive import canceled")
    target = store.root / "results" / f"gdb_archive_{uuid.uuid4().hex}.parquet"
    shutil.copyfile(source.root / "databases/samples.parquet", target)
    if file_sha256(target) != manifest["parquet_sha256"]:
        raise ValueError("Copied archive checksum differs")
    _, pq = _arrow()
    with pq.ParquetFile(target) as parquet:
        schema = parquet.schema_arrow
    report = json.loads((source.root / "verification.json").read_text(encoding="utf-8"))
    return _register(store, manifest, target, schema, report)
