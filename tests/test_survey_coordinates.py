import json

import numpy as np
import pytest

from survey_store import SurveyStore


def fixture_store(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("x,y\n1,2\n,3\n4,5\n", encoding="utf-8")
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(source)
    store.configure_geometry(database, "x", "y", "source")
    return store, database


def test_coordinate_pair_atomic_and_nulls(tmp_path):
    store, database = fixture_store(tmp_path)
    result = store.reproject_coordinates(database, "x", "y", "source", "target", "xx", "yy",
                                         lambda x, y: (x + 10, y + 20), "m")
    assert result["null_pairs"] == 1
    assert next(store.batches(database, ["xx", "yy"])).to_pydict() == {
        "xx": [11.0, None, 14.0], "yy": [22.0, None, 25.0]}
    assert next(store.batches(database, ["x"])).to_pydict()["x"] == ["1", None, "4"]
    metadata = json.loads(store.databases()[0]["metadata"])
    assert metadata["geometry"]["crs"] == "target"
    store.rename_channel(database, "xx", "renamed")
    assert metadata["geometry"]["x_channel_id"] == next(c["id"] for c in store.channels(database) if c["name"] == "renamed")


@pytest.mark.parametrize("failure", ["nonfinite", "exception", "cancel", "collision"])
def test_coordinate_failure_leaves_no_outputs(tmp_path, failure):
    store, database = fixture_store(tmp_path)
    before_files = set(store.root.rglob("*.parquet"))
    before_metadata = store.databases()[0]["metadata"]

    def convert(x, y):
        if failure == "exception":
            raise ValueError("missing grid")
        return (x * np.nan, y) if failure == "nonfinite" else (x, y)

    with pytest.raises((ValueError, InterruptedError)):
        store.reproject_coordinates(database, "x", "y", "source", "target",
            "x" if failure == "collision" else "xx", "yy", convert, canceled=lambda: failure == "cancel")
    assert len(store.channels(database)) == 2
    assert store.databases()[0]["metadata"] == before_metadata
    assert set(store.root.rglob("*.parquet")) == before_files
    assert not list(store.root.rglob("*.partial"))
