"""Bounded text inspection and explicit, reproducible survey parsing.

Detection is heuristic. Physical line numbers are one-based, header 0 means
no header. The same parser serves preview and the full streaming import.
"""

import codecs
import csv
from dataclasses import asdict, dataclass, field, replace
import math
from pathlib import Path
import re
import shlex
import unicodedata

MAX_LINE = 4 * 1024 * 1024
SAMPLE_BYTES = 256 * 1024


@dataclass
class ColumnSpec:
    name: str
    data_type: str = "text"
    role: str = ""
    unit: str = ""


@dataclass
class TextImportOptions:
    encoding: str = "utf-8-sig"
    mode: str = "delimited"
    delimiter: str = ","
    header_row: int = 1
    data_row: int = 2
    widths: tuple = ()
    decimal: str = "."
    comments: tuple = ("#", "//")
    null_values: tuple = ("",)
    trim: bool = True
    columns: list = field(default_factory=list)
    source_size: int = -1
    source_mtime_ns: int = -1

    def to_dict(self):
        return asdict(self)

    def validate(self):
        codecs.lookup(self.encoding)
        if self.mode not in ("delimited", "whitespace", "fixed"):
            raise ValueError("Unknown text layout.")
        if self.mode == "delimited" and (len(self.delimiter) != 1 or self.delimiter in '\r\n"'):
            raise ValueError("Choose a single delimiter, other than quote/newline.")
        if not isinstance(self.header_row, int) or not isinstance(self.data_row, int) or not 0 <= self.header_row < self.data_row:
            raise ValueError("Header must precede the first data line; use header 0 for no header.")
        if self.decimal not in (".", ","):
            raise ValueError("Decimal separator must be dot or comma.")
        if self.mode == "fixed" and (not self.widths or any(type(w) is not int or w < 1 for w in self.widths)):
            raise ValueError("Fixed-width input requires positive column widths.")
        names = [c.name for c in self.columns]
        if any(not n.strip() or len(n) > 200 or "\x00" in n for n in names) or len(set(names)) != len(names):
            raise ValueError("Channel names must be non-empty, unique and at most 200 characters.")
        roles = [c.role for c in self.columns if c.role]
        if len(set(roles)) != len(roles):
            raise ValueError("Assign each semantic role to at most one channel.")
        for column in self.columns:
            if column.data_type not in ("text", "integer", "float"):
                raise ValueError("Supported types: text, integer, float.")
            if column.role not in ("", "x", "y", "time", "line", "sensor"):
                raise ValueError("Unknown channel role.")


def _cancel(canceled):
    if canceled and canceled():
        raise InterruptedError("Text import canceled.")


class _PhysicalLines:
    def __init__(self, handle, start=0, canceled=None):
        self.handle, self.number = handle, start
        self.first = ""
        self.canceled = canceled

    def __iter__(self):
        return self

    def __next__(self):
        _cancel(self.canceled)
        value = self.handle.readline(MAX_LINE + 1)
        if not value:
            raise StopIteration
        self.number += 1
        if len(value) > MAX_LINE:
            raise ValueError(f"Line {self.number} exceeds the 4 MiB character limit.")
        if not self.first:
            self.first = value
        return value


def _tokens(line, options):
    if options.mode == "delimited":
        return next(csv.reader([line], delimiter=options.delimiter, strict=True))
    if options.mode == "whitespace":
        lexer = shlex.shlex(line, posix=True)
        lexer.whitespace_split, lexer.commenters, lexer.escape = True, "", ""
        return list(lexer)
    end, result = 0, []
    text = line.rstrip("\r\n")
    for width in options.widths:
        result.append(text[end:end + width])
        end += width
    if text[end:].strip():
        raise ValueError("Nonblank text beyond configured fixed widths; refusing to truncate.")
    return result


def records(path, options, start=None, canceled=None):
    """Yield (physical first line, fields). Quoted CSV newlines are supported."""
    options.validate()
    start = options.data_row if start is None else start
    with Path(path).open(encoding=options.encoding, errors="strict", newline="") as handle:
        lines = _PhysicalLines(handle, canceled=canceled)
        for _ in range(start - 1):
            try:
                next(lines)
            except StopIteration:
                return
        # Feed each first line plus continuation lines into the CSV parser.
        # Comments are skipped before parsing, not inside a quoted record.
        while True:
            lines.first = ""
            try:
                line = next(lines)
            except StopIteration:
                return
            number = lines.number
            if not line.strip() or any(line.lstrip().startswith(p) for p in options.comments if p):
                continue
            try:
                if options.mode == "delimited":
                    from itertools import chain
                    row = next(csv.reader(chain([line], lines), delimiter=options.delimiter, strict=True))
                else:
                    row = _tokens(line, options)
            except (csv.Error, ValueError) as error:
                raise ValueError(f"Line {number}: {error}") from error
            if options.trim:
                row = [value.strip() for value in row]
            yield number, row


def _header_names(path, options):
    if options.header_row:
        iterator = records(path, options, start=options.header_row)
        try:
            result = next(iterator, None)
            if result is None or result[0] != options.header_row:
                raise ValueError("Selected header line is blank, commented or absent.")
            return [n.strip() for n in result[1]]
        finally:
            iterator.close()
    iterator = records(path, options)
    try:
        first = next(iterator, None)
        if first is None:
            raise ValueError("No data at the selected first line.")
        return [f"channel_{i + 1}" for i in range(len(first[1]))]
    finally:
        iterator.close()


def _number(value, decimal):
    # Thousands separators are deliberately not inferred or removed.
    if decimal == ",":
        if "." in value:
            raise ValueError("Dot found with decimal comma; thousands separators are unsupported.")
        value = value.replace(",", ".")
    elif "," in value:
        raise ValueError("Comma found with decimal dot.")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
        raise ValueError("Expected a decimal or scientific-notation number without thousands separators.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite number; declare its text as a null marker or keep text type.")
    return result


def convert(value, column, options):
    if value in options.null_values:
        return None
    if column.data_type == "text":
        return value
    if column.data_type == "integer":
        if not re.fullmatch(r"[+-]?\d+", value):
            raise ValueError("Expected an integer (no decimal or grouping separator).")
        result = int(value)
        if not -(2**63) <= result < 2**63:
            raise ValueError("Integer exceeds int64; use text to preserve it exactly.")
        return result
    return _number(value, options.decimal)


def parsed_rows(path, options, canceled=None):
    options.validate()
    if not options.columns:
        raise ValueError("Configure channel names and types before importing.")
    for number, row in records(path, options, canceled=canceled):
        if len(row) != len(options.columns):
            raise ValueError(f"Line {number}: expected {len(options.columns)} fields, got {len(row)}.")
        result = []
        for value, column in zip(row, options.columns):
            try:
                result.append(convert(value, column, options))
            except (ValueError, OverflowError) as error:
                raise ValueError(f"Line {number}, channel '{column.name}': {error}") from error
        yield number, result


def preview(path, options, limit=30):
    from itertools import islice
    iterator = parsed_rows(path, options)
    try:
        return list(islice(iterator, limit))
    finally:
        iterator.close()


def arrow_batches(path, options, batch_size=65536, canceled=None):
    import pyarrow as pa
    types = {"text": pa.string(), "integer": pa.int64(), "float": pa.float64()}
    options.validate()
    schema = pa.schema([pa.field(c.name, types[c.data_type]) for c in options.columns])
    if not 1 <= batch_size <= 65536 or not options.columns:
        raise ValueError("Configure channels and a batch size from 1 to 65536.")

    def stream():
        columns = [[] for _ in options.columns]
        estimated_bytes = 0
        for _, row in parsed_rows(path, options, canceled):
            for values, value in zip(columns, row):
                values.append(value)
                estimated_bytes += 64 + (4 * len(value) if isinstance(value, str) else 8)
            if len(columns[0]) == batch_size or estimated_bytes >= 8 * 1024 * 1024:
                yield pa.RecordBatch.from_arrays([pa.array(v, type=f.type) for v, f in zip(columns, schema)], schema=schema)
                columns = [[] for _ in options.columns]
                estimated_bytes = 0
        if columns[0]:
            yield pa.RecordBatch.from_arrays([pa.array(v, type=f.type) for v, f in zip(columns, schema)], schema=schema)
    return schema, stream()


def _role(name):
    bare = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    normalized = "".join(c for c in unicodedata.normalize("NFKD", bare) if not unicodedata.combining(c))
    key = re.sub(r"[^a-z0-9]", "", normalized.casefold())
    aliases = {
        "x": {"x", "e", "east", "easting", "este", "longitude", "lon", "longitud", "utmxe"},
        "y": {"y", "n", "north", "northing", "norte", "latitude", "lat", "latitud"},
        "time": {"time", "timestamp", "timestampms", "datetime", "date", "fecha", "hora", "tempo", "utc"},
        "line": {"line", "lineid", "linenumber", "track", "trackid", "profile", "profileid", "linha", "linea", "transect"},
        "sensor": {"sensor", "sensorid", "sensornumber", "device", "deviceid"},
    }
    for role, names in aliases.items():
        if key in names or (role in ("x", "y") and key.startswith(role + "utm")):
            return role
    return ""


def suggest_columns(path, options):
    """Infer from up to 100 records. IDs and leading-zero values stay text."""
    names = _header_names(path, options)
    if not names or any(not n for n in names) or len(set(names)) != len(names):
        # Still allow user-supplied replacement names in the wizard.
        seen = set()
        for i, name in enumerate(names):
            if not name or name in seen:
                names[i] = f"channel_{i + 1}"
            while names[i] in seen:
                names[i] += "_"
            seen.add(names[i])
    samples = [[] for _ in names]
    iterator = records(path, options)
    try:
        from itertools import islice
        for number, row in islice(iterator, 100):
            if len(row) != len(names):
                raise ValueError(f"Line {number}: {len(row)} fields do not match {len(names)} channel names.")
            for sample, value in zip(samples, row):
                if value not in options.null_values:
                    sample.append(value)
    finally:
        iterator.close()
    roles = [_role(name) for name in names]
    result = []
    for name, values, role in zip(names, samples, roles):
        kind = "text"
        if values and role not in ("line", "sensor", "time") and not any(re.fullmatch(r"[+-]?0\d+", v) for v in values):
            try:
                numeric = [_number(v, options.decimal) for v in values]
                kind = "integer" if all(re.fullmatch(r"[+-]?\d+", v) and -(2**63) <= int(v) < 2**63 for v in values) else "float"
                # Do not convert huge integer identifiers to approximate floats.
                if any(re.fullmatch(r"[+-]?\d{16,}", v) for v in values) and kind == "float":
                    kind = "text"
                del numeric
            except ValueError:
                pass
        unit = re.search(r"[\[(]([^\])]+)[\])]\s*$", name)
        result.append(ColumnSpec(name, kind, role if roles.count(role) == 1 else "", unit.group(1).strip() if unit else ""))
    return result


def inspect_text(path):
    """Return suggestions, warnings and numbered sample lines, never import."""
    with Path(path).open("rb") as handle:
        raw = handle.read(SAMPLE_BYTES)
    warnings = ["Detection uses a limited sample. Review the physical line numbers, names and types before importing."]
    if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        encoding = "utf-32"
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    else:
        encoding = "utf-8-sig"
        try:
            codecs.getincrementaldecoder(encoding)(errors="strict").decode(raw, final=False)
        except UnicodeDecodeError:
            encoding = "cp1252"
            warnings.append("Encoding is ambiguous: Windows-1252 suggested; verify accented characters or choose Latin-1.")
    decoded = codecs.getincrementaldecoder(encoding)(errors="strict").decode(raw, final=False)
    if "\x00" in decoded:
        raise ValueError("NUL bytes detected. Choose UTF-16/UTF-32 explicitly or verify this is a text file.")
    lines = decoded.splitlines()
    if len(raw) == SAMPLE_BYTES and lines and not decoded.endswith(("\n", "\r")):
        lines = lines[:-1]
    lines = lines[:500]
    candidates = []
    for mode, delimiter in [("delimited", d) for d in (",", ";", "\t", "|")] + [("whitespace", " ")]:
        options = TextImportOptions(encoding=encoding, mode=mode, delimiter=delimiter)
        parsed = []
        for i, line in enumerate(lines):
            if not line.strip() or any(line.lstrip().startswith(p) for p in options.comments):
                continue
            try:
                row = [v.strip() for v in _tokens(line, options)]
            except (ValueError, csv.Error):
                continue
            if len(row) >= 2:
                parsed.append((i + 1, row))
        for index, (number, row) in enumerate(parsed[:100]):
            def ratio(values):
                count = 0
                for value in values:
                    try:
                        _number(value, "," if "," in value else ".")
                        count += 1
                    except ValueError:
                        pass
                return count / max(1, len(values))
            if ratio(row) < .4:
                continue
            run = []
            for _, following in parsed[index:index + 30]:
                if len(following) != len(row) or ratio(following) < .2:
                    break
                run.append(following)
            score = len(run) * 10 + min(len(row), 20) + ratio(row) - number * .01
            options.data_row, options.header_row = number, 0
            possible = [(n, r) for n, r in parsed[max(0, index - 5):index]
                        if len(r) == len(row) and ratio(r) < .4 and len(set(r)) == len(r)]
            if possible:
                options.header_row = max(possible, key=lambda item: (sum(bool(_role(v)) for v in item[1]), item[0]))[0]
            comma_numbers = sum(bool(re.fullmatch(r"[+-]?\d+,\d+(?:[eE][+-]?\d+)?", v)) for r in run for v in r)
            options.decimal = "," if comma_numbers else "."
            candidates.append((score, replace(options)))
    if candidates:
        options = max(candidates, key=lambda item: item[0])[1]
    else:
        options = TextImportOptions(encoding=encoding)
        try:
            dialect = csv.Sniffer().sniff("\n".join(lines[:30]), delimiters=",;\t|")
            options.delimiter = dialect.delimiter
        except csv.Error:
            pass
        warnings.append("No reliable numeric data block found; select header/data rows manually.")
    try:
        options.columns = suggest_columns(path, options)
    except (ValueError, UnicodeError, csv.Error) as error:
        warnings.append(str(error))
    return options, warnings, lines
