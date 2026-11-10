"""Conversions must not silently discard phase or missing-data masks."""

import numpy as np
import pytest

from terraworkbench_core._array_contract import as_array


def test_real_conversion_rejects_complex_and_preserves_explicit_complex():
    for value in (np.array([1.0 + 2j]), [1.0 + 0j]):
        with pytest.raises(ValueError, match="Complex"):
            as_array(value, float)
    np.testing.assert_array_equal(as_array([1 + 2j], complex), [1 + 2j])
    np.testing.assert_array_equal(as_array([1 + 2j]), [1 + 2j])
    np.testing.assert_array_equal(as_array([1, 2], float), [1.0, 2.0])
