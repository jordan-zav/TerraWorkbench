"""Versioned, column-selective survey storage (SQLite catalogue + Parquet).

No QGIS imports. Original files are read-only inputs; published Parquet files
are immutable. Catalogue transactions expose complete files only. A crash
before publication can leave an unreferenced file, never a partial channel.
"""

from contextlib import contextmanager, ExitStack
import ast
import csv
from datetime import datetime, timezone
import json
from itertools import zip_longest
import operator
from pathlib import Path
import sqlite3
import uuid

import numpy as np

BATCH_SIZE = 65536
FORMAT_VERSION = 1


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Install pyarrow through TerraWorkbench Dependencies before using survey databases.") from error
    return pa, pq


def _now():
    return datetime.now(timezone.utc).isoformat()


def _name(value):
    value = str(value).strip()
    if not value or len(value) > 200 or "\x00" in value:
        raise ValueError("Names must contain 1–200 characters and no NUL.")
    return value


def _check_cancel(canceled):
    if canceled and canceled():
        raise InterruptedError("Operation canceled; original data unchanged.")


class Formula:
    """Small arithmetic language: c('channel'), + - * / **, abs/sqrt/log10.

    Parses an allowlisted AST; never uses Python eval or executes user code.
    """

    functions = {"abs": np.abs, "sqrt": np.sqrt, "log10": np.log10}
    operations = {ast.Add: operator.add, ast.Sub: operator.sub,
                  ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}

    def __init__(self, expression):
        if len(expression) > 2048:
            raise ValueError("Formula is too long.")
        try:
            self.tree = ast.parse(expression, mode="eval").body
        except SyntaxError as error:
            raise ValueError("Invalid formula syntax.") from error
        if sum(1 for _ in ast.walk(self.tree)) > 128:
            raise ValueError("Formula is too complex.")
        self.channels = set()
        self._validate(self.tree)
        if not self.channels:
            raise ValueError("Formula must reference at least one channel using c('name').")

    def _validate(self, node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not np.isfinite(float(node.value)):
                raise ValueError("Constants must be finite.")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            self._validate(node.operand)
        elif isinstance(node, ast.BinOp) and type(node.op) in self.operations:
            if isinstance(node.op, ast.Pow) and not (
                isinstance(node.right, ast.Constant) and type(node.right.value) in (int, float)
                and 0 <= node.right.value <= 16
            ):
                raise ValueError("Power must be a constant between 0 and 16.")
            self._validate(node.left)
            self._validate(node.right)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords:
            if node.func.id == "c" and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.channels.add(node.args[0].value)
            elif node.func.id in self.functions:
                self._validate(node.args[0])
            else:
                raise ValueError("Use c('channel'), abs, sqrt or log10.")
        else:
            raise ValueError("Unsupported formula expression.")

    def calculate(self, arrays):
        def visit(node):
            if isinstance(node, ast.Constant):
                return float(node.value)
            if isinstance(node, ast.UnaryOp):
                return -visit(node.operand) if isinstance(node.op, ast.USub) else visit(node.operand)
            if isinstance(node, ast.BinOp):
                return self.operations[type(node.op)](visit(node.left), visit(node.right))
            if node.func.id == "c":
                return arrays[node.args[0].value]
            return self.functions[node.func.id](visit(node.args[0]))
        with np.errstate(all="ignore"):
            return np.asarray(visit(self.tree), dtype=float)


class SurveyStore:
    def __init__(self, root, create=False):
        self.root = Path(root).expanduser().resolve()
        self.catalogue = self.root / "catalog.sqlite"
        if not self.catalogue.exists():
            if not create:
                raise ValueError("This folder is not a TerraWorkbench survey project.")
            self.root.mkdir(parents=True, exist_ok=True)
            # Never claim an existing populated directory as a new project.
            if any(self.root.iterdir()):
                raise ValueError("Choose an empty folder to create a new survey project.")
            with self._connection() as db:
                db.executescript("""
                    CREATE TABLE project(format_version INTEGER NOT NULL);
                    INSERT INTO project VALUES (1);
                    CREATE TABLE databases(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                      rows INTEGER NOT NULL, source TEXT NOT NULL, metadata TEXT NOT NULL, created TEXT NOT NULL);
                    CREATE TABLE channels(id TEXT PRIMARY KEY, database_id TEXT NOT NULL REFERENCES databases(id),
                      name TEXT NOT NULL, unit TEXT NOT NULL, UNIQUE(database_id, name));
                    CREATE TABLE versions(id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES channels(id),
                      number INTEGER NOT NULL, path TEXT NOT NULL, field TEXT NOT NULL,
                      data_type TEXT NOT NULL, provenance TEXT NOT NULL, created TEXT NOT NULL,
                      UNIQUE(channel_id, number));
                    CREATE INDEX version_channel ON versions(channel_id, number);
                    CREATE TABLE events(id INTEGER PRIMARY KEY, database_id TEXT NOT NULL,
                      action TEXT NOT NULL, details TEXT NOT NULL, created TEXT NOT NULL);
                """)
            for folder in ("databases", "grids", "results", "recipes"):
                (self.root / folder).mkdir()
        with self._connection() as db:
            if db.execute("SELECT format_version FROM project").fetchone()[0] != FORMAT_VERSION:
                raise ValueError("Unsupported project format version.")

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.catalogue, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Catalogue path escapes the project.")
        return path

    def databases(self):
        with self._connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM databases ORDER BY name")]

    def channels(self, database_id):
        with self._connection() as db:
            return [dict(row) for row in db.execute("""
                SELECT c.*, v.id AS version_id, v.number, v.path, v.field, v.data_type, v.provenance
                FROM channels c JOIN versions v ON c.id=v.channel_id
                WHERE c.database_id=? AND v.number=(SELECT MAX(number) FROM versions WHERE channel_id=c.id)
                ORDER BY c.name""", (database_id,))]

    def history(self, database_id):
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM events WHERE database_id=? ORDER BY id", (database_id,))]

    @staticmethod
    def _event(db, database_id, action, details):
        db.execute("INSERT INTO events(database_id,action,details,created) VALUES(?,?,?,?)",
                   (database_id, action, json.dumps(details, ensure_ascii=False), _now()))

    def channel_pipeline(self, database_id, channel, limit=200):
        """Resolve immutable version ancestry, including formulas and aliases.

        Labels use current channel names; edges use exact historical version IDs.
        Missing or malformed references are errors, never invented ancestors.
        """
        root = self._snapshot(database_id, [channel])[0]["version_id"]
        nodes, edges, pending = {}, [], [root]
        with self._connection() as db:
            while pending:
                version = pending.pop()
                if version in nodes:
                    continue
                if len(nodes) >= limit:
                    raise ValueError(f"Pipeline exceeds the {limit}-node display limit.")
                row = db.execute("""SELECT v.*, c.name, c.unit, c.database_id FROM versions v
                    JOIN channels c ON c.id=v.channel_id WHERE v.id=?""", (version,)).fetchone()
                if row is None or row["database_id"] != database_id:
                    raise ValueError("Pipeline references a missing or foreign channel version.")
                node = dict(row)
                node["provenance"] = json.loads(node["provenance"])
                nodes[version] = node
                provenance = node["provenance"]
                inputs = dict(provenance.get("inputs", {}))
                if "input_version" in provenance:
                    inputs["source"] = provenance["input_version"]
                for name, parent in inputs.items():
                    edges.append({"source": parent, "target": version, "input_name": name})
                    pending.append(parent)
        return {"root": root, "nodes": nodes, "edges": edges}

    def import_file(self, source, name=None, delimiter=",", metadata=None, canceled=None, progress=None, text_options=None):
        pa, pq = _arrow()
        source = Path(source).resolve()
        name = _name(name or source.stem)
        before = source.stat()
        if text_options is not None and text_options.source_size >= 0 and (
            text_options.source_size, text_options.source_mtime_ns
        ) != (before.st_size, before.st_mtime_ns):
            raise ValueError("Source changed since the reviewed preview; inspect it again before importing.")
        database_id = uuid.uuid4().hex
        folder = self._path("databases/" + database_id)
        folder.mkdir(parents=True)
        staging, target = folder / "original.partial", folder / "original.parquet"
        rows = 0
        try:
            with ExitStack() as stack:
                if source.suffix.lower() == ".parquet":
                    if text_options is not None:
                        raise ValueError("Text options do not apply to Parquet inputs.")
                    reader = stack.enter_context(pq.ParquetFile(source))
                    schema, batches = reader.schema_arrow, reader.iter_batches(batch_size=BATCH_SIZE)
                elif text_options is not None:
                    if __package__:
                        from .text_import import arrow_batches
                    else:
                        from text_import import arrow_batches
                    schema, batches = arrow_batches(source, text_options, canceled=canceled)
                    stack.callback(batches.close)
                else:
                    import pyarrow.csv as arrow_csv
                    if delimiter not in (",", ";", "\t"):
                        raise ValueError("Choose comma, semicolon or tab as delimiter.")
                    with source.open(encoding="utf-8-sig", newline="") as handle:
                        names = next(csv.reader(handle, delimiter=delimiter))
                    if not names or any(not n.strip() for n in names) or len(set(names)) != len(names):
                        raise ValueError("CSV requires unique, non-empty header names.")
                    reader = stack.enter_context(arrow_csv.open_csv(source,
                        parse_options=arrow_csv.ParseOptions(delimiter=delimiter),
                        convert_options=arrow_csv.ConvertOptions(column_types={n: pa.string() for n in names},
                            strings_can_be_null=True, null_values=[""])))
                    schema, batches = reader.schema, reader
                if len(set(schema.names)) != len(schema.names) or not len(schema):
                    raise ValueError("Input requires unique channel names.")
                for field in schema:
                    _name(field.name)
                    if pa.types.is_nested(field.type):
                        raise ValueError("Nested Parquet columns are not supported as survey channels.")
                writer = stack.enter_context(pq.ParquetWriter(staging, schema, compression="zstd"))
                for batch in batches:
                    _check_cancel(canceled)
                    writer.write_batch(batch, row_group_size=BATCH_SIZE)
                    rows += batch.num_rows
                    if progress:
                        progress(rows)
            if rows == 0:
                raise ValueError("The input contains no observations.")
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed during import; retry from a stable copy.")
            _check_cancel(canceled)
            staging.replace(target)
            provenance = {"operation": "import", "source": str(source),
                          "source_bytes": before.st_size, "source_mtime_ns": before.st_mtime_ns,
                          "csv_columns": "UTF-8 strings, numeric conversion on calculation"}
            if source.suffix.lower() == ".parquet":
                provenance.pop("csv_columns")
                provenance["format"] = "Parquet"
            import_metadata = dict(metadata or {})
            if text_options is not None:
                provenance.pop("csv_columns")
                provenance["text_import"] = text_options.to_dict()
                import_metadata["text_import"] = text_options.to_dict()
                import_metadata["channel_roles"] = {}
            units = {c.name: c.unit for c in text_options.columns} if text_options is not None else {}
            roles = {c.name: c.role for c in text_options.columns if c.role} if text_options is not None else {}
            with self._connection() as db:
                db.execute("INSERT INTO databases VALUES(?,?,?,?,?,?)", (database_id, name, rows,
                           str(source), json.dumps(import_metadata), _now()))
                for field in schema:
                    channel_id = uuid.uuid4().hex
                    if field.name in roles:
                        import_metadata["channel_roles"][roles[field.name]] = channel_id
                    db.execute("INSERT INTO channels VALUES(?,?,?,?)", (channel_id, database_id, field.name, units.get(field.name, "")))
                    db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)", (
                        uuid.uuid4().hex, channel_id, 1, target.relative_to(self.root).as_posix(),
                        field.name, str(field.type), json.dumps(provenance), _now()))
                db.execute("UPDATE databases SET metadata=? WHERE id=?", (json.dumps(import_metadata), database_id))
                self._event(db, database_id, "import", provenance)
            return database_id
        except BaseException:
            staging.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            folder.rmdir()
            raise

    def _snapshot(self, database_id, names):
        available = {row["name"]: row for row in self.channels(database_id)}
        if not names or len(set(names)) != len(names):
            raise ValueError("Select at least one channel, without duplicates.")
        if any(name not in available for name in names):
            raise ValueError("Unknown channel selected.")
        return [available[name] for name in names]

    def _batches(self, snapshot, batch_size=BATCH_SIZE, canceled=None):
        pa, pq = _arrow()
        if not 1 <= batch_size <= BATCH_SIZE:
            raise ValueError("Batch size must be between 1 and 65536.")
        groups = {}
        for channel in snapshot:
            groups.setdefault(channel["path"], set()).add(channel["field"])
        with ExitStack() as stack:
            readers = {path: stack.enter_context(pq.ParquetFile(self._path(path))) for path in groups}
            with self._connection() as db:
                expected_rows = db.execute("SELECT rows FROM databases WHERE id=?", (snapshot[0]["database_id"],)).fetchone()[0]
            if any(r.metadata.num_rows != expected_rows for r in readers.values()):
                raise ValueError("Channel lengths disagree; project data is damaged.")
            iterators = [readers[path].iter_batches(batch_size=batch_size, columns=sorted(fields))
                         for path, fields in groups.items()]
            for chunks in zip_longest(*iterators):
                _check_cancel(canceled)
                if any(chunk is None for chunk in chunks) or len({len(chunk) for chunk in chunks}) != 1:
                    raise ValueError("Channel batches are not row-aligned.")
                by_path = dict(zip(groups, chunks))
                yield pa.RecordBatch.from_arrays([
                    by_path[c["path"]].column(by_path[c["path"]].schema.get_field_index(c["field"]))
                    for c in snapshot], names=[c["name"] for c in snapshot])

    def batches(self, database_id, names, batch_size=BATCH_SIZE, filters=None, canceled=None):
        """Only selected columns plus filter columns are read. Row order is stable.

        Filters are membership tests, e.g. {'line': ['L1', 'L2']}. They scan
        their selected columns; this is not yet a spatial or line index.
        """
        import pyarrow.compute as pc
        pa, _ = _arrow()
        filters = filters or {}
        if not names or len(set(names)) != len(names):
            raise ValueError("Select at least one channel, without duplicates.")
        snapshot = self._snapshot(database_id, list(dict.fromkeys([*names, *filters])))
        for batch in self._batches(snapshot, batch_size, canceled):
            for name, values in filters.items():
                array = batch.column(batch.schema.get_field_index(name))
                choices = pa.array(values).cast(array.type)
                batch = batch.filter(pc.is_in(array, value_set=choices))
            if batch.num_rows:
                yield batch.select(names)

    def derive(self, database_id, output_name, expression, unit="", canceled=None, progress=None):
        pa, pq = _arrow()
        formula, output_name = Formula(expression), _name(output_name)
        snapshot = self._snapshot(database_id, sorted(formula.channels))
        version_id = uuid.uuid4().hex
        target = self._path(f"databases/{database_id}/{version_id}.parquet")
        staging = target.with_suffix(".partial")
        schema = pa.schema([pa.field("value", pa.float64())])
        rows, invalid = 0, 0
        try:
            with pq.ParquetWriter(staging, schema, compression="zstd") as writer:
                for batch in self._batches(snapshot, canceled=canceled):
                    arrays = {name: batch.column(i).cast(pa.float64()).to_numpy(zero_copy_only=False)
                              for i, name in enumerate(batch.schema.names)}
                    result = formula.calculate(arrays)
                    mask = ~np.isfinite(result)
                    invalid += int(mask.sum())
                    writer.write_batch(pa.record_batch([pa.array(result, mask=mask)], schema=schema))
                    rows += len(result)
                    if progress:
                        progress(rows)
            _check_cancel(canceled)
            staging.replace(target)
            provenance = {"operation": "formula", "expression": expression,
                          "inputs": {c["name"]: c["version_id"] for c in snapshot}, "invalid_rows": invalid,
                          "unit": unit}
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT id FROM channels WHERE database_id=? AND name=?",
                                      (database_id, output_name)).fetchone()
                if existing:
                    channel_id = existing[0]
                    first = db.execute("SELECT provenance FROM versions WHERE channel_id=? AND number=1", (channel_id,)).fetchone()
                    if json.loads(first[0])["operation"] == "import":
                        raise ValueError("Original channels are immutable; choose a new output name.")
                    number = db.execute("SELECT MAX(number)+1 FROM versions WHERE channel_id=?", (channel_id,)).fetchone()[0]
                    db.execute("UPDATE channels SET unit=? WHERE id=?", (unit, channel_id))
                else:
                    channel_id, number = uuid.uuid4().hex, 1
                    db.execute("INSERT INTO channels VALUES(?,?,?,?)", (channel_id, database_id, output_name, unit))
                db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)", (version_id, channel_id, number,
                           target.relative_to(self.root).as_posix(), "value", "double", json.dumps(provenance), _now()))
                self._event(db, database_id, "derive", {**provenance, "output": output_name, "version": number})
            return {"name": output_name, "version": number, "rows": rows, "invalid_rows": invalid}
        except BaseException:
            staging.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def filter_channel(self, database_id, channel, output_name, options, canceled=None, progress=None):
        """Filter one channel into a new immutable channel, with full provenance."""
        if __package__:
            from .channel_filters import filtered_runs
        else:
            from channel_filters import filtered_runs
        import scipy
        options.validate()
        output_name = _name(output_name)
        if output_name in {c["name"] for c in self.channels(database_id)}:
            raise ValueError("Filter output must use a new channel name.")
        names = list(dict.fromkeys([channel, *[n for n in (options.axis, options.group, options.sensor) if n]]))
        snapshot = self._snapshot(database_id, names)
        pa, pq = _arrow()
        target = self._path(f"databases/{database_id}/{uuid.uuid4().hex}.parquet")
        staging = target.with_suffix(".partial")
        schema = pa.schema([("value", pa.float64())])
        stats = {"rows": 0, "output_null_rows": 0, "segments": 0, "short_segments": 0,
                 "spikes_replaced": 0, "input_null_rows": 0, "gap_splits": 0}
        try:
            with ExitStack() as stack:
                writer = stack.enter_context(pq.ParquetWriter(staging, schema, compression="zstd"))
                batches = self._batches(snapshot, canceled=canceled)
                stack.callback(batches.close)
                runs = filtered_runs(batches, channel, options, stats, canceled)
                stack.callback(runs.close)
                for result in runs:
                    for start in range(0, len(result), BATCH_SIZE):
                        _check_cancel(canceled)
                        values = result[start:start + BATCH_SIZE]
                        mask = ~np.isfinite(values)
                        writer.write_batch(pa.record_batch([pa.array(values, mask=mask)], schema=schema))
                        stats["rows"] += len(values)
                        stats["output_null_rows"] += int(mask.sum())
                        if progress:
                            progress(stats["rows"])
            _check_cancel(canceled)
            if stats["rows"] == stats["output_null_rows"]:
                raise ValueError("No filterable samples: all segments are missing or too short for these settings.")
            provenance = {"operation": "channel_filter", "parameters": options.to_dict(),
                          "inputs": {c["name"]: c["version_id"] for c in snapshot}, "statistics": stats,
                          "libraries": {"numpy": np.__version__, "scipy": scipy.__version__},
                          "ordering": "original rows, contiguous line/sensor runs; no sorting or resampling",
                          "edges": "complete centered windows; Butterworth odd padding, forward-backward SOS"}
            staging.replace(target)
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                expected = db.execute("SELECT rows FROM databases WHERE id=?", (database_id,)).fetchone()[0]
                if stats["rows"] != expected:
                    raise ValueError("Filter changed row count; output not published.")
                channel_id = uuid.uuid4().hex
                db.execute("INSERT INTO channels VALUES(?,?,?,?)", (channel_id, database_id, output_name, snapshot[0]["unit"]))
                db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)", (
                    uuid.uuid4().hex, channel_id, 1, target.relative_to(self.root).as_posix(),
                    "value", "double", json.dumps(provenance), _now()))
                self._event(db, database_id, "channel_filter", {**provenance, "output": output_name})
            return {"output": output_name, **stats}
        except BaseException:
            staging.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def level_lines(self, database_id, value_channel, line_channel, crossovers,
                    correction_name, corrected_name, outlier_sigma=4.5, canceled=None, progress=None):
        """Solve crossover constants and atomically publish correction/value channels.

        Crossovers are explicit (traverse, tie, residual) observations supplied by
        the crossover backend. Their hash, constants, QC and input version IDs
        are saved; original channels and active coordinates are untouched.
        """
        import hashlib
        if __package__:
            from .line_processing import robust_line_corrections, residual_statistics
        else:
            from line_processing import robust_line_corrections, residual_statistics
        rows = [(str(a), str(b), float(r)) for a, b, r in crossovers]
        if not rows or not all(np.isfinite(r) and a != b for a, b, r in rows):
            raise ValueError("Finite crossovers between distinct lines are required.")
        if not np.isfinite(outlier_sigma) or outlier_sigma <= 0:
            raise ValueError("Outlier sigma must be positive and finite.")
        names = [_name(correction_name), _name(corrected_name)]
        if len(set(names)) != 2 or set(names).intersection(c["name"] for c in self.channels(database_id)):
            raise ValueError("Two distinct new output channel names are required.")
        snapshot = self._snapshot(database_id, [value_channel, line_channel])
        _check_cancel(canceled)
        constants, accepted = robust_line_corrections(rows, outlier_sigma)
        statistics = residual_statistics(rows, constants, accepted)
        if not constants:
            raise ValueError("No constrained line corrections could be solved.")
        pa, pq = _arrow()
        target = self._path(f"databases/{database_id}/{uuid.uuid4().hex}.parquet")
        staging = target.with_suffix(".partial")
        schema = pa.schema([(name, pa.float64()) for name in names])
        count = 0
        try:
            with ExitStack() as stack:
                writer = stack.enter_context(pq.ParquetWriter(staging, schema, compression="zstd"))
                batches = self._batches(snapshot, canceled=canceled)
                stack.callback(batches.close)
                for batch in batches:
                    values = batch.column(0).cast(pa.float64())
                    line_values = batch.column(1).to_pylist()
                    if any(v is None or str(v) not in constants for v in line_values):
                        raise ValueError("A database line is missing from the constrained solution; no implicit zero correction.")
                    correction = np.array([constants[str(v)] for v in line_values])
                    raw = values.to_numpy(zero_copy_only=False)
                    nulls = values.is_null().to_numpy(zero_copy_only=False)
                    if np.any(~np.isfinite(raw) & ~nulls):
                        raise ValueError("Nonfinite source values; no corrected channels published.")
                    corrected = raw + correction
                    if np.any(~np.isfinite(corrected) & ~nulls):
                        raise ValueError("Corrected channel overflow.")
                    writer.write_batch(pa.record_batch([pa.array(correction), pa.array(corrected, mask=nulls)], schema=schema))
                    count += len(batch)
                    if progress:
                        progress(count)
            _check_cancel(canceled)
            provenance = {"operation": "line_leveling", "inputs": {c["name"]: c["version_id"] for c in snapshot},
                "outlier_sigma": outlier_sigma, "line_constants": constants, "statistics": statistics,
                "crossovers_count": len(rows), "crossovers_sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
                "crossovers_source": "explicit caller-supplied observations", "numpy": np.__version__,
                "model": "constant line corrections with zero-mean anchor", "rows": count}
            staging.replace(target)
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                for name in names:
                    channel_id = uuid.uuid4().hex
                    db.execute("INSERT INTO channels VALUES(?,?,?,?)", (channel_id, database_id, name, snapshot[0]["unit"]))
                    db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, channel_id, 1,
                        target.relative_to(self.root).as_posix(), name, "double",
                        json.dumps({**provenance, "output_role": "correction" if name == names[0] else "corrected_signal"}), _now()))
                self._event(db, database_id, "line_leveling", {**provenance, "outputs": names})
            return {"outputs": names, "statistics": statistics, "rows": count}
        except BaseException:
            staging.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def magnetic_grid_pipeline(self, database_id, template_path, x, y, line, correction,
                               options, sample_step_cells=4.0, sigma_cells=2.0,
                               input_precision="float64", canceled=None):
        """Database correction channels -> template -> versioned magnetic products.

        GDAL is loaded only on demand; no GUI is constructed or accessed.
        """
        if __package__:
            from .survey_grid_pipeline import run_magnetic_grid_pipeline
        else:
            from survey_grid_pipeline import run_magnetic_grid_pipeline
        return run_magnetic_grid_pipeline(self, database_id, template_path, x, y, line, correction,
            options, sample_step_cells, sigma_cells, input_precision, canceled)

    def rename_channel(self, database_id, old, new, unit=None):
        new = _name(new)
        with self._connection() as db:
            row = db.execute("SELECT id,unit FROM channels WHERE database_id=? AND name=?", (database_id, old)).fetchone()
            if row is None:
                raise ValueError("Unknown channel.")
            db.execute("UPDATE channels SET name=?,unit=? WHERE id=?", (new, row[1] if unit is None else unit, row[0]))
            self._event(db, database_id, "rename", {"old": old, "new": new, "unit": unit})

    def duplicate_channel(self, database_id, source_name, output_name):
        """Zero-copy alias of one immutable version; future versions are independent."""
        source = self._snapshot(database_id, [source_name])[0]
        output_name = _name(output_name)
        channel_id = uuid.uuid4().hex
        provenance = {"operation": "duplicate", "input_version": source["version_id"]}
        with self._connection() as db:
            db.execute("INSERT INTO channels VALUES(?,?,?,?)", (channel_id, database_id, output_name, source["unit"]))
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)", (
                uuid.uuid4().hex, channel_id, 1, source["path"], source["field"], source["data_type"],
                json.dumps(provenance), _now()))
            self._event(db, database_id, "duplicate", {**provenance, "output": output_name})

    def configure_geometry(self, database_id, x, y, crs):
        if x == y or not str(crs).strip():
            raise ValueError("Distinct X/Y channels and an explicit CRS are required.")
        channels = self._snapshot(database_id, [x, y])
        geometry = {"x_channel_id": channels[0]["id"], "y_channel_id": channels[1]["id"], "crs": str(crs)}
        with self._connection() as db:
            metadata = json.loads(db.execute("SELECT metadata FROM databases WHERE id=?", (database_id,)).fetchone()[0])
            metadata["geometry"] = geometry
            db.execute("UPDATE databases SET metadata=? WHERE id=?", (json.dumps(metadata), database_id))
            self._event(db, database_id, "geometry", geometry)

    def reproject_coordinates(self, database_id, x, y, source_crs, target_crs,
                              output_x, output_y, transform, unit="", details=None,
                              canceled=None, progress=None):
        """Publish a transformed XY pair and active geometry in one transaction.

        transform receives finite NumPy XY arrays and returns two arrays. Null
        pairs remain null; malformed/nonfinite coordinates abort the operation.
        The caller supplies and validates the CRS engine, not this storage layer.
        """
        pa, pq = _arrow()
        names = [_name(output_x), _name(output_y)]
        if names[0] == names[1] or not source_crs or not target_crs:
            raise ValueError("Distinct output names and explicit source/target CRS are required.")
        if set(names).intersection(c["name"] for c in self.channels(database_id)):
            raise ValueError("Coordinate outputs must be new channels.")
        snapshot = self._snapshot(database_id, [x, y])
        target = self._path(f"databases/{database_id}/{uuid.uuid4().hex}.parquet")
        staging = target.with_suffix(".partial")
        schema = pa.schema([(name, pa.float64()) for name in names])
        rows, missing = 0, 0
        try:
            with pq.ParquetWriter(staging, schema, compression="zstd") as writer:
                for batch in self._batches(snapshot, canceled=canceled):
                    arrays = [batch.column(i).cast(pa.float64()) for i in range(2)]
                    null = np.logical_or(*[a.is_null().to_numpy(zero_copy_only=False) for a in arrays])
                    coords = [a.to_numpy(zero_copy_only=False) for a in arrays]
                    if any(np.any(~np.isfinite(a) & ~null) for a in coords):
                        raise ValueError(f"Nonfinite coordinates in rows {rows + 1}–{rows + len(batch)}.")
                    valid = ~null
                    result = [np.full(len(batch), np.nan) for _ in range(2)]
                    if valid.any():
                        converted = transform(coords[0][valid], coords[1][valid])
                        if len(converted) != 2:
                            raise ValueError("Transform must return two coordinate arrays.")
                        for axis in range(2):
                            values = np.asarray(converted[axis], dtype=float)
                            if values.shape != (int(valid.sum()),) or not np.isfinite(values).all():
                                raise ValueError("Coordinate transformation failed; no outputs published.")
                            result[axis][valid] = values
                    writer.write_batch(pa.record_batch([pa.array(a, mask=null) for a in result], schema=schema))
                    rows += len(batch)
                    missing += int(null.sum())
                    if progress:
                        progress(rows)
            _check_cancel(canceled)
            staging.replace(target)
            provenance = {"operation": "reproject", "source_crs": source_crs, "target_crs": target_crs,
                          "inputs": {c["name"]: c["version_id"] for c in snapshot},
                          "null_pairs": missing, "engine": details or {}, "unit": unit}
            channel_ids = [uuid.uuid4().hex for _ in names]
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                for name, channel_id in zip(names, channel_ids):
                    db.execute("INSERT INTO channels VALUES(?,?,?,?)", (channel_id, database_id, name, unit))
                    db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)", (
                        uuid.uuid4().hex, channel_id, 1, target.relative_to(self.root).as_posix(),
                        name, "double", json.dumps(provenance), _now()))
                metadata = json.loads(db.execute("SELECT metadata FROM databases WHERE id=?", (database_id,)).fetchone()[0])
                metadata["geometry"] = {"x_channel_id": channel_ids[0], "y_channel_id": channel_ids[1], "crs": target_crs}
                db.execute("UPDATE databases SET metadata=? WHERE id=?", (json.dumps(metadata), database_id))
                self._event(db, database_id, "reproject", {**provenance, "outputs": names})
            return {"rows": rows, "null_pairs": missing, "outputs": names}
        except BaseException:
            staging.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def export_csv(self, database_id, names, destination, filters=None, canceled=None, progress=None):
        import pyarrow.csv as arrow_csv
        destination = Path(destination).resolve()
        if destination.exists():
            raise FileExistsError("Export never overwrites an existing file.")
        staging = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".partial")
        rows = 0
        created_destination = False
        try:
            with ExitStack() as stack:
                writer = None
                for batch in self.batches(database_id, names, filters=filters, canceled=canceled):
                    if writer is None:
                        sink = stack.enter_context(staging.open("wb"))
                        writer = stack.enter_context(arrow_csv.CSVWriter(sink, batch.schema))
                    writer.write_batch(batch)
                    rows += len(batch)
                    if progress:
                        progress(rows)
            if rows == 0:
                raise ValueError("No observations match the selection.")
            _check_cancel(canceled)
            # Exclusive creation protects existing user data, including races.
            with staging.open("rb") as source, destination.open("xb") as output:
                created_destination = True
                while chunk := source.read(1024 * 1024):
                    _check_cancel(canceled)
                    output.write(chunk)
            return rows
        except BaseException:
            if created_destination:
                destination.unlink(missing_ok=True)
            raise
        finally:
            staging.unlink(missing_ok=True)
