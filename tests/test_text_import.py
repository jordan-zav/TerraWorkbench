import json

import pyarrow as pa
import pytest

from survey_store import SurveyStore
from text_import import (ColumnSpec, TextImportOptions, arrow_batches, inspect_text,
                         parsed_rows, preview, suggest_columns)


@pytest.mark.parametrize("separator", [",", ";", "\t", "|"])
def test_detect_metadata_header_roles_and_separator(tmp_path, separator):
    path = tmp_path / "survey.txt"
    path.write_text("Survey export\n# instrument A\n" + separator.join(["Line", "Sensor ID", "X [m]", "Y [m]", "Mag [nT]"]) + "\n" +
                    "\n".join(separator.join(row) for row in [
                        ["001", "02", "500000", "4000000", "3.5"],
                        ["002", "02", "500001", "4000001", "4.5"],
                        ["003", "02", "500002", "4000002", "5.5"]]), encoding="utf-8")
    options, warnings, _ = inspect_text(path)
    assert options.delimiter == separator and options.mode == "delimited"
    assert (options.header_row, options.data_row) == (3, 4)
    assert [c.role for c in options.columns] == ["line", "sensor", "x", "y", ""]
    assert [c.data_type for c in options.columns] == ["text", "text", "integer", "integer", "float"]
    assert options.columns[-1].unit == "nT" and warnings
    assert preview(path, options)[0][1] == ["001", "02", 500000, 4000000, 3.5]


def test_decimal_comma_encoding_nulls_and_store_metadata(tmp_path):
    path = tmp_path / "survey.csv"
    path.write_bytes("Línea;X;Y;Mag [nT]\n001;1,5;2,5;-99,9\n002;2,5;3,5;4,5\n".encode("cp1252"))
    options, _, _ = inspect_text(path)
    assert options.encoding == "cp1252" and options.decimal == ","
    options.null_values = ("", "-99,9")
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(path, text_options=options)
    data = pa.Table.from_batches(list(store.batches(database, ["Línea", "X", "Mag [nT]"]))).to_pydict()
    assert data == {"Línea": ["001", "002"], "X": [1.5, 2.5], "Mag [nT]": [None, 4.5]}
    assert next(c for c in store.channels(database) if c["name"] == "Mag [nT]")["unit"] == "nT"
    assert json.loads(store.databases()[0]["metadata"])["text_import"]["encoding"] == "cp1252"


def test_no_header_whitespace_scientific_numbers(tmp_path):
    path = tmp_path / "survey.xyz"
    path.write_text("# field export\n500000 4000000 1.2e-3\n500001\t4000001   -2.3E+2\n", encoding="utf-8")
    options, _, _ = inspect_text(path)
    assert options.header_row == 0 and options.data_row == 2
    assert options.mode == "whitespace"
    assert [c.name for c in options.columns] == ["channel_1", "channel_2", "channel_3"]
    assert preview(path, options)[1][1] == [500001, 4000001, -230.]


def test_utf16_bom_and_quotes(tmp_path):
    path = tmp_path / "quoted.csv"
    path.write_text('line,x,label\n001,1,"a,b"\n002,2,"first\n# not a comment"\n', encoding="utf-16", newline="\n")
    options = TextImportOptions(encoding="utf-16", columns=[ColumnSpec("line"), ColumnSpec("x", "integer"), ColumnSpec("label")])
    values = preview(path, options)
    assert values[0] == (2, ["001", 1, "a,b"])
    assert values[1] == (3, ["002", 2, "first\n# not a comment"])
    detected, _, _ = inspect_text(path)
    assert detected.encoding == "utf-16"


def test_fixed_width_and_no_silent_truncation(tmp_path):
    path = tmp_path / "fixed.dat"
    path.write_text("001   10.5   -2.5\n002   11.5   -3.5\n", encoding="utf-8")
    options = TextImportOptions(mode="fixed", header_row=0, data_row=1, widths=(3, 7, 7),
                                columns=[ColumnSpec("line"), ColumnSpec("x", "float"), ColumnSpec("y", "float")])
    assert preview(path, options)[0][1] == ["001", 10.5, -2.5]
    options.widths = (3, 7, 2)
    with pytest.raises(ValueError, match="truncate"):
        preview(path, options)


def test_skipped_units_row_comments_and_blank_lines(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("X,Y,Mag\nm,m,nT\n\n# note\n1,2,3\n// another note\n2,3,4\n", encoding="utf-8")
    options = TextImportOptions(header_row=1, data_row=5)
    options.columns = suggest_columns(path, options)
    assert [n for n, _ in preview(path, options)] == [5, 7]


def test_errors_beyond_preview_roll_back_import(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text("x,y\n" + "1,2\n" * 45 + "3,broken\n", encoding="utf-8")
    options = TextImportOptions(columns=[ColumnSpec("x", "integer"), ColumnSpec("y", "float")])
    assert len(preview(path, options)) == 30
    store = SurveyStore(tmp_path / "project", create=True)
    with pytest.raises(ValueError, match="Line 47, channel 'y'"):
        store.import_file(path, text_options=options)
    assert store.databases() == []
    assert not list((store.root / "databases").iterdir())


def test_header_replacements_and_type_override(tmp_path):
    path = tmp_path / "repeat.csv"
    path.write_text("value,value,\n001,2,3\n002,3,4\n", encoding="utf-8")
    options = TextImportOptions()
    options.columns = suggest_columns(path, options)
    assert [c.name for c in options.columns] == ["value", "channel_2", "channel_3"]
    assert options.columns[0].data_type == "text"
    options.columns[0] = ColumnSpec("number", "integer")
    assert preview(path, options)[0][1][0] == 1


def test_batch_limits_and_cancellation(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x,y\n" + "1,2\n" * 11)
    options = TextImportOptions(columns=[ColumnSpec("x", "integer"), ColumnSpec("y", "integer")])
    schema, batches = arrow_batches(path, options, batch_size=4)
    assert [len(b) for b in batches] == [4, 4, 3] and schema.names == ["x", "y"]
    with pytest.raises(InterruptedError):
        list(parsed_rows(path, options, canceled=lambda: True))


def test_modified_source_after_review_is_rejected(tmp_path):
    path = tmp_path / "modified.csv"
    path.write_text("x,y\n1,2\n")
    options, _, _ = inspect_text(path)
    stat = path.stat()
    options.source_size, options.source_mtime_ns = stat.st_size, stat.st_mtime_ns
    path.write_text("x,y\n1,2\n3,4\n")
    store = SurveyStore(tmp_path / "project", create=True)
    with pytest.raises(ValueError, match="changed since"):
        store.import_file(path, text_options=options)
    assert store.databases() == []


def test_whitespace_quotes_and_literal_backslashes(tmp_path):
    path = tmp_path / "paths.txt"
    path.write_text('1 2 "C:\\field files\\raw"\n')
    options = TextImportOptions(mode="whitespace", header_row=0, data_row=1,
        columns=[ColumnSpec("x", "integer"), ColumnSpec("y", "integer"), ColumnSpec("path")])
    assert preview(path, options)[0][1][2] == "C:\\field files\\raw"


def test_roles_survive_channel_rename(tmp_path):
    path = tmp_path / "coordinates.csv"
    path.write_text("X,Y,Line\n1,2,001\n3,4,002\n")
    options, _, _ = inspect_text(path)
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(path, text_options=options)
    role_id = json.loads(store.databases()[0]["metadata"])["channel_roles"]["x"]
    store.rename_channel(database, "X", "Easting")
    assert next(c for c in store.channels(database) if c["id"] == role_id)["name"] == "Easting"


def test_ambiguous_roles_and_large_identifiers(tmp_path):
    path = tmp_path / "id.csv"
    path.write_text("X,Easting,id\n1,2,123456789012345678901234\n2,3,123456789012345678901235\n")
    options = TextImportOptions()
    options.columns = suggest_columns(path, options)
    assert [c.role for c in options.columns] == ["", "", ""]
    assert options.columns[-1].data_type == "text"


@pytest.mark.parametrize("options", [TextImportOptions(header_row=2, data_row=2),
    TextImportOptions(mode="fixed", widths=(0,)), TextImportOptions(columns=[ColumnSpec("same"), ColumnSpec("same")])])
def test_invalid_configuration(options):
    with pytest.raises(ValueError):
        options.validate()
