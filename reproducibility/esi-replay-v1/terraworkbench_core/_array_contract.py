"""Input conversion that never silently drops a NumPy missing-data mask."""

import numpy as np


def as_array(values, dtype=None):
    """Require explicit missing-data handling before numerical conversion.

    np.asarray discards MaskedArray masks. Reject populated masks instead;
    callers may deliberately fill with NaN where a method supports gaps.
    """
    if np.ma.isMaskedArray(values) and np.any(np.ma.getmask(values)):
        raise ValueError(
            "Masked data require explicit NoData handling before processing"
        )
    array = np.asarray(values)
    if (
        dtype is not None
        and np.issubdtype(np.dtype(dtype), np.number)
        and not np.issubdtype(np.dtype(dtype), np.complexfloating)
        and np.iscomplexobj(array)
    ):
        raise ValueError("Complex data require explicit real/imaginary handling")
    return np.asarray(array, dtype=dtype)
