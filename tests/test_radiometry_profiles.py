import numpy as np
import pytest
from terraworkbench_core.radiometry import live_time_correction, accumulated_profile_ratios


def test_measured_live_time():
    np.testing.assert_allclose(live_time_correction([100.] * 4, [1000., 800., 0., 1001.]),
                               [100., 125., np.nan, np.nan], equal_nan=True)
    assert live_time_correction(10., 250., 500.) == 20.
    with pytest.raises(ValueError):
        live_time_correction(-1., 1000.)


def run(k, u, th, profile, **kwargs):
    options = dict(thresholds=(3., 6., 9.), minimum_potassium=.1, max_radius=2)
    options.update(kwargs)
    return accumulated_profile_ratios(k, u, th, profile, **options)


def test_accumulation_and_line_boundaries():
    result, recipe = run([1.] * 6, [2.] * 6, [3.] * 6, ['a'] * 3 + ['b'] * 3)
    np.testing.assert_allclose(result['u_th'], 2 / 3)
    np.testing.assert_array_equal(result['sample_count'], [3] * 6)
    assert recipe['valid_outputs'] == 6
    result, _ = run([1., 1.], [2., 2.], [3., 3.], ['a', 'b'])
    assert np.isnan(result['u_k']).all()


def test_no_bridging_gaps_and_cancellation():
    for middle in (np.nan, 0., -1.):
        result, _ = run([1., middle, 1.], [2.] * 3, [3.] * 3, ['a'] * 3)
        assert np.isnan(result['u_th']).all()
    with pytest.raises(InterruptedError):
        run([1.], [2.], [3.], ['a'], canceled=lambda: True)
    with pytest.raises(ValueError):
        run([1.], [2.], [3.], ['a'], thresholds=(0., 1., 2.))


def test_independent_window_sums():
    data = np.random.default_rng(3).uniform(.2, 2., (3, 25))
    actual, _ = run(*data, ['a'] * 25)
    for i in range(25):
        expected = np.nan
        for radius in range(3):
            sums = data[:, max(0, i-radius):min(25, i+radius+1)].sum(axis=1)
            if np.all(sums >= [3., 6., 9.]):
                expected = sums[1] / sums[2]
                break
        np.testing.assert_allclose(actual['u_th'][i], expected, equal_nan=True)
