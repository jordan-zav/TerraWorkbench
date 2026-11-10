"""Band-limited finite-layer responses and regularized apparent properties.

Independent continuous, laterally periodic layer model, not vendor DENS/SUSC.
Rows increase north and columns east; distances are metres. Susceptibility is
SI, density contrast kg/m3, downward gravity mGal, total magnetic anomaly nT.
"""

import hashlib
from pathlib import Path

import numpy as np
import scipy
from scipy.constants import G

from .magnetic_components import _grid, _real, _cancel
from .spectral import magnetic_direction_factor


def _response(
    values,
    spacing,
    kind,
    top_depth_m,
    thickness_m,
    field_nt,
    inclination,
    declination,
    max_cells,
):
    data, ke, kn, k, band, excluded = _grid(values, spacing, max_cells)
    depth, thickness = float(top_depth_m), float(thickness_m)
    if not np.isfinite([depth, thickness]).all() or depth < 0 or thickness <= 0:
        raise ValueError(
            "Finite nonnegative top depth and positive layer thickness required"
        )
    if kind not in ("density", "susceptibility"):
        raise ValueError("Kind must be density or susceptibility")
    with np.errstate(over="ignore", under="ignore"):
        attenuation = np.exp(-k * depth)
        vertical = -np.expm1(-k * thickness)
    if kind == "density":
        if any(v is not None for v in (field_nt, inclination, declination)):
            raise ValueError("Magnetic field parameters do not apply to density")
        kernel = np.divide(
            2 * np.pi * G * 1e5 * attenuation * vertical,
            k,
            out=np.zeros(data.shape),
            where=k > 0,
        ).astype(complex)
        kernel[0, 0] = 2 * np.pi * G * 1e5 * thickness
        inputs, outputs = "kg/m3", "mGal downward"
    else:
        if any(v is None for v in (field_nt, inclination, declination)):
            raise ValueError(
                "Explicit field strength, inclination and declination required"
            )
        field, inc, dec = float(field_nt), float(inclination), float(declination)
        if (
            not np.isfinite([field, inc, dec]).all()
            or field <= 0
            or not -90 <= inc <= 90
        ):
            raise ValueError(
                "Positive field strength and finite direction with inclination in [-90,90] required"
            )
        direction = magnetic_direction_factor(ke, kn, k, inc, dec)
        # Induced M=chi*B0/mu0; T is the linear projection on B0.
        kernel = 0.5 * field * attenuation * vertical * direction**2
        inputs, outputs = "SI dimensionless", "nT linear total-field anomaly"
    # No interpolation of ambiguous even-grid Nyquist axes is performed.
    kernel[(k > 0) & ~band] = 0.0
    if not np.isfinite(kernel).all():
        raise ValueError("Layer response arithmetic exceeds finite range")
    recipe = dict(
        kind=kind,
        top_depth_m=depth,
        thickness_m=thickness,
        spacing_m=list(map(float, spacing)),
        property_units=inputs,
        data_units=outputs,
        field_nt=None if kind == "density" else field,
        inclination_degrees=None if kind == "density" else inc,
        declination_degrees=None if kind == "density" else dec,
        excluded_nyquist_modes=excluded,
        model="Continuous periodic layer, property constant with depth",
        axes="Rows north, columns east; inclination positive down; declination clockwise from grid north",
        gravitational_constant_si=float(G) if kind == "density" else None,
        libraries={"numpy": np.__version__, "scipy": scipy.__version__},
        source_sha256={
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in (
                "apparent_properties.py",
                "magnetic_components.py",
                "spectral.py",
                "_array_contract.py",
                "_calibration.py",
            )
        },
    )
    return data, kernel, k, band, recipe


def layer_property_response(
    values,
    spacing,
    *,
    kind,
    top_depth_m,
    thickness_m,
    field_nt=None,
    inclination=None,
    declination=None,
    max_cells=1_000_000,
    canceled=None,
):
    """Forward density contrast or induced susceptibility in a level layer.

    For k>0, gravity kernel is 2*pi*G*1e5*exp(-kh)*(1-exp(-kt))/k.
    Magnetic kernel is F/2*exp(-kh)*(1-exp(-kt))*d**2 with
    d=sin(I)+i*cos(I)*(ke*sin(D)+kn*cos(D))/k. Susceptibility mean
    produces no external response; uniform density gives the infinite-slab
    response. No remanence, self-demagnetization, terrain or datum adjustment.
    Complete finite periodic input; no implicit fill, detrend or padding.
    """
    _cancel(canceled)
    data, kernel, _, _, recipe = _response(
        values,
        spacing,
        kind,
        top_depth_m,
        thickness_m,
        field_nt,
        inclination,
        declination,
        max_cells,
    )
    result = _real(np.fft.fft2(data) * kernel)
    _cancel(canceled)
    return dict(predicted=result, recipe=recipe)


def apparent_layer_property(
    values,
    spacing,
    *,
    kind,
    top_depth_m,
    thickness_m,
    background,
    regularization_response,
    max_inverse_gain,
    minimum_wavelength_m,
    field_nt=None,
    inclination=None,
    declination=None,
    max_cells=1_000_000,
    canceled=None,
):
    """Regularized apparent contrast plus an explicitly chosen background.

    Uses conjugate(K)/(|K|**2+lambda**2), with explicit inverse-gain cap and
    radial shortest wavelength. lambda is in data-units/property-units;
    max_inverse_gain has reciprocal units. A hard wavelength cutoff is used.
    The observed mean is always removed and reported; background is prescribed
    and never inferred from DC. In magnetic data it is intrinsically invisible.
    At zero inclination exactly transverse modes are unobservable. Recovery
    strength is returned as resolution_transfer, not geological confidence.
    Does not remove IGRF/regional fields, infer geometry or estimate uncertainty.
    """
    _cancel(canceled)
    data, kernel, k, band, recipe = _response(
        values,
        spacing,
        kind,
        top_depth_m,
        thickness_m,
        field_nt,
        inclination,
        declination,
        max_cells,
    )
    background, regularization, cap, wavelength = map(
        float,
        (background, regularization_response, max_inverse_gain, minimum_wavelength_m),
    )
    if (
        not np.isfinite([background, regularization, cap, wavelength]).all()
        or regularization < 0
        or cap <= 0
        or wavelength < 2 * max(recipe["spacing_m"])
    ):
        raise ValueError(
            "Finite background, nonnegative regularization, positive gain and wavelength >= twice largest spacing required"
        )
    magnitude = abs(kernel)
    resolved = band & (k <= 2 * np.pi / wavelength) & (magnitude > 0)
    inverse = np.zeros(data.shape, complex)
    denominator = np.hypot(magnitude[resolved], regularization)
    with np.errstate(over="ignore", under="ignore"):
        gain = (magnitude[resolved] / denominator) / denominator
    clipped = int(np.count_nonzero(gain > cap))
    inverse[resolved] = (
        np.conj(kernel[resolved]) / magnitude[resolved] * np.minimum(gain, cap)
    )
    mean = float(np.mean(data))
    if not np.isfinite(mean):
        raise ValueError("Observed mean exceeds finite range")
    spectrum = np.fft.fft2(data - mean)
    contrast = _real(spectrum * inverse)
    _cancel(canceled)
    predicted = _real(np.fft.fft2(contrast) * kernel)
    residual = data - mean - predicted
    absolute = contrast + background
    if not np.isfinite(absolute).all() or not np.isfinite(residual).all():
        raise ValueError("Apparent property arithmetic exceeds finite range")
    scale = float(np.max(abs(residual))) or 1.0
    rms = scale * float(np.sqrt(np.mean((residual / scale) ** 2)))
    recipe.update(
        background=background,
        regularization_response=regularization,
        max_inverse_gain=cap,
        minimum_wavelength_m=wavelength,
        observed_mean_removed=mean,
        clipped_modes=clipped,
        resolved_modes=int(resolved.sum()),
        residual_rms=rms,
        regularization_units=recipe["data_units"] + "/" + recipe["property_units"],
        inverse_gain_units=recipe["property_units"] + "/" + recipe["data_units"],
        dc="Background prescribed; observed mean removed",
        scope="Apparent property of prescribed layer, not unique geology or DENS/SUSC parity",
    )
    _cancel(canceled)
    return dict(
        property=absolute,
        contrast=contrast,
        predicted_anomaly=predicted,
        residual_anomaly=residual,
        resolved_frequency_mask=resolved,
        resolution_transfer=(kernel * inverse).real,
        recipe=recipe,
    )
