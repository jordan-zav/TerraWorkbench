import numpy as np
import pytest
from terraworkbench_core.paired_flights import (
    separation_histogram,
    PairOptions,
    calculate_pair,
)


def test_distribution_includes_rejected_and_nonpositive_before_gates():
    values = np.array([0.36, 0.4, 0.44, 0.8, -0.1, 0, np.nan, 7])
    original = values.copy()
    h = separation_histogram(
        values, [1, 1, 1, 1, 1, 1, 1, 0], minimum=0.36, maximum=0.44, bins=8
    )
    assert (
        h["supported_cells"] == 6
        and h["inside_limits_cells"] == 3
        and h["nonpositive_cells"] == 2
    )
    assert (
        sum(h["counts"]) == 6
        and sum(h["inside_limits_counts"]) == 3
        and sum(h["outside_limits_counts"]) == 3
    )
    assert h["median_m"] == pytest.approx(0.38)
    assert h["positive_median_m"] == pytest.approx(0.42)
    np.testing.assert_equal(values, original)


def test_empty_constant_and_no_limits():
    h = separation_histogram([np.nan], [True])
    assert h["median_m"] is None and sum(h["counts"]) == 0
    h = separation_histogram([0.4] * 6, [True] * 6)
    assert h["median_m"] == 0.4 and sum(h["counts"]) == 6
    assert h["inside_limits_cells"] == 6 and sum(h["outside_limits_counts"]) == 0


@pytest.mark.parametrize(
    "kw",
    [
        {"bins": True},
        {"bins": 0},
        {"bins": 201},
        {"minimum": 0.3},
        {"minimum": 0.5, "maximum": 0.4},
    ],
)
def test_invalid_settings(kw):
    with pytest.raises(ValueError):
        separation_histogram([0.4], [True], **kw)


def test_pair_histogram_is_not_confidence_filtered():
    xy = np.array([[0.0, 0.0], [1.0, 0.0]])
    result = calculate_pair(
        np.ones((1, 2)),
        np.zeros((1, 2)),
        xy,
        np.column_stack((xy, [0.4, 0.8])),
        np.column_stack((xy, [0.0, 0.0])),
        PairOptions("recorded_z", 0.36, 0.44, 0.25, confidence_threshold=0.8),
        confidence=[[0.1, 0.1]],
    )
    assert not result.mask.any()
    h = result.metadata["separation_histogram"]
    assert (
        h["supported_cells"] == 2
        and h["inside_limits_cells"] == 1
        and h["median_m"] == pytest.approx(0.6)
    )
