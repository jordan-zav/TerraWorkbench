"""Pure helpers for robust delimited-grid detection and validation."""

from __future__ import annotations

import csv

import numpy as np


def detect_delimited_layout(first_line):
    """Return ``(delimiter, has_header)`` without mistaking exponents for text."""
    delimiter = next(
        (candidate for candidate in (",", ";", "\t") if candidate in first_line),
        None,
    )
    if delimiter is None:
        tokens = first_line.strip().split()
    else:
        tokens = next(csv.reader([first_line], delimiter=delimiter))

    def is_number(value):
        try:
            float(value.strip())
        except ValueError:
            return False
        return True

    has_header = not tokens or not all(is_number(token) for token in tokens)
    return delimiter, has_header


def regular_coordinate_axes(x, y):
    """Validate one unique sample per regular Cartesian grid cell."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError("X and Y coordinate columns have different lengths.")
    if x.ndim != 1:
        x = x.ravel()
        y = y.ravel()
    if x.size == 0:
        raise ValueError("The delimited grid contains no finite coordinates.")

    coordinates = np.column_stack((x, y))
    if np.unique(coordinates, axis=0).shape[0] != coordinates.shape[0]:
        raise ValueError("The delimited grid contains duplicate X/Y coordinates.")

    east = np.unique(x)
    north = np.unique(y)
    if east.size < 2 or north.size < 2 or east.size * north.size != x.size:
        raise ValueError(
            "The points are not a complete regular grid. Grid/interpolate the "
            "survey first; TerraWorkbench will not silently invent values."
        )
    dx = np.diff(east)
    dy = np.diff(north)
    if not np.allclose(dx, dx[0]) or not np.allclose(dy, dy[0]):
        raise ValueError("The X/Y spacing is not regular.")
    return east, north, dx, dy
