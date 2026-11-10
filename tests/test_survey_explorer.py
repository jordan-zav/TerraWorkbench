"""Read-only explorer contracts, including Arrow batch boundaries."""

import numpy as np
import pyarrow as pa
import pytest

from terraworkbench_core.survey_explorer import (
    read_survey_page,
    read_survey_profile,
    survey_group_values,
)


class Store:
    def __init__(self, data, batch_size=3):
        self.table = pa.table(data)
        self.batch_size = batch_size
        self.closed = False

    def batches(self, database_id, names, filters=None, canceled=None):
        table = self.table
        for name, values in (filters or {}).items():
            import pyarrow.compute as pc

            table = table.filter(
                pc.is_in(table[name], value_set=pa.array(values, type=table[name].type))
            )
        try:
            yield from table.select(names).to_batches(max_chunksize=self.batch_size)
        finally:
            self.closed = True


@pytest.mark.parametrize(
    "offset, expected, more",
    [
        (0, [0, 1, 2, 3], True),
        (4, [4, 5, 6, 7], True),
        (8, [8, 9], False),
        (10, [], False),
    ],
)
def test_pages(offset, expected, more):
    store = Store({"v": range(10)})
    result = read_survey_page(store, "db", ["v"], offset=offset, limit=4)
    assert result["data"]["v"] == expected
    assert result["has_next"] is more
    assert store.closed


def test_filtered_page():
    store = Store({"v": range(10), "line": ["a", "b"] * 5})
    result = read_survey_page(
        store, "db", ["v"], offset=2, limit=2, filters={"line": ["a"]}
    )
    assert result["data"] == {"v": [4, 6]}
    assert result["has_next"]


def test_segments_across_batches_and_gaps():
    store = Store(
        {
            "v": [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0, 9.0],
            "line": ["a"] * 6 + ["b", "b", "a"],
        }
    )
    result = read_survey_profile(store, "db", "v", group="line")
    assert [s["x"].tolist() for s in result["segments"]] == [
        [1, 2, 3],
        [5, 6],
        [7, 8],
        [9],
    ]
    assert result["valid_rows"] == 8
    assert result["excluded_rows"] == 1
    assert result["mean"] == pytest.approx(np.mean([1, 2, 3, 5, 6, 7, 8, 9]))
    assert store.closed


def test_axis_reset_and_sensor_selection():
    store = Store(
        {
            "v": ["1", "2", "3", "4", "5"],
            "x": [0, 1, 0, 1, 2],
            "sensor": [1, 1, 1, 1, 2],
        }
    )
    result = read_survey_profile(
        store, "db", "v", axis="x", sensor="sensor", filters={"sensor": [1]}
    )
    assert [s["x"].tolist() for s in result["segments"]] == [[0, 1], [0, 1]]
    assert result["rows"] == 4


def test_envelope_retains_spikes_and_full_statistics():
    values = np.zeros(10000)
    values[337] = 900
    values[8003] = -800
    result = read_survey_profile(Store({"v": values}, 127), "db", "v", max_points=100)
    assert result["reduced"] and result["display_points"] <= 100
    assert 900 in result["segments"][0]["y"]
    assert -800 in result["segments"][0]["y"]
    assert result["mean"] == pytest.approx(values.mean())
    assert result["std"] == pytest.approx(values.std())


@pytest.mark.parametrize("options", [{"max_samples": 4}, {"max_segments": 1}])
def test_budgets_close_reader(options):
    store = Store({"v": range(6), "line": ["a"] * 3 + ["b"] * 3})
    with pytest.raises(ValueError):
        read_survey_profile(store, "db", "v", group="line", **options)
    assert store.closed


def test_numeric_validation_and_empty_profile():
    with pytest.raises(ValueError, match="numeric"):
        read_survey_profile(Store({"v": ["bad"]}), "db", "v")
    result = read_survey_profile(
        Store({"v": pa.array([None, None], type=pa.float64())}), "db", "v"
    )
    assert result["segments"] == [] and result["mean"] is None


@pytest.mark.parametrize(
    "reader, args", [(read_survey_page, (["v"],)), (read_survey_profile, ("v",))]
)
def test_cancel(reader, args):
    with pytest.raises(InterruptedError):
        reader(Store({"v": range(10)}), "db", *args, cancel=lambda: True)


def test_mid_read_cancel_closes_generator():
    store = Store({"v": range(30)})
    cancelled = [False]
    with pytest.raises(InterruptedError):
        read_survey_profile(
            store,
            "db",
            "v",
            cancel=lambda: cancelled[0],
            progress=lambda _: cancelled.__setitem__(0, True),
        )
    assert store.closed


def test_null_group_excluded_and_disconnected():
    result = read_survey_profile(
        Store({"v": [1.0, 2.0, 3.0], "line": ["a", None, "a"]}), "db", "v", group="line"
    )
    assert result["excluded_rows"] == 1
    assert [s["x"].tolist() for s in result["segments"]] == [[1], [3]]


def test_group_values_bounded_unique_and_leading_zero_identifiers():
    store = Store(
        {"line": ["001", "002", "001", None, "003"], "sensor": [1, 2, 2, 1, 1]}
    )
    result = survey_group_values(store, "db", ["line", "sensor"], max_values=2)
    assert result["rows"] == 5
    assert result["values"] == {"line": ["001", "002"], "sensor": ["1", "2"]}
    assert result["truncated"] == {"line": True, "sensor": False}
    assert store.closed


def test_physical_distance_resets_at_group_and_invalid_coordinates():
    store = Store(
        {
            "v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "x": [0.0, 3.0, 6.0, None, 9.0, 12.0],
            "y": [0.0, 4.0, 8.0, 12.0, 12.0, 16.0],
            "line": ["a", "a", "b", "b", "b", "b"],
        },
        batch_size=2,
    )
    result = read_survey_profile(
        store,
        "db",
        "v",
        group="line",
        distance_columns=["x", "y"],
        source_crs="EPSG:32618",
    )
    assert [s["x"].tolist() for s in result["segments"]] == [[0, 5], [0], [0, 5]]
    assert result["valid_rows"] == 5


def test_distance_rejects_missing_crs_or_conflicting_axis():
    store = Store({"v": [1.0], "x": [0.0], "y": [0.0]})
    with pytest.raises(ValueError, match="explicit CRS"):
        read_survey_profile(store, "db", "v", distance_columns=["x", "y"])
    with pytest.raises(ValueError, match="alternate axis"):
        read_survey_profile(
            store,
            "db",
            "v",
            axis="x",
            distance_columns=["x", "y"],
            source_crs="EPSG:32618",
        )
