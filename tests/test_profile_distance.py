import numpy as np
import pytest
from terraworkbench_core.profile_distance import along_profile_distance


def test_metric_path_and_repeated_positions():
    np.testing.assert_equal(
        along_profile_distance([0, 3, 3, 6], [0, 4, 4, 8], "EPSG:32617"), [0, 5, 5, 10]
    )


def test_missing_coordinates_are_breaks_without_spanning_gap():
    np.testing.assert_equal(
        along_profile_distance(
            [0, 3, np.nan, 100, 103], [0, 4, np.nan, 100, 104], "EPSG:32617"
        ),
        [0, 5, np.nan, 5, 10],
    )


def test_geographic_distance_uses_ellipsoid_metres():
    d = along_profile_distance([0, 0.001, 0.002], [0, 0, 0], "EPSG:4326")
    np.testing.assert_allclose(d, [0, 111.31949079, 222.63898159], atol=1e-7)


def test_projected_feet_are_converted_to_metres():
    d = along_profile_distance([1000000, 1000010], [200000, 200000], "EPSG:2263")
    assert d[1] == pytest.approx(3.048006096012192)


def test_invalid_crs_coordinates_are_rejected():
    with pytest.raises(ValueError, match="longitude"):
        along_profile_distance([285000, 285001], [4676000, 4676001], "EPSG:4326")
    with pytest.raises(ValueError, match="finite"):
        along_profile_distance([np.nan], [0], "EPSG:32617")
