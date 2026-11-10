import numpy as np
import pytest

from terraworkbench_core.basic_processing import (
    GRIDFLT9_LEAST_SQUARES_SOURCE,
    smooth_least_squares_9x9,
    smooth_nine_point,
)


def reference_kernel():
    # Independent transcription of the published GRIDFLTN least-squares table.
    table = {
        (0, 0): 0.04441238,
        (1, 0): 0.04200738,
        (1, 1): 0.03960237,
        (2, 0): 0.03479237,
        (2, 1): 0.03238737,
        (2, 2): 0.02517236,
        (3, 0): 0.02276736,
        (3, 1): 0.02036235,
        (3, 2): 0.01314735,
        (3, 3): 0.00112233,
        (4, 0): 0.00593234,
        (4, 1): 0.00352734,
        (4, 2): -0.00368767,
        (4, 3): -0.01571268,
        (4, 4): -0.03254770,
    }
    return np.array(
        [
            [table[tuple(sorted((abs(r), abs(c)), reverse=True))] for c in range(-4, 5)]
            for r in range(-4, 5)
        ]
    )


def test_gridflt9_impulse_matches_official_coefficients_and_existing_default():
    data = np.zeros((25, 25))
    data[12, 12] = 1.0
    result = smooth_least_squares_9x9(data, passes=1)
    np.testing.assert_allclose(result[8:17, 8:17], reference_kernel(), atol=1e-16)
    outside = result.copy()
    outside[8:17, 8:17] = 0.0
    assert not outside.any()
    # Existing 3x3 behavior is deliberately independent of the optional filter.
    np.testing.assert_allclose(
        smooth_nine_point(data)[11:14, 11:14],
        np.outer([1.0, 2.0, 1.0], [1.0, 2.0, 1.0]) / 16.0,
    )
    assert GRIDFLT9_LEAST_SQUARES_SOURCE.endswith("examples/gridfltn/gridfltn.gxc")


def test_gridflt9_two_passes_matches_scalar_interior_reference():
    data = np.random.default_rng(104).normal(size=(23, 24))
    kernel = reference_kernel()
    first = data.copy()
    for r in range(4, 19):
        for c in range(4, 20):
            first[r, c] = np.sum(data[r - 4 : r + 5, c - 4 : c + 5] * kernel)
    expected = []
    for r in range(8, 15):
        for c in range(8, 16):
            expected.append(np.sum(first[r - 4 : r + 5, c - 4 : c + 5] * kernel))
    actual = smooth_least_squares_9x9(data)
    np.testing.assert_allclose(actual[8:15, 8:16].ravel(), expected, atol=1e-15)
    np.testing.assert_allclose(
        actual, smooth_least_squares_9x9(smooth_least_squares_9x9(data, 1), 1)
    )


@pytest.mark.parametrize("value", [0.0, -4.0, 9.0])
@pytest.mark.parametrize("shape", [(1, 1), (8, 11), (24, 25)])
def test_gridflt9_constant_gain_mask_shape_and_input_preserved(value, shape):
    data = np.full(shape, value)
    if shape[0] > 1:
        data[2:4, 3:5] = np.nan
        data[0, -1] = np.inf
    before = data.copy()
    result = smooth_least_squares_9x9(data)
    assert result.shape == shape
    np.testing.assert_array_equal(np.isnan(result), ~np.isfinite(data))
    np.testing.assert_array_equal(data, before)
    # Negative kernel weights are not renormalized at holes or boundaries.
    np.testing.assert_allclose(
        result[np.isfinite(result)], value * 1.0000001**2, rtol=1e-14, atol=1e-14
    )


def test_gridflt9_nearest_edges_are_explicit_approximation():
    data = np.zeros((25, 25))
    data[0, 0] = 1.0
    result = smooth_least_squares_9x9(data, passes=1)
    # A nearest extension only affects the first five rows/columns.
    assert not result[5:, :].any()
    assert not result[:, 5:].any()
    assert result[0, 0] == pytest.approx(reference_kernel()[4:, 4:].sum())


@pytest.mark.parametrize(
    "passes", [0, 101, 1.5, np.nan, np.inf, 2 + 0j, "2", None, [2]]
)
def test_gridflt9_rejects_invalid_passes(passes):
    with pytest.raises(ValueError, match="integer"):
        smooth_least_squares_9x9(np.ones((9, 9)), passes=passes)


@pytest.mark.parametrize(
    "data", [np.zeros(9), np.empty((0, 9)), np.full((9, 9), np.nan)]
)
def test_gridflt9_requires_nonempty_2d_finite_support(data):
    with pytest.raises(ValueError, match="two-dimensional"):
        smooth_least_squares_9x9(data)


def test_gridflt9_cancellation_before_and_between_passes_preserves_input():
    data = np.ones((25, 25))
    before = data.copy()
    with pytest.raises(InterruptedError, match="canceled"):
        smooth_least_squares_9x9(data, canceled=lambda: True)
    checks = iter([False, False, True])
    with pytest.raises(InterruptedError, match="canceled"):
        smooth_least_squares_9x9(data, canceled=lambda: next(checks))
    np.testing.assert_array_equal(data, before)
