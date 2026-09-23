import json
import sqlite3

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from survey_store import Formula, SurveyStore


@pytest.fixture
def survey(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("line,x,y,mag,base\n001,10,20,100,5\n002,11,21,110,6\n001,12,22,,7\n", encoding="utf-8")
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(source)
    return store, database, source


def values(store, database, names, **kwargs):
    return pa.Table.from_batches(list(store.batches(database, names, **kwargs))).to_pydict()


def test_import_selection_filter_and_reopen(survey):
    store, database, source = survey
    assert store.databases()[0]["rows"] == 3
    assert values(store, database, ["line"], batch_size=1) == {"line": ["001", "002", "001"]}
    assert values(store, database, ["mag"], filters={"line": ["002"]}) == {"mag": ["110"]}
    reopened = SurveyStore(store.root)
    assert len(reopened.channels(database)) == 5
    assert source.read_text().startswith("line,x,y,mag,base")


def test_versioned_formula_and_nulls(survey):
    store, database, _ = survey
    result = store.derive(database, "corrected", 'c("mag") - c("base")', unit="nT")
    assert result["invalid_rows"] == 1
    assert values(store, database, ["corrected"]) == {"corrected": [95., 104., None]}
    first = next(c for c in store.channels(database) if c["name"] == "corrected")
    result = store.derive(database, "corrected", 'c("mag") * 2', unit="nT")
    assert result["version"] == 2 and (store.root / first["path"]).exists()
    assert pq.read_table(store.root / first["path"])["value"].to_pylist() == [95., 104., None]
    assert len(store.history(database)) == 3
    with pytest.raises(ValueError, match="immutable"):
        store.derive(database, "mag", 'c("mag") + 1')


def test_rename_duplicate_and_export(survey, tmp_path):
    store, database, _ = survey
    store.duplicate_channel(database, "line", "line_copy")
    store.rename_channel(database, "mag", "field", "nT")
    assert values(store, database, ["line_copy", "field"])["line_copy"] == ["001", "002", "001"]
    output = tmp_path / "selected.csv"
    assert store.export_csv(database, ["x", "field"], output, filters={"line": ["001"]}) == 2
    assert '"x","field"' in output.read_text()
    with pytest.raises(FileExistsError):
        store.export_csv(database, ["x"], output)


def test_parquet_block_alignment(survey, tmp_path):
    store, _, _ = survey
    source = tmp_path / "large.parquet"
    pq.write_table(pa.table({"x": np.arange(150003), "line": np.arange(150003) % 3}), source, row_group_size=173)
    database = store.import_file(source)
    store.derive(database, "twice", 'c("x") * 2')
    batches = list(store.batches(database, ["x", "twice"], batch_size=10001))
    assert max(map(len, batches)) <= 10001
    assert sum(map(len, batches)) == 150003
    for batch in batches:
        np.testing.assert_array_equal(batch.column(1), np.asarray(batch.column(0))*2)


def test_cancel_and_conflicts_leave_original_untouched(survey, tmp_path):
    store, database, source = survey
    before = list((store.root / "databases").rglob("*.parquet"))
    with pytest.raises(InterruptedError):
        store.derive(database, "canceled", 'c("mag") + 1', canceled=lambda: True)
    with pytest.raises(InterruptedError):
        store.import_file(source, "cancel", canceled=lambda: True)
    with pytest.raises(sqlite3.IntegrityError):
        store.import_file(source)
    assert list((store.root / "databases").rglob("*.parquet")) == before
    assert not list(store.root.rglob("*.partial"))
    with pytest.raises(ValueError):
        SurveyStore(tmp_path, create=True)


@pytest.mark.parametrize("expression", ["__import__('os')", "c('x').sum()", "[x for x in c('x')]", "c('x') ** 100", "1+2"])
def test_formula_is_not_python_execution(expression):
    with pytest.raises(ValueError):
        Formula(expression)


def test_invalid_math_becomes_null(survey):
    store, database, _ = survey
    result = store.derive(database, "invalid", 'sqrt(c("mag") * 0 - 1)')
    assert result["invalid_rows"] == 3
    assert values(store, database, ["invalid"]) == {"invalid": [None, None, None]}
    provenance = json.loads(next(c for c in store.channels(database) if c["name"] == "invalid")["provenance"])
    assert provenance["inputs"]["mag"]
