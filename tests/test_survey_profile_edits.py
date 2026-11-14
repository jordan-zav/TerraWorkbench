"""Tests for exact editing, undo and catalogue provenance."""

import json

import numpy as np
import pytest

from terraworkbench_core.survey_profile_edits import ProfileEdits, publish_profile_edits
from terraworkbench_core.survey_store import SurveyStore


@pytest.mark.parametrize("method", ["linear", "akima"])
def test_interpolation_and_history(method):
    source = np.arange(10, dtype=float)
    edits = ProfileEdits(source)
    edits.dummy(3, 5)
    edits.dummy(0, 0)
    edits.interpolate(source, 0, 9, method, axis_name="fiducial")
    np.testing.assert_allclose(edits.values[1:], source[1:])
    assert np.isnan(edits.values[0])
    assert edits.operations[-1]["axis"] == "fiducial"
    edits.undo()
    assert np.isnan(edits.values[3:6]).all()
    edits.redo()
    np.testing.assert_allclose(edits.values[1:], source[1:])
    edits.undo()
    edits.dummy(7, 7)
    edits.redo()
    assert np.isnan(edits.values[3:6]).all()
    assert source[7] == 7


def test_spikes_and_differences():
    values = np.ones(13)
    values[6] = 50
    edits = ProfileEdits(values)
    for relative in (True, False):
        np.testing.assert_array_equal(edits.spike_candidates(3, relative=relative), [6])
    assert edits.values[6] == 50
    assert edits.fourth_difference()[6] == 294
    edits.apply_spikes([6], 3)
    assert edits.statistics(5, 7) == (2, 1, 1, 1, 1, 0)


def test_publication_is_new_and_row_aligned(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("line,signal\nL1,10\nL2,20\nL1,30\n", encoding="utf-8")
    store = SurveyStore(tmp_path / "survey", create=True)
    database = store.import_file(path)
    inputs = {row["name"]: row["version_id"] for row in store.channels(database)}
    model = ProfileEdits([10, 30])
    model.dummy(1, 1)
    _, changed = model.changes()
    records = [(np.array([2]), changed, {"line": "L1", "operations": model.operations})]
    publish_profile_edits(store, database, "signal", "clean", inputs, "nT", records)
    batch = next(store.batches(database, ["signal", "clean"]))
    assert batch.column("signal").to_pylist() == ["10", "20", "30"]
    assert batch.column("clean").to_pylist() == [10, 20, None]
    row = next(row for row in store.channels(database) if row["name"] == "clean")
    recipe = json.loads(row["provenance"])
    assert recipe["operation"] == "profile_edit"
    assert recipe["lines"] == [records[0][2]]
    assert inputs["signal"] in json.dumps(recipe["inputs"])
    with pytest.raises(ValueError):
        publish_profile_edits(
            store, database, "signal", "signal", inputs, "nT", records
        )
