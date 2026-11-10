"""Electrical survey geometry, reciprocal QC and IP/SIP primitives.

No Qt or external engine. Electrode coordinates in metres, I in A, V in V,
rho in ohm m. Geometric factors assume a homogeneous planar half space or
homogeneous full space, not a topographic correction or an ERT inversion.
"""

import numpy as np

from ._array_contract import as_array


def validate_abmn(electrodes, abmn, *, space="half", plane_tolerance_m=1e-6):
    """Validate an (n, 4) integer electrode-index table; -1 means remote B/N.

    All real electrodes must be distinct within each quadrupole. In half
    space all used finite electrodes must lie on the same horizontal plane.
    """
    xyz = as_array(electrodes, float)
    raw = as_array(abmn)
    if (
        xyz.ndim != 2
        or xyz.shape[1] != 3
        or xyz.shape[0] < 2
        or not np.isfinite(xyz).all()
    ):
        raise ValueError("electrodes must be finite (n, 3) metre coordinates")
    if (
        raw.ndim != 2
        or raw.shape[1] != 4
        or raw.shape[0] < 1
        or raw.dtype.kind not in "iu"
    ):
        raise ValueError("abmn must be a nonempty integer (n, 4) table")
    q = raw.astype(np.int64, copy=True)
    if np.any(q < -1) or np.any(q >= len(xyz)) or np.any(q[:, [0, 2]] < 0):
        raise ValueError("Only B and N may be remote (-1); invalid electrode index")
    if space not in ("half", "full"):
        raise ValueError("space must be half or full")
    for left in range(4):
        for right in range(left + 1, 4):
            if np.any((q[:, left] == q[:, right]) & (q[:, left] >= 0)):
                raise ValueError("Finite electrodes cannot repeat within a quadrupole")
    if not np.isfinite(plane_tolerance_m) or plane_tolerance_m < 0:
        raise ValueError("Invalid plane tolerance")
    used = q[q >= 0]
    if space == "half" and np.ptp(xyz[used, 2]) > plane_tolerance_m:
        raise ValueError(
            "Half-space geometry requires a common horizontal electrode plane"
        )
    return xyz.copy(), q


def geometric_factor(electrodes, abmn, *, space="half"):
    """Signed K = 2*pi/(1/AM-1/BM-1/AN+1/BN); full space uses 4*pi."""
    xyz, q = validate_abmn(electrodes, abmn, space=space)
    terms = []
    for i, j in ((0, 2), (1, 2), (0, 3), (1, 3)):
        real = (q[:, i] >= 0) & (q[:, j] >= 0)
        inv = np.zeros(len(q))
        distances = np.linalg.norm(xyz[q[real, i]] - xyz[q[real, j]], axis=1)
        if np.any(distances == 0):
            raise ValueError("Coincident electrode positions")
        inv[real] = 1 / distances
        terms.append(inv)
    denominator = terms[0] - terms[1] - terms[2] + terms[3]
    scale = sum(abs(term) for term in terms)
    if np.any(abs(denominator) <= 1e-12 * scale):
        raise ValueError("Degenerate geometric factor")
    return (2 if space == "half" else 4) * np.pi / denominator


def apparent_resistivity(electrodes, abmn, voltage_v, current_a, *, space="half"):
    """Preserve polarity; flag negative apparent rho instead of taking abs."""
    factor = geometric_factor(electrodes, abmn, space=space)
    v, i = np.broadcast_arrays(as_array(voltage_v, float), as_array(current_a, float))
    if (
        v.shape not in ((), factor.shape)
        or not np.isfinite(v).all()
        or not np.isfinite(i).all()
        or np.any(i == 0)
    ):
        raise ValueError(
            "Finite voltage/current arrays matching abmn; current cannot be zero"
        )
    rho = factor * v / i
    return {
        "rho_a_ohm_m": rho,
        "resistance_ohm": v / i,
        "geometric_factor_m": factor,
        "negative_rho": rho < 0,
        "space": space,
        "voltage_convention": "V(M)-V(N), current A to B",
    }


def reciprocal_errors(abmn, resistance_ohm):
    """O(n) reciprocal grouping with polarity correction and repeat counts.

    Swapping A/B or M/N flips resistance. Repeats in each orientation are
    averaged first; error = 200*abs(Rf-Rr)/(abs(Rf)+abs(Rr)). Same-orientation
    repeats alone are not reciprocals. Unpaired/zero pairs return NaN.
    """
    q = as_array(abmn)
    r = as_array(resistance_ohm, float)
    if (
        q.ndim != 2
        or q.shape[1] != 4
        or q.dtype.kind not in "iu"
        or r.shape != (len(q),)
        or not np.isfinite(r).all()
    ):
        raise ValueError("Integer abmn and finite matching resistance are required")
    if np.any(q < -1) or np.any(q[:, [0, 2]] < 0):
        raise ValueError("Invalid electrode indices")
    groups = {}
    for row, value in zip(q, r):
        a, b, m, n = map(int, row)
        if a == b or m == n or set((a, b)) & set((m, n)) - {-1}:
            raise ValueError("Invalid quadrupole")
        tx, rx = tuple(sorted((a, b))), tuple(sorted((m, n)))
        sign = (1 if a < b else -1) * (1 if m < n else -1)
        groups.setdefault((tx, rx), []).append(sign * value)
    rows, errors, repeat_counts = [], [], []
    for key, values in groups.items():
        reverse = (key[1], key[0])
        if reverse in groups and key < reverse:
            rf, rr = float(np.mean(values)), float(np.mean(groups[reverse]))
            denominator = abs(rf) + abs(rr)
            rows.append((*key[0], *key[1]))
            errors.append(200 * abs(rf - rr) / denominator if denominator else np.nan)
            repeat_counts.append((len(values), len(groups[reverse])))
    return {
        "abmn": as_array(rows, dtype=int).reshape(-1, 4),
        "reciprocal_error_percent": np.array(errors),
        "repeat_counts": as_array(repeat_counts, dtype=int).reshape(-1, 2),
        "paired_groups": len(rows),
        "unpaired_groups": len(groups) - 2 * len(rows),
    }


def integrated_chargeability(times_s, decay_v, primary_v, *, gate_s):
    """Trapezoidal time-average decay/primary, mV/V, with exact gate edges.

    Piecewise linear interpolation at gate boundaries; no extrapolation.
    This is normalized average chargeability, NOT an unnormalized ms integral.
    Last axis is time. Sign is preserved, primary voltage must be nonzero.
    """
    t, v = as_array(times_s, float), as_array(decay_v, float)
    gate = as_array(gate_s, float)
    if (
        t.ndim != 1
        or len(t) < 2
        or not np.isfinite(t).all()
        or np.any(t < 0)
        or np.any(np.diff(t) <= 0)
        or v.ndim < 1
        or v.shape[-1] != len(t)
        or not np.isfinite(v).all()
        or gate.shape != (2,)
        or not np.isfinite(gate).all()
        or not t[0] <= gate[0] < gate[1] <= t[-1]
    ):
        raise ValueError(
            "Finite increasing nonnegative times, matching decay and contained gate required"
        )
    primary = as_array(primary_v, float)
    if (
        primary.shape not in ((), v.shape[:-1])
        or not np.isfinite(primary).all()
        or np.any(primary == 0)
    ):
        raise ValueError("Primary voltage must be nonzero and match trace dimensions")
    inside = (t > gate[0]) & (t < gate[1])
    nodes = np.r_[gate[0], t[inside], gate[1]]
    flat = v.reshape(-1, len(t))
    samples = np.array([np.interp(nodes, t, trace) for trace in flat])
    # np.trapz remains available across the supported NumPy 1.x/2.x range.
    area = np.sum((samples[:, 1:] + samples[:, :-1]) * np.diff(nodes) / 2, axis=1)
    mean = area.reshape(v.shape[:-1]) / (gate[1] - gate[0])
    return 1000 * mean / primary


def cole_cole_resistivity(frequency_hz, rho_zero, chargeability, tau_s, exponent):
    """Pelton resistivity, exp(+i*omega*t): rho0*(1-m+m/(1+(i*w*tau)**c)).

    Low-frequency rho0; high-frequency rho0*(1-m). Negative imaginary part
    for passive polarization under this convention. No conductivity-model
    parameter conversion is implied.
    """
    f = as_array(frequency_hz, float)
    params = as_array([rho_zero, chargeability, tau_s, exponent], float)
    if (
        not np.isfinite(f).all()
        or np.any(f < 0)
        or not np.isfinite(params).all()
        or rho_zero <= 0
        or not 0 <= chargeability < 1
        or tau_s <= 0
        or not 0 < exponent <= 1
    ):
        raise ValueError("Require f>=0, rho0>0, 0<=m<1, tau>0 and 0<c<=1")
    return rho_zero * (
        1 - chargeability + chargeability / (1 + (2j * np.pi * f * tau_s) ** exponent)
    )
