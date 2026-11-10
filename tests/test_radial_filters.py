import numpy as np
import pytest

from terraworkbench_core.radial_filters import tabulated_radial_filter


def test_tabulated_radial_gains_mean_interpolation_and_upper_tail():
    x, y = np.meshgrid(np.arange(19.0), np.arange(17.0))
    k = 2 * np.pi / 19
    data = 7 + 3 * np.cos(k * x) + 2 * np.cos(2 * k * x)
    before = data.copy()
    result = tabulated_radial_filter(
        data, (1.0, 1.0), [0, k, 1.5 * k], [1.0, 0.5, 0.0], max_abs_gain=1
    )
    np.testing.assert_allclose(result["filtered"], 7 + 1.5 * np.cos(k * x), atol=1e-12)
    np.testing.assert_array_equal(data, before)
    assert result["recipe"]["above_last"] == "constant last gain"
    half = tabulated_radial_filter(data, (1.0, 1.0), [0, 2 * k], [0, 1], max_abs_gain=1)
    np.testing.assert_allclose(
        half["filtered"], 1.5 * np.cos(k * x) + 2 * np.cos(2 * k * x), atol=1e-12
    )


@pytest.mark.parametrize(
    "k,gain,maximum",
    [
        ([1, 2], [1, 0], 1),
        ([0, 0], [1, 0], 1),
        ([0, 1], [1, 2], 1),
        ([0, 1], [1, np.nan], 1),
        ([0, 1], [1], 1),
        ([0, 1], [1, 0], 0),
    ],
)
def test_bad_tables_and_gain_budgets(k, gain, maximum):
    with pytest.raises(ValueError):
        tabulated_radial_filter(np.ones((5, 5)), (1, 1), k, gain, max_abs_gain=maximum)


def test_cancellation_and_no_implicit_fill():
    with pytest.raises(RuntimeError, match="canceled"):
        tabulated_radial_filter(
            np.ones((5, 5)),
            (1, 1),
            [0, 1],
            [1, 0],
            max_abs_gain=1,
            canceled=lambda: True,
        )
    data = np.ones((5, 5))
    data[0, 0] = np.nan
    with pytest.raises(ValueError):
        tabulated_radial_filter(data, (1, 1), [0, 1], [1, 0], max_abs_gain=1)
