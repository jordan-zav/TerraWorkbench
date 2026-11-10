"""Band-limited potential-field component conversion and gradient integration.

Complete, periodic level grids in ENU coordinates; rows increase northward,
columns eastward. North-up raster rows must be oriented by the caller.
No fill, padding, detrend,
field direction or vertical datum is inferred. Results are not unique geology.
"""

import numpy as np

from ._array_contract import as_array
from ._calibration import integer_budget
from .spectral import frequency_grid, magnetic_direction_factor


def _grid(values, spacing, max_cells):
    integer_budget(max_cells, "Maximum cells")
    values = as_array(values, float)
    spacing = as_array(spacing, float)
    if (
        values.ndim != 2
        or min(values.shape) < 3
        or values.size > max_cells
        or not np.isfinite(values).all()
    ):
        raise ValueError(
            "A complete finite 2-D grid within the cell budget is required"
        )
    if spacing.shape != (2,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Spacing must be positive (northing,easting) metres")
    ke, kn, radial = frequency_grid(values.shape, *spacing)
    nyquist = np.zeros(values.shape, dtype=bool)
    if values.shape[0] % 2 == 0:
        nyquist[values.shape[0] // 2, :] = True
    if values.shape[1] % 2 == 0:
        nyquist[:, values.shape[1] // 2] = True
    return values, ke, kn, radial, (radial > 0) & ~nyquist, int(nyquist.sum())


def _real(spectrum):
    if not np.isfinite(spectrum).all():
        raise ValueError("Spectral arithmetic exceeds finite range")
    result = np.fft.ifft2(spectrum)
    if not np.isfinite(result).all() or np.max(abs(result.imag)) > 1e-10 * max(
        1.0, float(np.max(abs(result.real)))
    ):
        raise ValueError("Result is not a finite real field; review frequency symmetry")
    return result.real


def _cancel(canceled):
    if canceled is not None and canceled():
        raise RuntimeError("Magnetic transformation canceled")


def convert_field_component(
    values,
    spacing,
    *,
    input_component,
    output_component,
    output_mean_nt,
    inclination=None,
    declination=None,
    damping=0.0,
    max_gain=100.0,
    max_cells=4_000_000,
    canceled=None,
):
    """Convert total/east/north/up/down anomaly components in nT.

    Total means the SMALL-ANOMALY projection onto a constant reference field,
    not |B0+b|-|B0|. Inclination is positive down, declination clockwise from
    grid north in degrees. Both are mandatory whenever total is involved.
    A source-free harmonic half-space is assumed. At nonzero wavenumber,
    E/D=i*ke/k, N/D=i*kn/k, U/D=-1, T/D=sin(I)+i*cos(I)*(ke*sin(D)+kn*cos(D))/k.
    The inverse uses conjugate(input)/(|input|^2+damping^2), then a dimensionless
    gain cap. Unobservable and even-grid Nyquist modes are set to zero and
    counted. The output DC mean must be explicitly supplied, never inferred.
    """
    components = {"total", "east", "north", "up", "down"}
    if input_component not in components or output_component not in components:
        raise ValueError("Component must be total, east, north, up or down")
    damping, max_gain, mean = float(damping), float(max_gain), float(output_mean_nt)
    if not np.isfinite([damping, max_gain, mean]).all() or damping < 0 or max_gain < 1:
        raise ValueError(
            "Finite explicit mean, damping >= 0 and gain cap >= 1 are required"
        )
    _cancel(canceled)
    values, ke, kn, radial, usable, nyquist = _grid(values, spacing, max_cells)
    factors = {
        "down": np.ones(values.shape, complex),
        "up": -np.ones(values.shape, complex),
    }
    factors["east"] = np.divide(
        1j * ke, radial, out=np.zeros(values.shape, complex), where=radial > 0
    )
    factors["north"] = np.divide(
        1j * kn, radial, out=np.zeros(values.shape, complex), where=radial > 0
    )
    if "total" in (input_component, output_component):
        if (
            inclination is None
            or declination is None
            or not np.isfinite([inclination, declination]).all()
            or not -90 <= inclination <= 90
            or not -180 <= declination <= 180
        ):
            raise ValueError(
                "Explicit finite grid-north field angles in degrees are required"
            )
        factors["total"] = magnetic_direction_factor(
            ke, kn, radial, inclination, declination
        )
    source, target = factors[input_component], factors[output_component]
    observed = usable & (abs(source) > 1e-12)
    response = np.zeros(values.shape, complex)
    response[observed] = (
        target[observed]
        * source[observed].conjugate()
        / (abs(source[observed]) ** 2 + damping**2)
    )
    excessive = abs(response) > max_gain
    response[excessive] *= max_gain / abs(response[excessive])
    transformed = np.fft.fft2(values) * response
    transformed[0, 0] = mean * values.size
    result = _real(transformed)
    _cancel(canceled)
    return dict(
        field_nt=result,
        resolved_frequency_mask=observed,
        recipe=dict(
            input_component=input_component,
            output_component=output_component,
            output_mean_nt=mean,
            inclination=inclination,
            declination=declination,
            spacing_m=list(map(float, spacing)),
            damping=damping,
            max_gain=max_gain,
            clipped_modes=int(excessive.sum()),
            unobservable_modes=int((usable & ~observed).sum()),
            removed_nyquist_modes=nyquist,
            units="nT",
            axes="east,north,up",
            domain="Periodic level grid; DC supplied, not recovered; no boundary preparation",
        ),
    )


def reconstruct_tmi_from_gradients(
    spacing,
    *,
    reference_mean_nt,
    gradient_east=None,
    gradient_north=None,
    gradient_up=None,
    weights=None,
    damping_wavenumber=0.0,
    max_cells=4_000_000,
    canceled=None,
):
    """Weighted spectral least-squares integration of TMI derivatives (nT/m).

    At least one gradient is required. Weights are positive relative weights
    by east/north/up, not estimated covariance. The ridge wavenumber is rad/m.
    Operators are i*ke, i*kn, -k; the vertical gradient MUST be positive up.
    Returned field is nT. The DC datum is supplied by the caller. Unobservable
    modes and Nyquist rows/columns are zero, not observations or recovered data.
    Predictions and residual RMS permit consistency checks on supplied gradients.
    """
    supplied = {
        name: value
        for name, value in (
            ("east", gradient_east),
            ("north", gradient_north),
            ("up", gradient_up),
        )
        if value is not None
    }
    if not supplied:
        raise ValueError("At least one explicit TMI gradient is required")
    mean, damping = float(reference_mean_nt), float(damping_wavenumber)
    if not np.isfinite([mean, damping]).all() or damping < 0:
        raise ValueError(
            "Finite reference mean and nonnegative damping wavenumber are required"
        )
    weights = {name: 1.0 for name in supplied} if weights is None else dict(weights)
    if set(weights) != set(supplied) or any(
        not np.isfinite(w) or w <= 0 for w in weights.values()
    ):
        raise ValueError(
            "Positive relative weights must match the supplied gradient components"
        )
    _cancel(canceled)
    first, ke, kn, radial, usable, nyquist = _grid(
        next(iter(supplied.values())), spacing, max_cells
    )
    operators = {"east": 1j * ke, "north": 1j * kn, "up": -radial}
    numerator, normal = np.zeros(first.shape, complex), np.zeros(first.shape)
    arrays = {}
    for name, values in supplied.items():
        values = as_array(values, float)
        if values.shape != first.shape or not np.isfinite(values).all():
            raise ValueError(
                "All gradient grids must have the same complete finite shape"
            )
        arrays[name] = values
        operator, weight = operators[name], weights[name]
        numerator += weight * operator.conjugate() * np.fft.fft2(values)
        normal += weight * abs(operator) ** 2
    resolved = usable & (normal > 0)
    spectrum = np.zeros(first.shape, complex)
    spectrum[resolved] = numerator[resolved] / (normal[resolved] + damping**2)
    spectrum[0, 0] = mean * first.size
    field = _real(spectrum)
    predictions = {name: _real(operators[name] * spectrum) for name in supplied}
    rms = {
        name: float(np.sqrt(np.mean((predictions[name] - arrays[name]) ** 2)))
        for name in supplied
    }
    _cancel(canceled)
    return dict(
        tmi_nt=field,
        predicted_gradients=predictions,
        residual_rms_nt_per_m=rms,
        resolved_frequency_mask=resolved,
        recipe=dict(
            reference_mean_nt=mean,
            gradient_units="nT/m",
            field_units="nT",
            vertical_gradient="positive up",
            spacing_m=list(map(float, spacing)),
            weights={name: float(value) for name, value in weights.items()},
            damping_wavenumber_rad_per_m=damping,
            unobservable_modes=int((usable & ~resolved).sum()),
            removed_nyquist_modes=nyquist,
            domain="Periodic level grid; no inferred DC, geometry, filling or padding",
        ),
    )
