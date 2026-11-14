"""Independent sequential raster recipes backed by TerraWorkbench FFT helpers."""

from __future__ import annotations

import re
import numpy as np

FILTERS = (
    "1VD",
    "2VD",
    "DX",
    "DY",
    "TDR",
    "THDR",
    "UC",
    "AS",
    "AGC",
    "RTP",
    "LP",
    "HP",
    "MEDIAN",
    "STD",
    "VAR",
    "DIRECTIONAL",
    "WAVELET",
)
_BASE_UNITS = {
    "DX": "nT/m",
    "DY": "nT/m",
    "DZ_1VD": "nT/m",
    "DZ2_2VD": "nT/m^2",
    "THDR": "nT/m",
    "AS": "nT/m",
    "45HG": "nT/m",
    "Tilt": "degrees",
    "TDX": "degrees",
    "Theta": "degrees",
}


def _check(canceled):
    if canceled and canceled():
        raise InterruptedError("Filter proposals canceled; no products published.")


def _number(value, label, minimum=0.0, inclusive=True):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be finite.") from None
    if not np.isfinite(number) or (
        number < minimum if inclusive else number <= minimum
    ):
        raise ValueError(f"Invalid {label}.")
    return number


def _derivative_units(units, order=1):
    match = re.fullmatch(r"(.+?)(?:/m(?:\^(\d+))?)?", units)
    numerator, exponent = match.groups()
    old = int(exponent) if exponent else (1 if "/m" in units else 0)
    power = old + order
    return numerator + ("/m" if power == 1 else f"/m^{power}")


def _grid(values, cell_size, padding):
    arr = np.ma.asarray(values, dtype=float).filled(np.nan)
    if arr.ndim != 2 or min(arr.shape) < 2 or not np.isfinite(arr).any():
        raise ValueError("A supported 2D grid with two cells per axis is required.")
    if np.isinf(arr).any():
        raise ValueError("Infinite grid samples are invalid; use NaN for NoData.")
    _number(cell_size, "cell size in metres", inclusive=False)
    if type(padding) is not int or not 0 <= padding <= 4096:
        raise ValueError("Padding must be integer cells between 0 and 4096.")
    if (
        arr.size > 4_000_000
        or (arr.shape[0] + 2 * padding) * (arr.shape[1] + 2 * padding) > 8_000_000
    ):
        raise ValueError(
            "Grid exceeds 4 million output or 8 million FFT workspace cells."
        )
    return arr


def apply_proposals(
    grid_south_to_north,
    cell_size,
    proposals,
    *,
    base_grids=None,
    inclination=None,
    declination=None,
    padding=16,
    angle_units="degrees",
    canceled=None,
    base_units=None,
    composite_derivative_method="finite_difference",
    vertical_positive="down",
    composite_preparation=None,
    horizontal_fft_convention="classic",
    validate_only=False,
    stage_callback=None,
):
    """Return named final arrays and JSON-safe provenance for up to three recipes.

    Each proposal is {name, base, steps:[{filter, param, ...}]}. Bases raw/RMI
    select the caller grid; others must exist in base_grids. UC param is height
    metres. AGC param/window_metres is full square width; default 10 m with gain
    capped at 10. LP/HP param is Gaussian sigma metres; MEDIAN/STD/VAR param
    is full square width metres. These five filters require explicit parameters.
    STD and VAR use population moments. Each chain pads once in listed order. Original
    support is restored only on publication. No proprietary AGC parity claimed.
    """
    from terraworkbench_core.spectral import (
        prepare_fft_grid,
        finish_fft_grid,
        frequency_grid,
        apply_transfer,
        magnetic_field_transform,
        set_rtp_mean,
    )

    _check(canceled)
    raw = _grid(grid_south_to_north, cell_size, padding)
    if horizontal_fft_convention not in ("standard", "classic"):
        raise ValueError("Choose standard/classic horizontal FFT convention explicitly.")
    if angle_units not in ("degrees", "radians"):
        raise ValueError("Angle units must be degrees or radians.")
    if composite_derivative_method not in ("fft", "finite_difference"):
        raise ValueError(
            "Choose fft/finite_difference composite derivatives explicitly."
        )
    if composite_preparation is None:
        composite_preparation = (
            "edge_plane_prediction"
            if composite_derivative_method == "finite_difference"
            else "reflect"
        )
    if composite_preparation not in (
        "reflect",
        "edge_plane_biharmonic",
        "edge_plane_prediction",
    ):
        raise ValueError(
            "Choose reflect, edge_plane_biharmonic or edge_plane_prediction composite preparation."
        )
    if (
        composite_preparation != "reflect"
        and composite_derivative_method != "finite_difference"
    ):
        raise ValueError(
            "Edge-plane composite preparation requires central horizontal derivatives."
        )
    if vertical_positive not in ("down", "up"):
        raise ValueError("Choose down/up vertical derivative convention explicitly.")
    if not isinstance(proposals, list) or len(proposals) > 3:
        raise ValueError("Provide a list of at most three filter proposals.")
    available = dict(base_grids or {})
    available.update(raw=raw, RMI=raw)
    units_map = dict(_BASE_UNITS)
    for angle in ("Tilt", "TDX", "Theta"):
        units_map[angle] = angle_units
    units_map.update(base_units or {})
    reserved = {key.casefold() for key in available}
    reserved.update(
        {
            "magnetogram",
            "direction_1",
            "direction_2",
            "preview",
            "points",
            "manifest",
            "qc_json",
            "pipeline_json",
            "pipeline_svg",
            "con",
            "prn",
            "aux",
            "nul",
        }
    )
    validated, names = [], set()
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("Each proposal must be an object.")
        name = proposal.get("name", "")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,79}", name)
            or name.casefold() in names
        ):
            raise ValueError(
                "Proposal names must be unique safe names of at most 80 characters."
            )
        if (
            name.casefold() in reserved
            or name != name.strip()
            or re.fullmatch(
                r"(?:points|direction)_\d+|(?:com|lpt)[1-9]", name.casefold()
            )
        ):
            raise ValueError(
                f"Proposal name collides with a reserved product or output: {name}"
            )
        names.add(name.casefold())
        base = proposal.get("base", "raw")
        if not isinstance(base, str) or base not in available:
            raise ValueError(f"Unavailable proposal base: {base}")
        arr = _grid(available[base], cell_size, padding)
        if arr.shape != raw.shape:
            raise ValueError("Every proposal base must share the input grid shape.")
        steps = proposal.get("steps", [])
        if not isinstance(steps, list) or len(steps) > 32:
            raise ValueError("Each proposal permits at most 32 steps.")
        parsed = []
        for step in steps:
            if not isinstance(step, dict) or step.get("filter") not in FILTERS:
                raise ValueError(
                    "Unknown raster filter; choose a supported filter explicitly."
                )
            f = step["filter"]
            params = {"filter": f}
            if f == "DY":
                params["horizontal_fft_convention"] = horizontal_fft_convention
            if f in ("TDR", "THDR", "AS"):
                params["horizontal_derivative_method"] = composite_derivative_method
            if f in ("1VD", "TDR", "AS"):
                params["vertical_positive"] = vertical_positive
            if f == "UC":
                params["height_metres"] = _number(
                    step.get("height_metres", step.get("param", 500)), "UC height"
                )
            elif f == "AGC":
                width = _number(
                    step.get("window_metres", step.get("param", 10)),
                    "AGC window",
                    inclusive=False,
                )
                cells = max(1, int(np.ceil(width / cell_size)))
                cells += 1 - cells % 2
                if cells > 2049:
                    raise ValueError("AGC window exceeds 2049 cells.")
                gain = _number(step.get("max_gain", 10), "AGC maximum gain", minimum=1)
                if gain > 1000:
                    raise ValueError("AGC maximum gain must not exceed 1000.")
                params.update(window_metres=width, window_cells=cells, max_gain=gain)
            elif f in ("LP", "HP"):
                sigma = _number(
                    step.get("sigma_metres", step.get("param")),
                    "Gaussian sigma in metres",
                    inclusive=False,
                )
                sigma_cells = sigma / cell_size
                if sigma_cells > 256:
                    raise ValueError("Gaussian sigma exceeds 256 cells.")
                params.update(
                    sigma_metres=sigma,
                    sigma_cells=sigma_cells,
                    method="Gaussian",
                    boundary="reflect",
                    truncate_sigma=4.0,
                )
            elif f in ("MEDIAN", "STD", "VAR"):
                width = _number(
                    step.get("window_metres", step.get("param")),
                    "Square window in metres",
                    inclusive=False,
                )
                limit = 31 if f == "MEDIAN" else 2049
                if width / cell_size > limit:
                    raise ValueError(f"{f} window exceeds {limit} cells.")
                cells = max(1, int(np.ceil(width / cell_size)))
                cells += 1 - cells % 2
                params.update(
                    window_metres=width,
                    window_cells=cells,
                    effective_window_metres=float(cells * cell_size),
                    boundary="reflect",
                    method="square median"
                    if f == "MEDIAN"
                    else "square population moments",
                )
            elif f == "WAVELET":
                from .grid_tools import wavelet_settings

                keys = (
                    "stripe_direction",
                    "wavelet",
                    "decomposition_level",
                    "first_level",
                    "last_level",
                    "strength",
                )
                if any(key not in step for key in keys):
                    raise ValueError(
                        "WAVELET requires explicit direction, basis, decomposition, selected levels and strength."
                    )
                cfg = wavelet_settings(
                    None if validate_only else arr.shape,
                    cell_size,
                    **{key: step[key] for key in keys},
                    padding_cells=0,
                )
                params.update(
                    cfg,
                    method="directional DWT detail attenuation",
                    references=[
                        "https://doi.org/10.1046/j.1365-2478.2003.00373.x",
                        "https://doi.org/10.1002/arp.1936",
                    ],
                    implementation="Independent orthogonal DWT; not the cited interpolating wavelet",
                )
            elif f == "DIRECTIONAL":
                from .grid_tools import directional_transfer

                keys = (
                    "stripe_angle_degrees",
                    "half_width_degrees",
                    "wavelength_min_m",
                    "wavelength_max_m",
                    "strength",
                )
                if any(key not in step for key in keys):
                    raise ValueError(
                        "DIRECTIONAL requires explicit angle, angular width, wavelength band and strength."
                    )
                settings = {key: float(step[key]) for key in keys}
                directional_transfer(arr.shape, cell_size, **settings)
                params.update(
                    settings,
                    method="raised-cosine directional notch",
                    angle_reference="clockwise from grid north",
                )
            elif f == "RTP":
                if (
                    inclination is None
                    or declination is None
                    or not np.isfinite([inclination, declination]).all()
                ):
                    raise ValueError(
                        "RTP requires explicit inclination and grid-north declination."
                    )
                if not -90 <= inclination <= 90 or not -180 <= declination <= 180:
                    raise ValueError("Invalid RTP field angles.")
                gain = _number(
                    step.get("max_gain", 100),
                    "RTP maximum gain",
                    minimum=1,
                    inclusive=False,
                )
                if gain > 1000:
                    raise ValueError("RTP maximum gain must not exceed 1000.")
                preserve_mean = step.get("preserve_mean", True)
                if not isinstance(preserve_mean, bool):
                    raise ValueError("RTP preserve_mean must be a boolean.")
                params.update(
                    preserve_mean=preserve_mean,
                    inclination=float(inclination),
                    declination=float(declination),
                    max_gain=gain,
                )
            parsed.append(params)
        validated.append((name, base, arr, parsed))
    if validate_only:
        return {}, dict(
            operation="validate_filter_parameters",
            proposals=[
                dict(name=name, base=base, steps=steps)
                for name, base, arr, steps in validated
            ],
            grid_shape_checked=False,
        )
    products, recipes, product_units = {}, [], {}
    for proposal_index, (name, base, arr, steps) in enumerate(validated):
        _check(canceled)
        work, state = prepare_fft_grid(
            arr, -1, 0, 0, padding_cells=(padding, padding), nodata_policy="nearest"
        )
        ke, kn, radial = frequency_grid(work.shape, cell_size, cell_size)
        units = units_map.get(base, "nT")
        history = []
        published = None
        for step_index, params in enumerate(steps):
            _check(canceled)
            f, input_units = params["filter"], units
            rtp_source = finish_fft_grid(work, state, False) if f == "RTP" else None
            if f in ("DX", "DY", "1VD", "2VD", "UC", "RTP"):
                if f == "DX":
                    transfer = 1j * ke
                elif f == "DY":
                    transfer = 1j * kn.copy()
                    if horizontal_fft_convention == "classic" and work.shape[0] % 2 == 0:
                        # The classic convention uses the east-frequency half-plane
                        # to orient the self-aliased north Nyquist row. Other
                        # frequencies retain the standard spectral derivative.
                        row = work.shape[0] // 2
                        transfer[row] *= np.sign(ke[row])
                        transfer[row, 0] = 0
                        if work.shape[1] % 2 == 0:
                            transfer[row, work.shape[1] // 2] = 0
                elif f == "1VD":
                    transfer = radial if vertical_positive == "down" else -radial
                elif f == "2VD":
                    transfer = radial**2
                elif f == "UC":
                    transfer = np.exp(-radial * params["height_metres"])
                else:
                    transfer = magnetic_field_transform(
                        ke,
                        kn,
                        radial,
                        inclination,
                        declination,
                        90,
                        0,
                        max_gain=params["max_gain"],
                    )
                work = apply_transfer(work, transfer)
                if f in ("DX", "DY", "1VD", "2VD"):
                    units = _derivative_units(units, 2 if f == "2VD" else 1)
            elif f == "WAVELET":
                from .grid_tools import wavelet_directional_filter

                keys = (
                    "stripe_direction",
                    "wavelet",
                    "decomposition_level",
                    "first_level",
                    "last_level",
                    "strength",
                )
                work, diagnostic = wavelet_directional_filter(
                    work,
                    cell_size,
                    **{key: params[key] for key in keys},
                    padding_cells=0,
                )
                params["wavelet_diagnostics"] = diagnostic
            elif f == "DIRECTIONAL":
                from .grid_tools import directional_transfer

                keys = (
                    "stripe_angle_degrees",
                    "half_width_degrees",
                    "wavelength_min_m",
                    "wavelength_max_m",
                    "strength",
                )
                work = apply_transfer(
                    work,
                    directional_transfer(
                        work.shape, cell_size, **{key: params[key] for key in keys}
                    ),
                )
            elif f in ("LP", "HP"):
                from scipy.ndimage import gaussian_filter

                lowpass = gaussian_filter(
                    work, sigma=params["sigma_cells"], mode="reflect", truncate=4.0
                )
                work = lowpass if f == "LP" else work - lowpass
            elif f == "MEDIAN":
                from scipy.ndimage import median_filter

                work = median_filter(work, size=params["window_cells"], mode="reflect")
            elif f in ("STD", "VAR"):
                from scipy.ndimage import uniform_filter

                # Centre before scaling to preserve small variation on a large background.
                centred = work - work.flat[0]
                scale = float(np.max(np.abs(centred)))
                if scale:
                    normalized = centred / scale
                    mean = uniform_filter(
                        normalized, size=params["window_cells"], mode="reflect"
                    )
                    moment = uniform_filter(
                        normalized**2, size=params["window_cells"], mode="reflect"
                    )
                    variance = np.maximum(moment - mean**2, 0.0)
                    work = (
                        np.sqrt(variance) * scale
                        if f == "STD"
                        else variance * scale * scale
                    )
                else:
                    work = np.zeros_like(work)
                if f == "VAR":
                    units = f"({units})^2"
            elif f == "AGC":
                from scipy.ndimage import uniform_filter

                scale = float(np.max(np.abs(work)))
                if scale:
                    normalized = work / scale
                    local = np.sqrt(
                        np.maximum(
                            0,
                            uniform_filter(
                                normalized**2,
                                size=params["window_cells"],
                                mode="reflect",
                            ),
                        )
                    )
                    core = normalized[state["row_slice"], state["column_slice"]][
                        ~state["missing"]
                    ]
                    target = float(np.sqrt(np.mean(core**2)))
                    gain = np.divide(
                        target,
                        local,
                        out=np.full_like(local, params["max_gain"]),
                        where=local > np.finfo(float).eps,
                    )
                    work = work * np.minimum(gain, params["max_gain"])
            else:
                if composite_preparation != "reflect":
                    from terraworkbench_core.classic_style import (
                        composite_derivatives,
                        central_valid,
                    )

                    supported = finish_fft_grid(work, state, restore_trend=False)
                    if f == "THDR":
                        dx, dy = (
                            central_valid(supported, 1, cell_size),
                            central_valid(supported, 0, cell_size),
                        )
                        preparation = {
                            "horizontal_derivatives": "central/one-sided on original support",
                            "vertical_preparation": "not used for THDR",
                        }
                    else:
                        dx, dy, dz, _, preparation = composite_derivatives(
                            supported,
                            (cell_size, cell_size),
                            vertical_positive,
                            composite_preparation,
                        )
                    thdr = np.hypot(dx, dy)
                    result = (
                        thdr
                        if f == "THDR"
                        else (
                            np.arctan2(dz, thdr) if f == "TDR" else np.hypot(thdr, dz)
                        )
                    )
                    if f == "TDR" and angle_units == "degrees":
                        result = np.degrees(result)
                    work, state = prepare_fft_grid(
                        result,
                        -1,
                        0,
                        0,
                        padding_cells=(padding, padding),
                        nodata_policy="nearest",
                    )
                    params["vertical_preparation"] = preparation
                else:
                    if composite_derivative_method == "fft":
                        dx, dy = (
                            apply_transfer(work, 1j * ke),
                            apply_transfer(work, 1j * kn),
                        )
                    else:
                        dy, dx = np.gradient(work, cell_size, cell_size, edge_order=1)
                    thdr = np.hypot(dx, dy)
                    if f == "THDR":
                        work = thdr
                    else:
                        dz = apply_transfer(
                            work, radial if vertical_positive == "down" else -radial
                        )
                        work = (
                            np.arctan2(dz, thdr) if f == "TDR" else np.hypot(thdr, dz)
                        )
                        if f == "TDR" and angle_units == "degrees":
                            work = np.degrees(work)
                units = angle_units if f == "TDR" else _derivative_units(units)
            if not np.isfinite(work).all():
                raise ValueError(f"Nonfinite intermediate in proposal {name}: {f}")
            history.append(dict(params, input_units=input_units, output_units=units))
            published = None
            if rtp_source is not None:
                published = set_rtp_mean(finish_fft_grid(work, state, False),
                                         rtp_source, params["preserve_mean"])
            if stage_callback is not None:
                stage_callback(
                    proposal_index,
                    step_index,
                    published if published is not None else finish_fft_grid(work, state, False),
                    units,
                )
        _check(canceled)
        products[name] = published if published is not None else finish_fft_grid(work, state, False)
        product_units[name] = units
        recipes.append(
            {
                "name": name,
                "base": base,
                "steps": history,
                "output_units": units,
                "missing_cells": int(state["missing"].sum()),
            }
        )
    return products, {
        "recipe_version": 2,
        "operation": "sequential_filter_proposals",
        "proposals": recipes,
        "product_units": product_units,
        "spacing_metres": float(cell_size),
        "padding_cells": padding,
        "array_orientation": "south-to-north rows; west-to-east columns",
        "proprietary_equivalence": False,
        "preparation": "nearest-fill retained margins for sequential filters; composites may use recorded explicit edge-plane vertical preparation; restore original mask",
        "vertical_derivative_sign": "+radial (positive down)"
        if vertical_positive == "down"
        else "-radial (positive up; legacy)",
        "composite_derivative_method": composite_derivative_method,
        "composite_preparation": composite_preparation,
        "horizontal_fft_convention": horizontal_fft_convention,
        "method_revision": "archie-filters-4: independent Burg composite preparation; explicit classic/standard standalone DY Nyquist convention; positive-down vertical; central composite derivatives",
        "agc_definition": "global supported-core RMS divided by reflect square-window local RMS; gain capped; units retained",
        "local_filters_definition": "LP: reflect Gaussian sigma metres, truncate 4 sigma; HP: input minus LP; MEDIAN: odd square median; STD/VAR: odd square population moments; workspace nearest-filled before filtering",
        "limitations": [
            "RTP preserves the supported mean in published stages by default; subsequent stages use the zero-DC FFT workspace.",
            "AGC normalizes by local RMS.",
            "Sequential filtering of angles is allowed and changes physical units accordingly.",
            "Workspace filling and padding influence boundaries; no synthetic coverage published.",
        ],
    }


def radial_spectrum(
    grid_south_to_north, cell_size, *, bins=96, units="nT", canceled=None
):
    """JSON-safe Terra radial mean power, scaled by N squared (not PSD density)."""
    from terraworkbench_core.spectral import prepare_fft_grid, radial_power_spectrum

    _check(canceled)
    grid = _grid(grid_south_to_north, cell_size, 0)
    if type(bins) is not int or not 2 <= bins <= 512:
        raise ValueError("Spectrum bins must be integer between 2 and 512.")
    prepared, state = prepare_fft_grid(
        grid, 0, 0, 0, padding_cells=(0, 0), nodata_policy="nearest"
    )
    k, power = radial_power_spectrum(prepared, cell_size, cell_size, bins=bins)
    _check(canceled)
    return {
        "wavenumber_rad_per_m": k.tolist(),
        "frequency_cycles_per_m": (k / (2 * np.pi)).tolist(),
        "mean_power": (power / grid.size**2).tolist(),
        "bins": bins,
        "input_units": units,
        "power_units": f"({units})^2",
        "missing_cells": int(state["missing"].sum()),
        "method": "Terra radial annular mean |FFT|^2/N^2; nearest fill; remove mean; no taper",
        "limitation": "Preview power spectrum; not a calibrated spectral density; masks affect spectrum.",
    }
