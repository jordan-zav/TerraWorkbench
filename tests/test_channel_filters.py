import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from channel_filters import ChannelFilterOptions, filter_segment, filtered_runs
from survey_store import SurveyStore


def test_centered_mean_and_median():
    y = np.array([1, 2, 99, 4, 5], dtype=float)
    mean, stats = filter_segment(np.arange(5), y, ChannelFilterOptions(window=3))
    np.testing.assert_allclose(mean, [np.nan, 34, 35, 36, np.nan], equal_nan=True)
    median, _ = filter_segment(np.arange(5), y, ChannelFilterOptions(method="median", window=3))
    np.testing.assert_allclose(median, [np.nan, 2, 4, 5, np.nan], equal_nan=True)
    assert stats["short_segments"] == 0


def test_three_million_sample_limit():
    options = ChannelFilterOptions(method="detrend")
    assert options.max_segment_rows == 3_000_000
    options.validate()
    with pytest.raises(ValueError, match="3,000,000"):
        ChannelFilterOptions(max_segment_rows=3_000_001).validate()
    axis = np.arange(3_000_000, dtype=float)
    result, stats = filter_segment(axis, np.ones(len(axis)), options)
    assert len(result) == 3_000_000 and stats["short_segments"] == 0
    np.testing.assert_allclose(result, 0, atol=1e-12)
    with pytest.raises(ValueError, match="safety limit"):
        filter_segment(np.arange(3_000_001, dtype=float), np.ones(3_000_001), options)


def test_hampel_replaces_spike_and_reports():
    y = np.zeros(15)
    y[7] = 50
    result, stats = filter_segment(np.arange(15), y, ChannelFilterOptions(method="despike", window=5))
    assert stats["spikes_replaced"] == 1
    np.testing.assert_allclose(result[2:-2], 0)
    assert np.isnan(result[:2]).all() and np.isnan(result[-2:]).all()


def test_detrend_actual_irregular_axis():
    axis = np.array([0, 1, 3, 7, 12], dtype=float) + 1e9
    result, _ = filter_segment(axis, (axis - axis[0]) * 3 + 100, ChannelFilterOptions(method="detrend"))
    np.testing.assert_allclose(result, 0, atol=1e-12)


@pytest.mark.parametrize("method,cutoff,upper,expected", [
    ("lowpass", 0.05, 0.2, "slow"), ("highpass", 0.05, 0.2, "fast"),
    ("bandpass", 0.1, 0.3, "fast"),
])
def test_butterworth_frequency_separation(method, cutoff, upper, expected):
    x = np.arange(2000, dtype=float)
    slow, fast = np.sin(2 * np.pi * 0.01 * x), np.sin(2 * np.pi * 0.2 * x)
    result, _ = filter_segment(x, slow + fast, ChannelFilterOptions(method=method, cutoff=cutoff, upper_cutoff=upper))
    reference = slow if expected == "slow" else fast
    assert np.sqrt(np.mean((result[200:-200] - reference[200:-200]) ** 2)) < 0.01


@pytest.mark.parametrize("axis,cutoff,message", [
    ([0, 1, 3, 4], 0.1, "regular"), ([0, 1, 1, 2], 0.1, "strictly"),
    ([3, 2, 1, 0], 0.1, "strictly"), ([0, 1, 2, 3], 0.5, "Nyquist"),
])
def test_invalid_axis_and_cutoff(axis, cutoff, message):
    with pytest.raises(ValueError, match=message):
        filter_segment(axis, np.ones(4), ChannelFilterOptions(method="lowpass", cutoff=cutoff))


def test_short_segments_and_cancel():
    for method in ("mean", "median", "despike", "lowpass", "highpass", "bandpass", "detrend"):
        result, stats = filter_segment([0], [2], ChannelFilterOptions(method=method))
        assert np.isnan(result).all() and stats["short_segments"] == 1
    with pytest.raises(InterruptedError):
        filter_segment(np.arange(10), np.ones(10), ChannelFilterOptions(), lambda: True)


def test_runs_cross_batches_but_never_groups_gaps_or_nulls():
    table = pa.table({"s": [1., 2, 3, 100, 100, 100, None, 7, 8, 9, 10, 11, 12],
                      "t": [0., 1, 2, 0, 1, 2, 3, 4, 5, 6, 20, 21, 22],
                      "line": ["a"] * 3 + ["b"] * 10})
    options = ChannelFilterOptions(domain="time", axis="t", group="line", max_gap=2, window=3)
    stats = {}
    result = np.concatenate(list(filtered_runs(table.to_batches(max_chunksize=2), "s", options, stats)))
    np.testing.assert_allclose(result, [np.nan, 2, np.nan, np.nan, 100, np.nan, np.nan,
                                       np.nan, 8, np.nan, np.nan, 11, np.nan], equal_nan=True)
    assert stats["segments"] == 4 and stats["gap_splits"] == 1 and stats["input_null_rows"] == 1


def test_sensor_changes_and_missing_group_do_not_join():
    table = pa.table({"s": [1.] * 3 + [20.] * 3 + [99.] + [2.] * 3,
                      "line": ["a"] * 6 + [None] + ["a"] * 3,
                      "sensor": ["a"] * 3 + ["b"] * 7})
    stats = {}
    values = np.concatenate(list(filtered_runs(table.to_batches(max_chunksize=2), "s",
        ChannelFilterOptions(group="line", sensor="sensor", window=3), stats)))
    np.testing.assert_allclose(values, [np.nan, 1, np.nan, np.nan, 20, np.nan, np.nan, np.nan, 2, np.nan], equal_nan=True)


def test_safety_limit_and_malformed_values():
    for data, options, pattern in [
        ({"s": [1.] * 5}, ChannelFilterOptions(max_segment_rows=3), "exceeds"),
        ({"s": ["1", "oops", "3"]}, ChannelFilterOptions(), "Row 2"),
        ({"s": [1., np.inf, 3.]}, ChannelFilterOptions(), "infinite"),
    ]:
        with pytest.raises(ValueError, match=pattern):
            list(filtered_runs(pa.table(data).to_batches(), "s", options, {}))


def make_store(tmp_path):
    source = tmp_path / "input.parquet"
    pq.write_table(pa.table({"signal": np.arange(50, dtype=float), "base": np.ones(50),
                             "line": ["L1"] * 25 + ["L2"] * 25}), source)
    store = SurveyStore(tmp_path / "workspace", create=True)
    return store, store.import_file(source)


def test_filter_store_provenance_and_branch_lineage(tmp_path):
    store, database = make_store(tmp_path)
    store.derive(database, "corrected", 'c("signal") - c("base")', "nT")
    original_version = next(c for c in store.channels(database) if c["name"] == "corrected")["version_id"]
    result = store.filter_channel(database, "corrected", "corrected__mean_w3", ChannelFilterOptions(window=3, group="line"))
    assert result["rows"] == 50 and result["output_null_rows"] == 4
    store.derive(database, "corrected", 'c("signal") - 2*c("base")', "nT")
    store.rename_channel(database, "signal", "mag_raw")
    store.duplicate_channel(database, "corrected__mean_w3", "alias")
    graph = store.channel_pipeline(database, "alias")
    assert original_version in graph["nodes"]
    assert graph["nodes"][original_version]["number"] == 1
    assert {n["provenance"]["operation"] for n in graph["nodes"].values()} == {"import", "formula", "channel_filter", "duplicate"}
    assert any(n["name"] == "mag_raw" for n in graph["nodes"].values())
    assert len(graph["edges"]) == 5  # alias + filter signal/line + formula signal/base
    node = next(c for c in store.channels(database) if c["name"] == "corrected__mean_w3")
    assert node["unit"] == "nT"
    provenance = json.loads(node["provenance"])
    assert provenance["parameters"]["window"] == 3
    assert "scipy" in provenance["libraries"]


@pytest.mark.parametrize("case", ["cancel", "collision", "all_null", "failure_after_write"])
def test_store_rollback(tmp_path, case):
    store, database = make_store(tmp_path)
    before = set(store.root.rglob("*.parquet"))
    options = ChannelFilterOptions(window=3, group="line")
    if case == "all_null":
        options.window = 101
    calls = []
    def cancel():
        return case == "cancel" or (case == "failure_after_write" and bool(calls))
    with pytest.raises((ValueError, InterruptedError)):
        store.filter_channel(database, "signal", "signal" if case == "collision" else "output", options,
                             canceled=cancel, progress=calls.append)
    assert len(store.channels(database)) == 3
    assert set(store.root.rglob("*.parquet")) == before
    assert not list(store.root.rglob("*.partial"))


@pytest.mark.parametrize("change", [{"window": 4}, {"domain": "time"}, {"max_gap": 0},
                                    {"cutoff": 0}, {"method": "bandpass", "upper_cutoff": 0.01},
                                    {"order": 11}, {"spacing_tolerance": 0.1}])
def test_options_validation(change):
    with pytest.raises(ValueError):
        ChannelFilterOptions(**change).validate()
