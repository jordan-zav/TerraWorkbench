"""Independent spatial processing; no QGIS or proprietary runtime required."""

import numpy as np


class ThinPlateGridder:
    """Global minimum-bending TPS, or explicitly local TPS approximation.

    Coordinates use a single isotropic scale. Smoothing is dimensionless in
    those normalized coordinates, not tension or a RANGRID parameter.
    Coincident observations are averaged deterministically.
    """

    def __init__(self, coordinates, values, smoothing=0.0, neighbors=0):
        from scipy.interpolate import RBFInterpolator

        xy = np.asarray(coordinates, dtype=float)
        z = np.asarray(values, dtype=float)
        if xy.ndim != 2 or xy.shape[1] != 2 or z.shape != (len(xy),):
            raise ValueError("Expected N x 2 coordinates and N values.")
        if not np.isfinite(xy).all() or not np.isfinite(z).all():
            raise ValueError("TPS inputs must be finite.")
        if not np.isfinite(smoothing) or smoothing < 0:
            raise ValueError("TPS smoothing must be finite and non-negative.")
        if int(neighbors) != neighbors or neighbors < 0 or 0 < neighbors < 3:
            raise ValueError("TPS neighbors must be zero or an integer >= 3.")
        unique, inverse, counts = np.unique(xy, axis=0, return_inverse=True, return_counts=True)
        self.duplicate_count = len(xy) - len(unique)
        z = np.bincount(inverse, weights=z) / counts
        if len(unique) < 3:
            raise ValueError("TPS requires at least three distinct points.")
        self.origin = unique.mean(axis=0)
        self.scale = float(np.ptp(unique, axis=0).max())
        normalized = (unique - self.origin) / self.scale
        if np.linalg.matrix_rank(np.column_stack((np.ones(len(unique)), normalized))) < 3:
            raise ValueError("TPS points must not be collinear.")
        if neighbors == 0 and len(unique) > 2000:
            raise ValueError("Global TPS is limited to 2000 unique points. Use local TPS neighbors or reduce the input; no silent subsampling is performed.")
        self.neighbors = min(int(neighbors), len(unique)) if neighbors else None
        self.model = RBFInterpolator(normalized, z, kernel="thin_plate_spline",
                                     degree=1, smoothing=smoothing, neighbors=self.neighbors)

    def __call__(self, query):
        query = np.asarray(query, dtype=float)
        if query.ndim != 2 or query.shape[1] != 2 or not np.isfinite(query).all():
            raise ValueError("TPS query must contain finite N x 2 coordinates.")
        try:
            result = self.model((query - self.origin) / self.scale)
        except np.linalg.LinAlgError as error:
            raise ValueError("TPS neighborhood is singular; increase the neighbor count or use non-collinear points.") from error
        if not np.isfinite(result).all():
            raise ValueError("TPS produced non-finite values.")
        return result


def _raster(values):
    data = np.asarray(values, dtype=float)
    if data.ndim != 2 or not data.size or not np.isfinite(data).any():
        raise ValueError("A two-dimensional raster with finite cells is required.")
    return data, np.isfinite(data)


def smooth_nine_point(values, passes=1, canceled=None):
    """Binomial 3x3 kernel [1,2,1] outer product; valid-weight normalization.

    Outside the raster and NoData contribute no weight. Original holes remain
    holes after every pass. This is not a claimed gridflt9 reproduction.
    """
    from scipy.ndimage import convolve

    data, valid = _raster(values)
    if int(passes) != passes or not 1 <= passes <= 100:
        raise ValueError("Smoothing passes must be an integer from 1 to 100.")
    kernel = np.outer([1., 2., 1.], [1., 2., 1.])
    weight = convolve(valid.astype(float), kernel, mode="constant", cval=0.)
    result = data.copy()
    for _ in range(int(passes)):
        if canceled is not None and canceled():
            raise InterruptedError("Processing canceled.")
        total = convolve(np.where(valid, result, 0.), kernel, mode="constant", cval=0.)
        result = np.divide(total, weight, out=np.full_like(total, np.nan), where=valid)
    return result


def circular_median(values, radius=1, canceled=None):
    """Median over a pixel-centre disk, not an angular/circular-statistics median.

    Offsets satisfy dx²+dy² <= radius². Ignore outside/NoData neighbors but
    preserve the original missing footprint. Even valid counts use their middle
    pair average. Bounded gather blocks avoid a full image x footprint array.
    """
    data, valid = _raster(values)
    if not np.isfinite(radius) or int(radius) != radius or not 1 <= radius <= 50:
        raise ValueError("Circular median radius must be an integer from 1 to 50 pixels.")
    radius = int(radius)
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    disk = xx * xx + yy * yy <= radius * radius
    dy, dx = yy[disk], xx[disk]
    padded = np.pad(np.where(valid, data, np.nan), radius, constant_values=np.nan)
    result = np.full_like(data, np.nan)
    block = max(1, 262144 // len(dx))
    # Iterate rows without allocating an index array for every valid raster cell.
    for row in range(data.shape[0]):
        columns = np.flatnonzero(valid[row])
        for start in range(0, len(columns), block):
            if canceled is not None and canceled():
                raise InterruptedError("Processing canceled.")
            selected = columns[start:start + block]
            neighbors = padded[row + radius + dy[None, :], selected[:, None] + radius + dx[None, :]]
            result[row, selected] = np.nanmedian(neighbors, axis=1)
    return result


def automatic_gain_control(values, window=11, floor_fraction=0.05, max_gain=10.):
    """Global RMS / local RMS gain, with an RMS floor and gain cap.

    Square odd-sized window in pixels; no mean subtraction. Units are retained
    algebraically, but amplitude is altered and is unsuitable for inversion.
    """
    from scipy.ndimage import uniform_filter

    data, valid = _raster(values)
    if int(window) != window or not 3 <= window <= 1001 or window % 2 != 1:
        raise ValueError("AGC window must be an odd integer from 3 to 1001.")
    if not np.isfinite(floor_fraction) or not 0 < floor_fraction <= 1:
        raise ValueError("AGC RMS floor fraction must be in (0, 1].")
    if not np.isfinite(max_gain) or max_gain < 1:
        raise ValueError("AGC maximum gain must be finite and >= 1.")
    scale = float(np.max(np.abs(data[valid])))
    if scale == 0:
        return np.where(valid, 0., np.nan)
    normalized = np.where(valid, data / scale, 0.)
    weight = uniform_filter(valid.astype(float), size=int(window), mode="constant")
    square = uniform_filter(normalized**2, size=int(window), mode="constant")
    local = np.sqrt(np.maximum(np.divide(square, weight, out=np.zeros_like(square), where=weight > 0), 0))
    target = float(np.sqrt(np.mean(normalized[valid]**2)))
    gain = np.minimum(target / np.maximum(local, floor_fraction * target), max_gain)
    with np.errstate(over="ignore", invalid="ignore"):
        result = np.where(valid, data * gain, np.nan)
    if not np.isfinite(result[valid]).all():
        raise ValueError("AGC output overflow; rescale the input.")
    return result
