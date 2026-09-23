import numpy as np
import pytest

from basic_processing import circular_median


def test_disk_not_square_and_original_mask():
    values = np.array([[100., 1, 100], [2, 99, 3], [100, 4, np.nan]])
    result = circular_median(values, 1)
    assert result[1, 1] == 3  # [1, 2, 99, 3, 4], excluding diagonals
    assert result[0, 0] == 2  # no artificial edge padding
    assert np.isnan(result[2, 2])
    np.testing.assert_array_equal(np.isnan(result), np.isnan(values))


@pytest.mark.parametrize("radius", [1, 2, 3, 10])
def test_matches_independent_disk_reference(radius):
    rng = np.random.default_rng(42)
    values = rng.normal(size=(9, 11))
    values[2:4, 4:6] = np.nan
    expected = np.full_like(values, np.nan)
    for y in range(9):
        for x in range(11):
            if np.isfinite(values[y, x]):
                neighbors = [values[j, i] for j in range(9) for i in range(11)
                             if (i-x)**2 + (j-y)**2 <= radius**2 and np.isfinite(values[j, i])]
                expected[y, x] = np.median(neighbors)
    np.testing.assert_allclose(circular_median(values, radius), expected, equal_nan=True)


@pytest.mark.parametrize("radius", [0, 1.5, 51, np.nan])
def test_radius_rejected(radius):
    with pytest.raises(ValueError):
        circular_median(np.ones((3, 3)), radius)


def test_cancellation():
    with pytest.raises(InterruptedError):
        circular_median(np.ones((3, 3)), canceled=lambda: True)
