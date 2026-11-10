"""Prescribed electrical sources and reference networks, not fluid-flow inference.

Metres, S/m, amperes and VOLTS. Green functions assume constant isotropic
conductivity and full space or an insulating horizontal surface z=0. No
streaming-potential coefficient or hydraulic model is inferred from SP alone.
"""

import numpy as np

from ._array_contract import as_array


def _green(observation_m, reference_m, source_m, conductivity_s_m, space, max_elements):
    obs, ref, sources = [
        as_array(a, float) for a in (observation_m, reference_m, source_m)
    ]
    if (
        obs.ndim != 2
        or obs.shape[1] != 3
        or not len(obs)
        or sources.ndim != 2
        or sources.shape[1] != 3
        or not len(sources)
    ):
        raise ValueError("Nonempty (n,3) observation/source coordinates required")
    if ref.shape == (3,):
        ref = np.broadcast_to(ref, obs.shape)
    if ref.shape != obs.shape or not all(
        np.isfinite(a).all() for a in (obs, ref, sources)
    ):
        raise ValueError(
            "Finite coordinates and common/per-observation reference required"
        )
    if (
        not np.isfinite(conductivity_s_m)
        or conductivity_s_m <= 0
        or space not in ("full", "half")
    ):
        raise ValueError("Positive conductivity and full/half space required")
    if obs.shape[0] * sources.shape[0] + 4 * sources.shape[0] ** 2 > max_elements:
        raise ValueError("Dense prescribed-source kernel budget exceeded")
    if space == "half" and (
        np.any(obs[:, 2] > 0) or np.any(ref[:, 2] > 0) or np.any(sources[:, 2] > 0)
    ):
        raise ValueError("Insulating-surface half-space model requires z<=0")

    def inverse_distance(target, points):
        radius = np.linalg.norm(target[:, None, :] - points[None, :, :], axis=-1)
        if np.any(radius == 0):
            raise ValueError("Source/electrode coincidence is singular")
        return 1 / radius

    green = inverse_distance(obs, sources) - inverse_distance(ref, sources)
    if space == "half":
        images = sources.copy()
        images[:, 2] *= -1
        green += inverse_distance(obs, images) - inverse_distance(ref, images)
    return green / (4 * np.pi * conductivity_s_m)


def prescribed_source_potential(
    observation_m,
    reference_m,
    source_m,
    current_a,
    *,
    conductivity_s_m,
    space="half",
    max_elements=2_000_000,
):
    """V(observation)-V(reference) from neutral prescribed point-current sources.

    Current conservation sum(I)=0 is required. Surface image sources impose
    zero normal current at z=0. These equivalent point currents are not a
    calibrated electrokinetic, redox or ore-body interpretation.
    """
    kernel = _green(
        observation_m, reference_m, source_m, conductivity_s_m, space, max_elements
    )
    current = as_array(current_a, float)
    if (
        current.shape != (kernel.shape[1],)
        or not np.isfinite(current).all()
        or abs(current.sum()) > 1e-10 * max(np.sum(abs(current)), 1e-30)
    ):
        raise ValueError(
            "Finite current per source and conserved total current required"
        )
    return {
        "potential_difference_v": kernel @ current,
        "space": space,
        "conductivity_s_m": conductivity_s_m,
        "reference_convention": "V(observation)-V(reference)",
    }


def invert_source_currents(
    observation_m,
    reference_m,
    source_m,
    voltage_v,
    *,
    voltage_std_v,
    conductivity_s_m,
    beta,
    space="half",
    max_elements=2_000_000,
):
    """Regularized linear equivalent-current estimate with exact neutrality.

    Last source balances all others; identity L2 prior acts on the independent
    currents, so prior depends on that explicit parameterization. Supplied
    source geometry and conductivity are fixed. No unique hydraulic inference.
    """
    kernel = _green(
        observation_m, reference_m, source_m, conductivity_s_m, space, max_elements
    )
    data, std = as_array(voltage_v, float), as_array(voltage_std_v, float)
    if (
        kernel.shape[1] < 2
        or data.shape != (kernel.shape[0],)
        or std.shape != data.shape
        or not np.isfinite(data).all()
        or not np.isfinite(std).all()
        or np.any(std <= 0)
        or not np.isfinite(beta)
        or beta < 0
    ):
        raise ValueError(
            "Matching finite voltages/errors, >=2 sources and nonnegative beta required"
        )
    basis = np.vstack([np.eye(kernel.shape[1] - 1), -np.ones(kernel.shape[1] - 1)])
    weighted = (kernel @ basis) / std[:, None]
    design = np.vstack([weighted, np.sqrt(beta) * np.eye(basis.shape[1])])
    target = np.r_[data / std, np.zeros(basis.shape[1])]
    fit, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    if rank != basis.shape[1]:
        raise ValueError("Source currents not constrained by data/prior")
    current = basis @ fit
    predicted = kernel @ current
    covariance = basis @ np.linalg.inv(design.T @ design) @ basis.T
    return {
        "current_a": current,
        "predicted_voltage_v": predicted,
        "conditional_covariance_a2": covariance,
        "chi_squared": float(np.sum(((predicted - data) / std) ** 2)),
        "data_rank": int(np.linalg.matrix_rank(weighted)),
        "beta": beta,
        "warning": "Fixed homogeneous conductivity/source locations; equivalent sources are nonunique",
    }


def adjust_reference_network(
    pairs, voltage_v, *, voltage_std_v, node_count, anchors_v, max_elements=2_000_000
):
    """WLS electrode-node potentials from oriented differences V[a]-V[b].

    Anchors are exact known node potentials. Detect disconnected/underdetermined
    networks; retain loop residuals. This is network adjustment, not a fabricated
    time-dependent electrode-drift or telluric correction.
    """
    q, data, std = (
        as_array(pairs),
        as_array(voltage_v, float),
        as_array(voltage_std_v, float),
    )
    if (
        isinstance(node_count, bool)
        or not isinstance(node_count, (int, np.integer))
        or node_count < 2
    ):
        raise ValueError("node_count must be an integer >=2")
    if (
        q.ndim != 2
        or q.shape[1] != 2
        or q.dtype.kind not in "iu"
        or not len(q)
        or np.any(q < 0)
        or np.any(q >= node_count)
        or np.any(q[:, 0] == q[:, 1])
    ):
        raise ValueError("Integer oriented electrode pairs required")
    if (
        data.shape != (len(q),)
        or std.shape != data.shape
        or not np.isfinite(data).all()
        or not np.isfinite(std).all()
        or np.any(std <= 0)
    ):
        raise ValueError(
            "Finite matching voltage differences and positive errors required"
        )
    if not anchors_v or any(
        not isinstance(k, (int, np.integer))
        or not 0 <= k < node_count
        or not np.isfinite(v)
        for k, v in anchors_v.items()
    ):
        raise ValueError("Finite exact node-potential anchors required")
    unknown = [i for i in range(node_count) if i not in anchors_v]
    if not unknown or len(q) * len(unknown) + 4 * len(unknown) ** 2 > max_elements:
        raise ValueError("Network must have unknown nodes within dense budget")
    index = {node: col for col, node in enumerate(unknown)}
    design = np.zeros((len(q), len(unknown)))
    target = data.copy()
    for row, (a, b) in enumerate(q):
        for node, sign in ((a, 1), (b, -1)):
            if node in anchors_v:
                target[row] -= sign * anchors_v[node]
            else:
                design[row, index[node]] = sign
    weighted = design / std[:, None]
    model, _, rank, _ = np.linalg.lstsq(weighted, target / std, rcond=None)
    if rank != len(unknown):
        raise ValueError("Disconnected or unanchored potential network")
    values = np.array(
        [anchors_v[i] if i in anchors_v else model[index[i]] for i in range(node_count)]
    )
    residual = values[q[:, 0]] - values[q[:, 1]] - data
    return {
        "node_potential_v": values,
        "residual_v": residual,
        "conditional_unknown_covariance_v2": np.linalg.inv(weighted.T @ weighted),
        "unknown_nodes": np.array(unknown),
        "chi_squared": float(np.sum((residual / std) ** 2)),
        "degrees_of_freedom": len(q) - rank,
        "anchors_are_exact": True,
    }
