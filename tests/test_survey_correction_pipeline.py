import json
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from survey_correction_pipeline import MagneticCorrectionOptions, correct_magnetic_arrays
from survey_store import SurveyStore


def test_known_base_heading_and_lag_terms():
    time = np.arange(8.)
    raw = 100 + 2 * time
    result, recipe = correct_magnetic_arrays(raw, time, [1]*8, [1]*8,
        MagneticCorrectionOptions(max_gap_seconds=2, lag_seconds=1, heading_cosine=3, heading_sine=4),
        base_time=time, base_value=10+time, base_reference=10, azimuth_degrees=np.zeros(8))
    np.testing.assert_allclose(result["corrected"][:-1], 105 + time[:-1])
    assert np.isnan(result["corrected"][-1])
    np.testing.assert_allclose(result["total_delta"][:-1], 5-time[:-1])
    assert recipe["enabled"] == {"base": True, "lag": True, "heading": True, "despike": False}


def test_lag_never_crosses_sensor_track_gap_or_missing_row():
    result, _ = correct_magnetic_arrays([1, 2, 100, 200, 7, 8, np.nan, 9, 10],
        [0, 1, 0, 1, 10, 11, 12, 13, 14], [1]*9, [1, 1, 2, 2, 2, 2, 2, 2, 2],
        MagneticCorrectionOptions(max_gap_seconds=2, lag_seconds=1))
    np.testing.assert_allclose(result["corrected"], [2, np.nan, 200, np.nan, 8, np.nan, np.nan, 10, np.nan], equal_nan=True)


def test_despike_keeps_terms_and_marks_incomplete_windows():
    raw = np.ones(21) * 50
    raw[10] = 1000
    result, recipe = correct_magnetic_arrays(raw, np.arange(21.), [1]*21, [1]*21,
        MagneticCorrectionOptions(max_gap_seconds=2, despike_window=7))
    np.testing.assert_allclose(result["corrected"][3:-3], 50)
    assert result["despike_delta"][10] == -950
    assert np.isnan(result["corrected"][:3]).all()
    assert recipe["statistics"]["spikes_replaced"] == 1


def test_base_does_not_extrapolate_and_requires_explicit_reference():
    options = MagneticCorrectionOptions(max_gap_seconds=2)
    with pytest.raises(ValueError, match="reference"):
        correct_magnetic_arrays([5]*4, np.arange(4.), [1]*4, [1]*4, options,
                                base_time=[1, 2], base_value=[10, 11])
    result, _ = correct_magnetic_arrays([5]*4, np.arange(4.), [1]*4, [1]*4, options,
        base_time=[1, 2], base_value=[10, 11], base_reference=10)
    np.testing.assert_allclose(result["corrected"], [np.nan, 5, 4, np.nan], equal_nan=True)
    with pytest.raises(ValueError, match="increase"):
        correct_magnetic_arrays([1, 2], [0, 0], [1, 1], [1, 1], options)


def test_store_publishes_terms_atomically_and_retains_source(tmp_path):
    source = tmp_path / "input.parquet"
    pq.write_table(pa.table({"mag": [100., 102, 104, 106], "ms": [0, 1000, 2000, 3000],
                            "track": [1]*4, "sensor": [1]*4}), source)
    store = SurveyStore(tmp_path / "store", create=True)
    database = store.import_file(source)
    original = source.read_bytes()
    options = MagneticCorrectionOptions(max_gap_seconds=2, lag_seconds=1)
    result = store.correct_magnetic(database, "mag", "ms", "track", "sensor", options, time_scale=.001)
    assert len(result["outputs"]) == 6
    actual = pa.Table.from_batches(list(store.batches(database, ["mag", "mag__corrected"]))).to_pydict()
    assert actual == {"mag": [100., 102, 104, 106], "mag__corrected": [102., 104, 106, None]}
    assert source.read_bytes() == original
    event = json.loads(store.history(database)[-1]["details"])
    assert event["enabled"]["base"] is False and len(event["inputs"]) == 4
    before = list(store.channels(database))
    with pytest.raises(ValueError, match="new channel"):
        store.correct_magnetic(database, "mag", "ms", "track", "sensor", options, time_scale=.001)
    assert store.channels(database) == before
    with pytest.raises(InterruptedError):
        store.correct_magnetic(database, "mag", "ms", "track", "sensor", options, prefix="cancel", canceled=lambda: True)
    assert store.channels(database) == before
