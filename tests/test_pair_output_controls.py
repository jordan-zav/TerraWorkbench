import numpy as np
import pytest
from terraworkbench_core.paired_flights import PairOptions, calculate_pair


def pair(mode="both", threshold=None, confidence=None):
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
    hp = np.column_stack((xy, [0.4, 0.8, 0.0, -0.4]))
    lp = np.column_stack((xy, np.zeros(4)))
    return calculate_pair(
        np.array([[8.0, 8.0, 8.0, 8.0]]),
        np.zeros((1, 4)),
        xy,
        hp,
        lp,
        PairOptions(
            "recorded_z",
            0.36,
            0.44,
            0.25,
            output_mode=mode,
            confidence_threshold=threshold,
        ),
        confidence=confidence,
    )


def test_unmasked_preserves_rejected_height_but_not_invalid_separation():
    r = pair("unmasked")
    np.testing.assert_allclose(
        r.gradient, [[20.0, 10.0, np.nan, np.nan]], equal_nan=True
    )
    assert r.mask.tolist() == [[True, False, False, False]]
    np.testing.assert_allclose(
        r.gradient_masked, [[20.0, np.nan, np.nan, np.nan]], equal_nan=True
    )


def test_supplied_confidence_export_only_and_inclusive_threshold():
    c = np.array([[0.7, 0.1, np.nan, 0.9]])
    r = pair(confidence=c)
    assert r.mask[0, 0]
    assert pair(threshold=0.7, confidence=c).mask[0, 0]
    assert not pair(threshold=0.71, confidence=c).mask.any()
    np.testing.assert_equal(
        pair(threshold=0.71, confidence=c).gradient_unmasked, r.gradient_unmasked
    )
    assert r.metadata["confidence_generated"] is False
    np.testing.assert_equal(c, [[0.7, 0.1, np.nan, 0.9]])


@pytest.mark.parametrize(
    "c", [np.ones((2, 2)), np.array([[1.2, 0, 0, 0]]), np.array([[np.inf, 0, 0, 0]])]
)
def test_confidence_validation(c):
    with pytest.raises(ValueError):
        pair(confidence=c)


def test_threshold_requires_source():
    with pytest.raises(ValueError, match="required"):
        pair(threshold=0.5)


def test_modes_keep_legacy_masked_behavior():
    np.testing.assert_equal(pair("masked").gradient, pair("both").gradient)
    with pytest.raises(ValueError):
        pair("unknown")
