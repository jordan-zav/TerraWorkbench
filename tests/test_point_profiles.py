import numpy as np
import pytest
from terraworkbench_core.paired_flights import match_point_profiles


def test_reversed_lower_acquisition_order_matches_xy_without_inverting_profile():
    high = np.array([[0, 0, 10.4], [1, 0, 10.5], [2, 0, 10.6]], float)
    low = np.array([[2, 0.1, 10.2], [1, 0.1, 10.1], [0, 0.1, 10]], float)
    original = low.copy()
    r = match_point_profiles(high, low, 0.25, minimum=0.36, maximum=0.44)
    np.testing.assert_equal(r["paired_low_index"], [2, 1, 0])
    np.testing.assert_allclose(r["delta_height_m"], 0.4)
    np.testing.assert_allclose(r["distance_m"], [0, 1, 2])
    assert r["accepted"].all()
    np.testing.assert_equal(low, original)


def test_no_bridge_missing_elevation_outside_xy_and_reused_sample():
    high = np.array(
        [[0, 0, 1], [0.05, 0, 1.1], [3, 0, 1], [np.nan, 0, 1], [0, 0, np.nan]], float
    )
    low = np.array([[0, 0, 0.6], [3, 0, np.nan], [9, 0, 0.5]], float)
    r = match_point_profiles(high, low, 0.25, minimum=0.36, maximum=0.44)
    np.testing.assert_equal(r["paired"], [1, 1, 0, 0, 0])
    np.testing.assert_equal(r["accepted"], [1, 0, 0, 0, 0])
    assert np.isnan(r["delta_height_m"][2:]).all()
    assert r["metadata"]["reused_lower_samples"] == 1
    assert r["metadata"]["unpaired_low_points"] == 2


def test_empty_finite_candidate_population_and_zero_distance():
    r = match_point_profiles([[0, 0, 1]], [[0, 0, np.nan]], 0)
    assert not r["paired"].any()
    assert r["paired_low_index"][0] == -1
    r = match_point_profiles([[0, 0, 1]], [[0, 0, 0.6]], 0)
    assert r["paired"].all()


@pytest.mark.parametrize(
    "args",
    [
        ([], [[0, 0, 0]], 0.2),
        ([[0, 0]], [[0, 0, 0]], 0.2),
        ([[0, 0, 1]], [[0, 0, 0]], -1),
    ],
)
def test_validation(args):
    with pytest.raises(ValueError):
        match_point_profiles(*args)


def test_tolerance_comparison_uses_fixed_pairs_without_changing_selected_mask():
    from terraworkbench_core.paired_flights import profile_tolerance_summary

    result = {
        "paired": np.array([1, 1, 1, 0], dtype=bool),
        "delta_height_m": np.array([0.4, 0.33, 0.29, 0.4]),
        "accepted": np.array([1, 0, 0, 0], dtype=bool),
    }
    original = result["accepted"].copy()
    rows = profile_tolerance_summary(result, 0.4)
    assert [r["accepted_points"] for r in rows] == [1, 2, 3]
    assert [r["xy_paired_points"] for r in rows] == [3, 3, 3]
    np.testing.assert_equal(original, result["accepted"])
    assert (
        profile_tolerance_summary(
            {"paired": np.array([False]), "delta_height_m": np.array([np.nan])}, 0.4
        )[0]["accepted_percent_of_xy_pairs"]
        is None
    )
    with pytest.raises(ValueError):
        profile_tolerance_summary(result, 0)
    with pytest.raises(ValueError):
        profile_tolerance_summary(result, 0.4, percentages=(100,))


def test_horizontal_comparison_includes_new_candidates_without_mutating_pairing():
    from terraworkbench_core.paired_flights import horizontal_pair_summary

    high = np.array([[0, 0, 1], [1, 0, 1], [2, 0, 1], [3, 0, 1], [4, 0, 1]], float)
    low = np.array(
        [[0, 0.2, 0.6], [1, 0.29, 0.6], [2, 0.32, 0.5], [3, 0.4, 0.6], [4, 0, np.nan]],
        float,
    )
    r = match_point_profiles(high, low, 0.25, minimum=0.36, maximum=0.44)
    before = r["paired"].copy()
    delta = r["delta_height_m"].copy()
    rows = horizontal_pair_summary(r)
    assert [x["xy_paired_points"] for x in rows] == [1, 2, 3]
    assert [x["unpaired_high_points"] for x in rows] == [4, 3, 2]
    assert [x["accepted_with_vertical_limits"] for x in rows] == [1, 2, 2]
    np.testing.assert_allclose(
        [x["horizontal_limit_m"] for x in rows], [0.25, 0.3, 0.325]
    )
    np.testing.assert_equal(r["paired"], before)
    np.testing.assert_equal(r["delta_height_m"], delta)
    with pytest.raises(ValueError):
        horizontal_pair_summary(r, increases=(-10,))


def test_point_matrix_distinguishes_horizontal_and_vertical_gates():
    from terraworkbench_core.paired_flights import point_pair_tolerance_matrix

    r = match_point_profiles(
        [[0, 0, 1], [1, 0, 1], [2, 0, 1]],
        [[0, 0.2, 0.6], [1, 0.29, 0.67], [2, 0.32, 0.71]],
        0.25,
        minimum=0.36,
        maximum=0.44,
    )
    initial = r["paired"].copy()
    matrix = point_pair_tolerance_matrix(r, 0.4)
    counts = (
        np.array([row["accepted_with_vertical_limits"] for row in matrix["rows"]])
        .reshape(3, 3)
        .T
    )
    np.testing.assert_equal(counts, [[1, 1, 1], [1, 2, 2], [1, 2, 3]])
    np.testing.assert_equal(r["paired"], initial)
    assert matrix["active_pairing_changed"] is False
