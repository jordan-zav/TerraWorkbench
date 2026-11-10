"""Known-geometry 3-D property estimation with an optional Harmonica forward.

No free vertex/voxel inversion. SI density contrasts and physical magnetization
vectors, signed GLS, independent known errors, conditional full covariance.
"""

import numpy as np

from ._array_contract import as_array
from ._calibration import gaussian_calibration, integer_budget


def _domain(coordinates, prisms, max_interactions, max_elements, columns):
    integer_budget(max_interactions, "max_interactions")
    integer_budget(max_elements, "max_elements")
    xyz, bodies = as_array(coordinates, float), as_array(prisms, float)
    if (
        xyz.ndim != 2
        or xyz.shape[1] != 3
        or not len(xyz)
        or bodies.ndim != 2
        or bodies.shape[1] != 6
        or not 1 <= len(bodies) <= 128
        or not np.isfinite(xyz).all()
        or not np.isfinite(bodies).all()
        or np.any(bodies[:, 0::2] >= bodies[:, 1::2])
    ):
        raise ValueError(
            "Finite ENU observations and positive-volume west/east/south/north/bottom/top prisms required"
        )
    if len(xyz) * len(bodies) * columns > max_interactions:
        raise ValueError("Prism fitting interaction budget exceeded")
    if (
        len(xyz) * columns * (columns * len(bodies) + 3)
        + 4 * (columns * len(bodies) + 3) ** 2
        > max_elements
    ):
        raise ValueError("Prism fitting design/covariance element budget exceeded")
    for p in bodies:
        inside = np.all((xyz >= p[0::2]) & (xyz <= p[1::2]), axis=1)
        if np.any(inside):
            raise ValueError("Observations must be outside every source prism")
    return xyz, bodies


def _fit(design, observed, std, maximum_condition):
    if (
        observed.shape != design.shape[:2]
        or std.shape != observed.shape
        or not np.isfinite(observed).all()
        or not np.isfinite(std).all()
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Aligned finite observations and independent positive errors required"
        )
    if observed.size < design.shape[-1]:
        raise ValueError("Not enough data to separate the supplied prism properties")
    covariance = np.zeros((len(observed), observed.shape[1], observed.shape[1]))
    index = np.arange(observed.shape[1])
    covariance[:, index, index] = std**2
    model, cov, diagnostics = gaussian_calibration(
        design, observed, covariance, maximum_condition=maximum_condition
    )
    predicted = np.einsum("nkp,p->nk", design, model)
    return model, cov, predicted, diagnostics


def fit_prism_density(
    coordinates_enu_m,
    prisms_m,
    observed_mgal,
    data_std_mgal,
    *,
    gravity_component="up",
    fit_offset=False,
    maximum_condition=1e8,
    max_interactions=20_000_000,
    max_elements=2_000_000,
    canceled=None,
):
    """Signed density kg/m3 per fixed prism, optional constant mGal background.

    Forward uses Harmonica, whose g_z convention is downward. The API explicitly
    converts it to gravity_component up/down. Noise is independent absolute
    standard deviation; covariance excludes geometric/model uncertainty.
    """
    if gravity_component not in ("up", "down") or type(fit_offset) is not bool:
        raise ValueError("Choose gravity_component up/down and boolean fit_offset")
    xyz, bodies = _domain(
        coordinates_enu_m, prisms_m, max_interactions, max_elements, 1
    )
    if canceled is not None and canceled():
        raise InterruptedError("Prism density fit canceled")
    import harmonica as hm

    response = []
    for body in bodies:
        if canceled is not None and canceled():
            raise InterruptedError("Prism density fit canceled")
        column = hm.prism_gravity(
            tuple(xyz.T), body, [1.0], field="g_z", parallel=False
        )
        response.append((-1.0 if gravity_component == "up" else 1.0) * column)
    if fit_offset:
        response.append(np.ones(len(xyz)))
    design = np.column_stack(response)[:, None, :]
    observed, std = as_array(observed_mgal, float), as_array(data_std_mgal, float)
    if observed.ndim != 1 or std.ndim != 1:
        raise ValueError("Density observations and errors must be vectors")
    model, cov, predicted, diagnostics = _fit(
        design, observed[:, None], std[:, None], maximum_condition
    )
    if canceled is not None and canceled():
        raise InterruptedError("Prism density fit canceled")
    return dict(
        density_kg_m3=model[: len(bodies)],
        parameter_covariance=cov,
        offset_mgal=float(model[-1]) if fit_offset else 0.0,
        predicted_mgal=predicted[:, 0],
        residual_mgal=observed - predicted[:, 0],
        diagnostics=diagnostics,
        parameter_order=[f"density_kg_m3[{i}]" for i in range(len(bodies))]
        + (["offset_mgal"] if fit_offset else []),
        scope="Fixed 3D geometry; signed independent-known-error Gaussian property fit; no shape or geological uniqueness claim",
    )


def fit_prism_magnetization(
    coordinates_enu_m,
    prisms_m,
    observed_nt,
    data_std_nt,
    *,
    component="total",
    inclination=None,
    declination=None,
    fit_offset=False,
    maximum_condition=1e8,
    max_interactions=20_000_000,
    max_elements=2_000_000,
    canceled=None,
):
    """Physical ENU magnetization A/m per fixed prism, full coefficient covariance.

    Vector observations/errors have shape (n,3), interleaved ENU per record.
    Total uses shape (n,) and small-anomaly projection along explicit inducing
    I/D, degrees clockwise from grid north and positive-down inclination.
    It does NOT invert the exact magnetic vector norm. No field amplitude or
    susceptibility-to-magnetization conversion is inferred. Background offsets
    are optional: three for vector, one for projected total.
    """
    if component not in ("vector", "total") or type(fit_offset) is not bool:
        raise ValueError("Choose vector/total and boolean fit_offset")
    xyz, bodies = _domain(
        coordinates_enu_m, prisms_m, max_interactions, max_elements, 3
    )
    if component == "total":
        if (
            inclination is None
            or declination is None
            or not np.isfinite([inclination, declination]).all()
            or not -90 <= inclination <= 90
        ):
            raise ValueError(
                "Total projection requires finite inclination [-90,90] and declination"
            )
        inc, dec = np.deg2rad([inclination, declination])
        direction = np.array(
            [np.cos(inc) * np.sin(dec), np.cos(inc) * np.cos(dec), -np.sin(inc)]
        )
    if canceled is not None and canceled():
        raise InterruptedError("Prism magnetization fit canceled")
    import harmonica as hm

    columns = []
    for body in bodies:
        for axis in range(3):
            if canceled is not None and canceled():
                raise InterruptedError("Prism magnetization fit canceled")
            unit = np.eye(3)[axis]
            field = np.asarray(
                hm.prism_magnetic(
                    tuple(xyz.T), body, tuple(unit[:, None]), field="b", parallel=False
                )
            ).T
            columns.append(
                field if component == "vector" else (field @ direction)[:, None]
            )
    design = np.stack(columns, axis=-1)
    count = 3 if component == "vector" else 1
    if fit_offset:
        offsets = np.broadcast_to(np.eye(count), (len(xyz), count, count))
        design = np.concatenate([design, offsets], axis=-1)
    observed, std = as_array(observed_nt, float), as_array(data_std_nt, float)
    expected = (len(xyz), 3) if component == "vector" else (len(xyz),)
    if observed.shape != expected or std.shape != expected:
        raise ValueError(
            "Observed data and errors must match vector (n,3) or total (n,)"
        )
    data = observed if component == "vector" else observed[:, None]
    noise = std if component == "vector" else std[:, None]
    model, cov, predicted, diagnostics = _fit(design, data, noise, maximum_condition)
    if canceled is not None and canceled():
        raise InterruptedError("Prism magnetization fit canceled")
    vector = model[: 3 * len(bodies)].reshape(-1, 3)
    return dict(
        magnetization_a_m=vector,
        amplitude_a_m=np.linalg.norm(vector, axis=1),
        parameter_covariance=cov,
        offset_nt=model[3 * len(bodies) :] if fit_offset else np.zeros(count),
        predicted_nt=predicted if component == "vector" else predicted[:, 0],
        residual_nt=observed
        - (predicted if component == "vector" else predicted[:, 0]),
        diagnostics=diagnostics,
        parameter_order=[
            f"magnetization_{axis}_a_m[{i}]"
            for i in range(len(bodies))
            for axis in ("east", "north", "up")
        ]
        + ([f"offset_{i}_nt" for i in range(count)] if fit_offset else []),
        scope="Known fixed prism geometry and independent absolute Gaussian errors; covariance excludes geometry, calibration and inducing-direction uncertainty",
    )
