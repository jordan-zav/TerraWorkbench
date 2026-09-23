import numpy as np
import pytest

from basic_processing import ThinPlateGridder, smooth_nine_point, automatic_gain_control


@pytest.mark.parametrize("neighbors", [0, 8])
def test_tps_plane_and_coordinate_invariance(neighbors):
    rng = np.random.default_rng(19)
    xy = rng.random((30, 2))
    z = 12 + 3 * xy[:, 0] - 2 * xy[:, 1]
    q = rng.random((20, 2))
    expected = 12 + 3 * q[:, 0] - 2 * q[:, 1]
    for scale, offset in [(1, 0), (100, 500000)]:
        model = ThinPlateGridder(xy * scale + offset, z, neighbors=neighbors)
        np.testing.assert_allclose(model(q * scale + offset), expected, atol=1e-9)


def test_tps_exact_anomaly_and_duplicates():
    xy = np.array([[0, 0], [0, 1], [1, 0], [1, 1], [.5, .5]], float)
    z = np.array([0, 0, 0, 0, 5.])
    model = ThinPlateGridder(np.vstack([xy, xy[-1]]), np.r_[z, 7.])
    assert model.duplicate_count == 1
    np.testing.assert_allclose(model(xy), [0, 0, 0, 0, 6], atol=1e-10)


def test_tps_rejects_degenerate_and_large_global_inputs():
    with pytest.raises(ValueError, match="collinear"):
        ThinPlateGridder([[0, 0], [1, 1], [2, 2]], [0, 1, 2])
    with pytest.raises(ValueError, match="distinct"):
        ThinPlateGridder([[0, 0], [0, 0], [0, 0]], [0, 1, 2])
    with pytest.raises(ValueError, match="finite"):
        ThinPlateGridder([[0, 0], [1, 0], [0, 1]], [0, 1, np.nan])
    xy = np.random.default_rng(1).random((2001, 2))
    with pytest.raises(ValueError, match="2000"):
        ThinPlateGridder(xy, np.zeros(2001))


def test_smoothing_kernel_and_passes():
    data = np.zeros((9, 9))
    data[4, 4] = 16
    actual = smooth_nine_point(data)
    np.testing.assert_allclose(actual[3:6, 3:6], np.outer([1, 2, 1], [1, 2, 1]))
    np.testing.assert_allclose(smooth_nine_point(data, 2), smooth_nine_point(actual))
    with pytest.raises(InterruptedError):
        smooth_nine_point(data, canceled=lambda: True)


@pytest.mark.parametrize("fn", [smooth_nine_point, automatic_gain_control])
@pytest.mark.parametrize("value", [0., -4., 9.])
def test_filters_preserve_constant_and_mask(fn, value):
    data = np.full((8, 8), value)
    data[2:4, 2:4] = np.nan
    result = fn(data)
    np.testing.assert_array_equal(np.isnan(result), np.isnan(data))
    np.testing.assert_allclose(result[np.isfinite(result)], value)


def test_agc_reference_rms_and_cap():
    data = np.arange(1., 26.).reshape(5, 5)
    result = automatic_gain_control(data, window=3, max_gain=2.)
    target = np.sqrt(np.mean(data**2))
    for row in range(5):
        for col in range(5):
            sample = data[max(0, row-1):row+2, max(0, col-1):col+2]
            gain = min(target / max(np.sqrt(np.mean(sample**2)), .05 * target), 2.)
            assert result[row, col] == pytest.approx(data[row, col] * gain)


@pytest.mark.parametrize("kwargs", [{"window": 4}, {"floor_fraction": 0}, {"max_gain": .5}])
def test_agc_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        automatic_gain_control(np.ones((3, 3)), **kwargs)
