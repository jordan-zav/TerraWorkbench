import numpy as np
import pytest

from terraworkbench_core import basic_processing


@pytest.mark.parametrize("passes", [1, 2, 0, None])
def test_removed_smoother_fails_explicitly_without_modifying_input(passes):
    data = np.ones((9, 9))
    before = data.copy()
    def canceled():
        pytest.fail("Removed smoother must fail before processing")
    with pytest.raises(NotImplementedError) as error:
        basic_processing.smooth_least_squares_9x9(data, passes, canceled)
    message = str(error.value)
    for text in ("EN:", "ES:", "PT:", "1.1.0", "smooth_nine_point", "circular_median"):
        assert text in message
    np.testing.assert_array_equal(data, before)
    assert not hasattr(basic_processing, "GRIDFLT9_LEAST_SQUARES_COEFFICIENTS")


def test_binomial_alternative_remains_available():
    data = np.zeros((9, 9))
    data[4, 4] = 1
    np.testing.assert_allclose(
        basic_processing.smooth_nine_point(data)[3:6, 3:6],
        np.outer([1., 2., 1.], [1., 2., 1.]) / 16.,
    )
