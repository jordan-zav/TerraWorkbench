"""Explicit base-station, scalar TL and static vector norm calibration.

Physical models implemented independently; no MagComPy source is copied.
Norm calibration identifies intensity, not absolute vector orientation.
"""

import hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

MAX_ROWS = 2_000_000
MAX_CALIBRATION_ROWS = 200_000
SOURCE = "https://doi.org/10.1029/2021GC009745"


def _check(canceled):
    if canceled and canceled():
        raise InterruptedError("Magnetic compensation canceled.")


def _frame(frame, canceled=None, calibration=False):
    import pandas as pd

    _check(canceled)
    if not isinstance(frame, pd.DataFrame) or len(frame) > (
        MAX_CALIBRATION_ROWS if calibration else MAX_ROWS
    ):
        raise ValueError("Compensation requires a DataFrame within the row limit.")


def _array(frame, column):
    import pandas as pd

    if column not in frame:
        raise ValueError(f"Missing compensation column {column}.")
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _seconds(frame, column, unit):
    if unit not in ("s", "ms", "us"):
        raise ValueError("Time unit must be s, ms or us; use a common epoch.")
    return _array(frame, column) * {"s": 1.0, "ms": 0.001, "us": 0.000001}[unit]


def _limit(t, gap):
    if gap is not None:
        if not np.isfinite(gap) or gap <= 0:
            raise ValueError("max_gap_seconds must be positive and finite.")
        return float(gap)
    dt = np.diff(t)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    return 2 * float(np.median(dt)) if len(dt) else np.inf


def _runs(t, valid, gap):
    start = None
    for i in range(len(t)):
        good = bool(valid[i] and np.isfinite(t[i]))
        split = i and (
            not np.isfinite(t[i - 1]) or t[i] <= t[i - 1] or t[i] - t[i - 1] > gap
        )
        if start is not None and (not good or split):
            yield np.arange(start, i)
            start = None
        if good and start is None:
            start = i
    if start is not None:
        yield np.arange(start, len(t))


def _audit(frame, column, correction, operation, canceled=None):
    _check(canceled)
    names = (f"{column}__{operation}_original", f"{column}__{operation}_correction_nt")
    if any(name in frame for name in names):
        raise ValueError("Existing compensation audit columns would be overwritten.")
    out = frame.copy(deep=True)
    original = _array(frame, column)
    out[names[0]], out[names[1]], out[column] = (
        original,
        correction,
        original - correction,
    )
    finite = np.isfinite(correction) & np.isfinite(original)
    return out, {
        "operation": operation,
        "rows": len(frame),
        "corrected_rows": int(finite.sum()),
        "uncovered_rows": int((np.isfinite(original) & ~finite).sum()),
        "correction_rms_nt": float(np.sqrt(np.mean(correction[finite] ** 2)))
        if finite.any()
        else None,
        "original_column": names[0],
        "correction_column": names[1],
        "source": SOURCE,
    }


def correct_diurnal(
    frame,
    base_frame,
    *,
    magnetic_column,
    time_column,
    base_magnetic_column,
    base_time_column,
    time_unit="s",
    base_time_unit="s",
    reference_nt=None,
    max_gap_seconds=None,
    canceled=None,
):
    """Subtract base(t)-reference; outside coverage and outages become null."""
    _frame(frame, canceled)
    _frame(base_frame, canceled)
    t = _seconds(frame, time_column, time_unit)
    bt = _seconds(base_frame, base_time_column, base_time_unit)
    bv = _array(base_frame, base_magnetic_column)
    ft = bt[np.isfinite(bt)]
    if len(ft) < 2 or np.any(np.diff(ft) <= 0):
        raise ValueError(
            "Base timestamps must be strictly increasing with no duplicates."
        )
    valid = np.isfinite(bt) & np.isfinite(bv)
    if valid.sum() < 2:
        raise ValueError("Base station needs at least two finite samples.")
    reference = (
        float(np.median(bv[valid])) if reference_nt is None else float(reference_nt)
    )
    if not np.isfinite(reference):
        raise ValueError("Base reference must be finite.")
    gap = _limit(bt, max_gap_seconds)
    correction = np.full(len(frame), np.nan)
    segments = 0
    for ids in _runs(bt, valid, gap):
        _check(canceled)
        segments += 1
        selected = (
            t == bt[ids[0]]
            if len(ids) == 1
            else np.isfinite(t) & (t >= bt[ids[0]]) & (t <= bt[ids[-1]])
        )
        correction[selected] = np.interp(t[selected], bt[ids], bv[ids]) - reference
    out, report = _audit(frame, magnetic_column, correction, "diurnal", canceled)
    report.update(
        reference_nt=reference,
        base_segments=segments,
        max_gap_seconds=None if not np.isfinite(gap) else gap,
        time_unit=time_unit,
        base_time_unit=base_time_unit,
        uncovered_policy="null",
    )
    return out, report


def _vectors(frame, columns):
    if (
        not isinstance(columns, (list, tuple))
        or len(columns) != 3
        or len(set(columns)) != 3
    ):
        raise ValueError("Map three distinct body-frame vector columns in nT.")
    return np.column_stack([_array(frame, c) for c in columns])


def tolles_lawson_design(
    frame,
    *,
    vector_columns,
    time_column,
    time_unit="s",
    max_gap_seconds=None,
    field_scale_nt=50000.0,
    canceled=None,
):
    """18 terms: 3 permanent, 6 symmetric induced, 9 eddy-current terms.

    Induced/eddy terms use B/field_scale for conditioning. Derivatives use
    seconds and separate finite acquisition runs, without crossing outages.
    """
    _frame(frame, canceled)
    if not np.isfinite(field_scale_nt) or field_scale_nt <= 0:
        raise ValueError("field_scale_nt must be positive.")
    b = _vectors(frame, vector_columns)
    t = _seconds(frame, time_column, time_unit)
    norm = np.linalg.norm(b, axis=1)
    valid = np.isfinite(b).all(axis=1) & np.isfinite(norm) & (norm > 0)
    u, du = np.full_like(b, np.nan), np.full_like(b, np.nan)
    u[valid] = b[valid] / norm[valid, None]
    for ids in _runs(t, valid, _limit(t, max_gap_seconds)):
        _check(canceled)
        if len(ids) >= 3:
            du[ids] = np.gradient(u[ids], t[ids], axis=0, edge_order=2)
    induced = np.column_stack(
        [u[:, i] * u[:, j] for i, j in ((0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2))]
    )
    eddy = np.column_stack([u[:, i] * du[:, j] for i in range(3) for j in range(3)])
    return np.column_stack(
        [
            u,
            induced * (norm / field_scale_nt)[:, None],
            eddy * (norm / field_scale_nt)[:, None],
        ]
    )


def _reference(value, size):
    reference = np.asarray(value, dtype=float)
    if reference.ndim == 0:
        reference = np.full(size, float(reference))
    if (
        reference.shape != (size,)
        or not np.isfinite(reference).all()
        or np.any(reference <= 0)
    ):
        raise ValueError(
            "reference_field_nt must be a positive scalar or one value per calibration row."
        )
    return reference


def _confirmed(confirmed):
    if confirmed is not True:
        raise ValueError("Confirm an independent low-gradient calibration flight.")


def calibrate_tolles_lawson(
    calibration_frame,
    *,
    magnetic_column,
    vector_columns,
    time_column,
    reference_field_nt,
    low_gradient_confirmed,
    time_unit="s",
    ridge=1e-6,
    max_gap_seconds=None,
    canceled=None,
):
    _frame(calibration_frame, canceled, calibration=True)
    _confirmed(low_gradient_confirmed)
    if not np.isfinite(ridge) or ridge <= 0:
        raise ValueError("ridge must be positive and finite.")
    a = tolles_lawson_design(
        calibration_frame,
        vector_columns=vector_columns,
        time_column=time_column,
        time_unit=time_unit,
        max_gap_seconds=max_gap_seconds,
        canceled=canceled,
    )
    reference = _reference(reference_field_nt, len(a))
    y = _array(calibration_frame, magnetic_column) - reference
    valid = np.isfinite(a).all(axis=1) & np.isfinite(y)
    if valid.sum() < 60:
        raise ValueError(
            "TL calibration needs at least 60 finite samples in runs of three or more."
        )
    a, y = a[valid], y[valid]
    center = a.mean(axis=0)
    ac, yc = a - center, y - y.mean()
    scale = np.std(ac, axis=0)
    scale[scale < 1e-12] = 1.0
    z = ac / scale
    rank = int(np.linalg.matrix_rank(z))
    if rank < 8:
        raise ValueError("Insufficient calibration attitude excitation for TL.")
    _check(canceled)
    coef = (
        np.linalg.solve(z.T @ z + float(ridge) * len(z) * np.eye(18), z.T @ yc) / scale
    )
    residual = yc - ac @ coef
    return {
        "method": "tolles_lawson",
        "version": 1,
        "coefficients": coef.tolist(),
        "design_center": center.tolist(),
        "field_scale_nt": 50000.0,
        "ridge": float(ridge),
        "calibration_rows": len(y),
        "design_rank": rank,
        "time_unit": time_unit,
        "max_gap_seconds": max_gap_seconds,
        "mean_policy": "retain calibration mean",
        "calibration_residual_rms_nt": float(np.sqrt(np.mean(residual**2))),
        "calibration_raw_std_nt": float(np.std(y)),
        "reference_field_nt": float(np.mean(reference)),
        "source": SOURCE,
    }


def apply_tolles_lawson(
    frame,
    model,
    *,
    magnetic_column,
    vector_columns,
    time_column,
    time_unit="s",
    max_gap_seconds=None,
    canceled=None,
):
    if model.get("method") != "tolles_lawson" or model.get("version") != 1:
        raise ValueError("Unsupported TL model.")
    coef, center = (
        np.asarray(model["coefficients"], float),
        np.asarray(model["design_center"], float),
    )
    if (
        coef.shape != (18,)
        or center.shape != (18,)
        or not np.isfinite(coef).all()
        or not np.isfinite(center).all()
    ):
        raise ValueError("Invalid TL model coefficients.")
    a = tolles_lawson_design(
        frame,
        vector_columns=vector_columns,
        time_column=time_column,
        time_unit=time_unit,
        max_gap_seconds=max_gap_seconds
        if max_gap_seconds is not None
        else model.get("max_gap_seconds"),
        field_scale_nt=model["field_scale_nt"],
        canceled=canceled,
    )
    return _audit(
        frame, magnetic_column, (a - center) @ coef, "tolles_lawson", canceled
    )


def _matrix(p):
    return np.array(
        [
            [np.exp(p[3]), 0.0, 0.0],
            [p[6], np.exp(p[4]), 0.0],
            [p[7], p[8], np.exp(p[5])],
        ]
    )


def calibrate_vector(
    calibration_frame,
    *,
    vector_columns,
    reference_field_nt,
    low_gradient_confirmed,
    robust_scale_nt=5.0,
    canceled=None,
):
    """Fit hard-iron offset and positive-definite intensity metric (9 params)."""
    _frame(calibration_frame, canceled, calibration=True)
    _confirmed(low_gradient_confirmed)
    b = _vectors(calibration_frame, vector_columns)
    reference = _reference(reference_field_nt, len(b))
    valid = np.isfinite(b).all(axis=1)
    if valid.sum() < 60:
        raise ValueError("Vector calibration needs at least 60 finite samples.")
    b, reference = b[valid], reference[valid]
    field_scale = float(np.median(reference))
    points = b / field_scale
    centered = points - points.mean(axis=0)
    eig = np.linalg.eigvalsh(centered.T @ centered / len(centered))
    if eig[0] <= 0 or eig[0] / eig[-1] < 0.02:
        raise ValueError(
            "Vector calibration needs three-dimensional orientation coverage."
        )
    if not np.isfinite(robust_scale_nt) or robust_scale_nt <= 0:
        raise ValueError("robust_scale_nt must be positive.")

    def residual(p):
        _check(canceled)
        return (
            np.linalg.norm((points - p[:3]) @ _matrix(p).T, axis=1)
            - reference / field_scale
        )

    p = np.zeros(9)
    p[:3] = points.mean(axis=0)
    fit = least_squares(
        residual,
        p,
        loss="soft_l1",
        f_scale=robust_scale_nt / field_scale,
        max_nfev=500,
        bounds=([-3] * 9, [3] * 9),
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
    )
    if not fit.success or np.linalg.matrix_rank(fit.jac) < 9:
        raise ValueError(
            "Vector calibration did not converge to an identifiable norm model."
        )
    r = residual(fit.x) * field_scale
    return {
        "method": "vector_norm",
        "version": 1,
        "offset_nt": (fit.x[:3] * field_scale).tolist(),
        "matrix": _matrix(fit.x).tolist(),
        "calibration_rows": len(b),
        "reference_field_nt": float(reference.mean()),
        "calibration_residual_rms_nt": float(np.sqrt(np.mean(r**2))),
        "calibration_raw_std_nt": float(np.std(np.linalg.norm(b, axis=1))),
        "orientation_identified": False,
        "model": "static affine norm calibration",
        "source": SOURCE,
    }


def apply_vector_calibration(
    frame, model, *, magnetic_column, vector_columns, canceled=None
):
    _frame(frame, canceled)
    if model.get("method") != "vector_norm" or model.get("version") != 1:
        raise ValueError("Unsupported vector model.")
    offset, matrix = (
        np.asarray(model["offset_nt"], float),
        np.asarray(model["matrix"], float),
    )
    if (
        offset.shape != (3,)
        or matrix.shape != (3, 3)
        or not np.isfinite(offset).all()
        or not np.isfinite(matrix).all()
        or np.linalg.det(matrix) <= 0
    ):
        raise ValueError("Invalid vector calibration model.")
    b = _vectors(frame, vector_columns)
    corrected = (b - offset) @ matrix.T
    intensity = np.linalg.norm(corrected, axis=1)
    intensity[~np.isfinite(b).all(axis=1)] = np.nan
    out, report = _audit(
        frame,
        magnetic_column,
        _array(frame, magnetic_column) - intensity,
        "vector_norm",
        canceled,
    )
    for i, c in enumerate(vector_columns):
        name = f"{c}__calibrated"
        if name in out:
            raise ValueError("Existing calibrated vector columns would be overwritten.")
        out[name] = corrected[:, i]
    report["orientation_identified"] = False
    return out, report


def _read_source(path, canceled):
    import pandas as pd

    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("Calibration/base input missing or exceeds 512 MB.")

    def digest():
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                _check(canceled)
                h.update(chunk)
        return h.hexdigest()

    before = digest()
    with path.open("r", encoding="utf-8-sig") as handle:
        first = handle.readline()
        skip = 0
        if first.strip().lower().startswith("raw track"):
            skip = 1
            first = handle.readline()
            while first and not first.strip():
                skip += 1
                first = handle.readline()
    frame = pd.read_csv(
        path,
        sep="\t" if "\t" in first else None,
        engine="python",
        skiprows=skip,
        encoding="utf-8-sig",
        nrows=MAX_ROWS + 1,
    )
    if len(frame) > MAX_ROWS or digest() != before:
        raise ValueError(
            "Compensation source exceeds row limit or changed during reading."
        )
    return frame, {"path": str(path), "sha256": before}


def _apply_calibration(
    frame, calibration, options, magnetic_column, time_column, canceled
):
    method = options["method"]
    common = dict(
        vector_columns=options["vector_columns"],
        reference_field_nt=options["reference_field_nt"],
        low_gradient_confirmed=options.get("low_gradient_confirmed", False),
        canceled=canceled,
    )
    if method == "tolles_lawson":
        model = calibrate_tolles_lawson(
            calibration,
            magnetic_column=options.get("calibration_value_column", magnetic_column),
            time_column=options.get("calibration_time_column", time_column),
            time_unit=options.get(
                "calibration_time_unit", options.get("time_unit", "s")
            ),
            ridge=options.get("ridge", 1e-6),
            max_gap_seconds=options.get("max_gap_seconds"),
            **common,
        )
        out, step = apply_tolles_lawson(
            frame,
            model,
            magnetic_column=magnetic_column,
            vector_columns=options["vector_columns"],
            time_column=time_column,
            time_unit=options.get("time_unit", "s"),
            max_gap_seconds=options.get("max_gap_seconds"),
            canceled=canceled,
        )
    else:
        model = calibrate_vector(
            calibration, robust_scale_nt=options.get("robust_scale_nt", 5.0), **common
        )
        out, step = apply_vector_calibration(
            frame,
            model,
            magnetic_column=magnetic_column,
            vector_columns=options["vector_columns"],
            canceled=canceled,
        )
    step["model"] = model
    return out, step


def compensate_frame(
    frame,
    options,
    *,
    magnetic_column,
    time_column,
    sensor_column=None,
    canceled=None,
    stage_callback=None,
):
    """Apply independent calibration then diurnal correction with CSV/ASC mappings.

    Mapped sensor arrays use independent calibration models by default. Setting
    per_sensor=False applies one explicitly shared model. Acquisition order and
    duplicate DataFrame labels are preserved through positional assignment.
    """
    _frame(frame, canceled)
    options = dict(options or {})
    method = options.get("method", "none")
    out, report = frame.copy(deep=True), {"steps": [], "sources": []}
    if method not in ("none", "tolles_lawson", "vector"):
        raise ValueError("Compensation method must be none, tolles_lawson or vector.")
    if method != "none":
        options["method"] = method
        calibration, source = _read_source(options["calibration_path"], canceled)
        report["sources"].append(source)
        sensor_column = sensor_column or options.get("sensor_column")
        per_sensor = options.get("per_sensor", True)
        if not isinstance(per_sensor, bool):
            raise ValueError("per_sensor must be true or false.")
        if per_sensor and sensor_column:
            calibration_sensor = (
                options.get("calibration_sensor_column") or sensor_column
            )
            if sensor_column not in frame or calibration_sensor not in calibration:
                raise ValueError("Mapped survey/calibration sensor column is missing.")
            if (
                frame[sensor_column].isna().any()
                or calibration[calibration_sensor].isna().any()
            ):
                raise ValueError(
                    "Per-sensor compensation requires non-null sensor IDs."
                )
            report["sensor_mode"] = "per_sensor"
            for key, ids in frame.groupby(sensor_column, sort=False).indices.items():
                _check(canceled)
                selected = calibration[calibration_sensor].eq(key).to_numpy()
                if not selected.any():
                    raise ValueError(
                        f"Missing independent calibration for sensor {key}."
                    )
                cfg = dict(options)
                reference = np.asarray(cfg["reference_field_nt"])
                if reference.ndim:
                    if reference.shape != (len(calibration),):
                        raise ValueError(
                            "Calibration reference array has the wrong length."
                        )
                    cfg["reference_field_nt"] = reference[selected]
                group, step = _apply_calibration(
                    frame.iloc[ids],
                    calibration.iloc[np.flatnonzero(selected)],
                    cfg,
                    magnetic_column,
                    time_column,
                    canceled,
                )
                for column in group:
                    if column == magnetic_column or column not in frame:
                        values = (
                            out[column].to_numpy(copy=True)
                            if column in out
                            else np.full(len(out), np.nan)
                        )
                        values[ids] = group[column].to_numpy()
                        out[column] = values
                step["sensor_id"] = key.item() if hasattr(key, "item") else key
                report["steps"].append(step)
                if stage_callback is not None:
                    stage_callback(dict(step), out.copy(deep=True))
        else:
            if per_sensor and options.get("per_sensor") is True:
                raise ValueError(
                    "Per-sensor compensation needs an explicit sensor column."
                )
            report["sensor_mode"] = "shared_model"
            out, step = _apply_calibration(
                out, calibration, options, magnetic_column, time_column, canceled
            )
            report["steps"].append(step)
            if stage_callback is not None:
                stage_callback(dict(step), out.copy(deep=True))
    if options.get("diurnal"):
        cfg = dict(options["diurnal"])
        base, source = _read_source(cfg["path"], canceled)
        report["sources"].append(source)
        out, step = correct_diurnal(
            out,
            base,
            magnetic_column=magnetic_column,
            time_column=time_column,
            base_magnetic_column=cfg["value_column"],
            base_time_column=cfg["time_column"],
            time_unit=options.get("time_unit", "s"),
            base_time_unit=cfg.get("time_unit", "s"),
            reference_nt=cfg.get("reference_nt"),
            max_gap_seconds=cfg.get("max_gap_seconds"),
            canceled=canceled,
        )
        report["steps"].append(step)
        if stage_callback is not None:
            stage_callback(dict(step), out.copy(deep=True))
    _check(canceled)
    return out, report
