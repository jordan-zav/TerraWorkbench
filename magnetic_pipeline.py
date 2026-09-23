"""Versioned, GUI-independent magnetic grid pipeline with retained FFT margins.

Arrays are south-to-north, west-to-east. Filling is confined to the numerical
workspace; all published products restore the original support mask.
"""
from dataclasses import asdict, dataclass

import numpy as np

if __package__:
    from .spectral import prepare_fft_grid, finish_fft_grid, frequency_grid, magnetic_field_transform, apply_transfer
else:
    from spectral import prepare_fft_grid, finish_fft_grid, frequency_grid, magnetic_field_transform, apply_transfer


@dataclass
class MagneticPipelineOptions:
    inclination: float
    declination: float
    declination_frame: str = "grid"
    grid_convergence: float = 0.0
    derivative_method: str = "fft"
    angle_units: str = "radians"
    continuation_height: float = 500.0
    padding_rows: int = 16
    padding_columns: int = 16
    detrend_order: int = -1
    taper_percent: float = 0.0
    nodata_policy: str = "nearest"
    max_gain: float = 100.0

    def validate(self):
        if not np.isfinite([self.inclination, self.declination, self.grid_convergence,
                           self.continuation_height, self.taper_percent, self.max_gain]).all():
            raise ValueError("Pipeline parameters must be finite.")
        if not -90 <= self.inclination <= 90 or self.max_gain <= 1:
            raise ValueError("Invalid inclination or maximum gain.")
        if self.declination_frame not in ("grid", "true"):
            raise ValueError("Choose grid or true-north declination explicitly.")
        if self.derivative_method not in ("fft", "finite_difference") or self.angle_units not in ("radians", "degrees"):
            raise ValueError("Choose fft/finite_difference and radians/degrees explicitly.")
        if self.continuation_height < 0 or not 0 <= self.taper_percent <= 100:
            raise ValueError("Invalid continuation height or taper.")
        if self.detrend_order not in (-1, 0, 1) or self.nodata_policy not in ("nearest", "reject"):
            raise ValueError("Invalid detrend order or NoData policy.")
        if any(type(p) is not int or not 0 <= p <= 4096 for p in (self.padding_rows, self.padding_columns)):
            raise ValueError("Padding must be integer cells between 0 and 4096 per side.")


def magnetic_grid_products(values, spacing, options, canceled=None):
    """Branch from one padded RTP; crop/mask only final products.

    No removed trend is restored to transformed anomalies. RMI retains the input.
    True-north declination follows the host convention: grid angle = true angle
    + supplied grid convergence. Callers must derive convergence for their CRS.
    """
    options.validate()
    if len(spacing) != 2 or not np.isfinite(spacing).all() or min(spacing) <= 0:
        raise ValueError("Spacing must contain positive northing/easting distances.")
    def check():
        if canceled and canceled():
            raise InterruptedError("Magnetic pipeline canceled; no products published.")
    check()
    prepared, state = prepare_fft_grid(values, options.detrend_order, 0, options.taper_percent,
        padding_cells=(options.padding_rows, options.padding_columns), nodata_policy=options.nodata_policy)
    ke, kn, radial = frequency_grid(prepared.shape, *spacing)
    dec = options.declination + (options.grid_convergence if options.declination_frame == "true" else 0)
    rtp = apply_transfer(prepared, magnetic_field_transform(ke, kn, radial, options.inclination, dec, 90, 0,
                                                         max_gain=options.max_gain))
    check()
    if options.derivative_method == "fft":
        dx = apply_transfer(rtp, 1j * ke)
        dy = apply_transfer(rtp, 1j * kn)
    else:
        dy, dx = np.gradient(rtp, *spacing, edge_order=1)
    dz = apply_transfer(rtp, -radial)
    dz2 = apply_transfer(rtp, radial**2)
    uc = apply_transfer(rtp, np.exp(-radial * options.continuation_height))
    thdr = np.hypot(dx, dy)
    analytic = np.sqrt(dx**2 + dy**2 + dz**2)
    theta = np.arccos(np.clip(np.divide(thdr, analytic, out=np.zeros_like(thdr), where=analytic > 0), -1, 1))
    theta[analytic == 0] = 0  # explicitly defined zero-signal angle
    products = {"RTP": rtp, "DX": dx, "DY": dy, "DZ_1VD": dz, "DZ2_2VD": dz2,
                "THDR": thdr, "AS": analytic, "45HG": (dx + dy) / np.sqrt(2),
                "Tilt": np.arctan2(dz, thdr), "TDX": np.arctan2(thdr, np.abs(dz)),
                "Theta": theta, "UC500" if options.continuation_height == 500 else "UC": uc, "RS": rtp - uc}
    for key in products:
        check()
        if not np.isfinite(products[key]).all():
            raise ValueError(f"Nonfinite intermediate product: {key}")
        products[key] = finish_fft_grid(products[key], state, restore_trend=False)
        if options.angle_units == "degrees" and key in ("Tilt", "TDX", "Theta"):
            products[key] = np.degrees(products[key])
    products["RMI"] = np.asarray(values, dtype=float).copy()
    products["RMI"][state["missing"]] = np.nan
    return products, {"recipe_version": 1, "operation": "magnetic_grid_pipeline", "parameters": asdict(options),
        "preparation": "nearest fill only in workspace; reflect pad once; crop and restore mask at publication",
        "branch_source": "padded RTP for all derivatives and continuation", "numpy": np.__version__,
        "missing_cells": int(state["missing"].sum()), "zero_signal_theta": 0}


def line_correction_surface(batches, x_name, y_name, line_name, correction_name, x_grid, y_grid,
                            support, sample_step_cells=4.0, sigma_cells=2.0, canceled=None):
    """Rasterize database correction channels onto a published grid.

    Line rows must be contiguous and ordered. Sampling is based on cumulative
    distance per line. This is not interpolation of raw magnetic observations.
    Grid coordinates must be increasing, regularly spaced pixel centers.
    """
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    x_grid, y_grid = np.asarray(x_grid), np.asarray(y_grid)
    if min(len(x_grid), len(y_grid)) < 2:
        raise ValueError("Correction grid must have at least two cells per axis.")
    dx, dy = float(x_grid[1] - x_grid[0]), float(y_grid[1] - y_grid[0])
    if min(dx, dy) <= 0 or not np.allclose(np.diff(x_grid), dx) or not np.allclose(np.diff(y_grid), dy):
        raise ValueError("Correction grid axes must be increasing and regular.")
    if not np.isfinite([sample_step_cells, sigma_cells]).all() or sample_step_cells <= 0 or sigma_cells < 0:
        raise ValueError("Invalid correction surface spacing/smoothing.")
    support = np.asarray(support, dtype=bool)
    if support.shape != (len(y_grid), len(x_grid)) or not support.any():
        raise ValueError("Invalid correction surface support mask.")
    sums, counts = np.zeros(support.shape), np.zeros(support.shape, dtype=np.int64)
    visited, previous_line, previous_xy = set(), None, None
    distance, previous_bin, rows = 0., -1, 0
    step = max(dx, dy) * sample_step_cells
    for batch in batches:
        if canceled and canceled():
            raise InterruptedError("Correction surface canceled.")
        data = batch.to_pydict()
        for x, y, line, correction in zip(data[x_name], data[y_name], data[line_name], data[correction_name]):
            rows += 1
            if rows % 1024 == 0 and canceled and canceled():
                raise InterruptedError("Correction surface canceled.")
            if line is None or any(v is None for v in (x, y, correction)):
                raise ValueError(f"Row {rows}: missing coordinates, line or correction.")
            x, y, correction = float(x), float(y), float(correction)
            if not np.isfinite([x, y, correction]).all():
                raise ValueError(f"Row {rows}: nonfinite surface inputs.")
            line = str(line)
            if line != previous_line:
                if line in visited:
                    raise ValueError("Correction surface requires contiguous line rows; no implicit sorting.")
                visited.add(line)
                previous_line, previous_xy = line, None
                distance, previous_bin = 0., -1
            if previous_xy is not None:
                distance += np.hypot(x - previous_xy[0], y - previous_xy[1])
            current_bin = int(np.floor(distance / step))
            if current_bin > previous_bin:
                col, row = int(np.rint((x - x_grid[0]) / dx)), int(np.rint((y - y_grid[0]) / dy))
                if 0 <= row < len(y_grid) and 0 <= col < len(x_grid):
                    sums[row, col] += correction
                    counts[row, col] += 1
            previous_xy, previous_bin = (x, y), current_bin
    known = counts > 0
    if not known.any():
        raise ValueError("No correction samples intersect the template grid.")
    sparse = np.divide(sums, counts, out=np.zeros_like(sums), where=known)
    indices = distance_transform_edt(~known, return_distances=False, return_indices=True)
    surface = gaussian_filter(sparse[tuple(indices)], sigma=sigma_cells, mode="nearest")
    surface[~support] = np.nan
    return surface, {"operation": "line_constant_surface", "sample_step_cells": sample_step_cells,
                     "sigma_cells": sigma_cells, "distance_sampling": "first sample in each cumulative-distance bin",
                     "source_rows": rows, "lines": len(visited), "populated_cells": int(known.sum()),
                     "fill": "nearest correction then Gaussian smoothing; original template support retained"}
