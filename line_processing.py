"""Numerical helpers for traverse/tie-line leveling."""

from __future__ import annotations

import math
import numpy as np


def robust_line_corrections(crossovers, outlier_sigma=4.5):
    """Solve constant line corrections from ``(traverse, tie, residual)`` rows."""
    rows = list(crossovers)
    if not rows:
        return {}, np.zeros(0, dtype=bool)
    residuals = np.asarray([float(row[2]) for row in rows], dtype=float)
    median = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - median)))
    keep = np.ones(residuals.size, dtype=bool)
    if mad > 0.0 and outlier_sigma > 0.0:
        keep = np.abs(residuals - median) <= outlier_sigma * 1.4826 * mad
    accepted = [row for row, accepted_row in zip(rows, keep) if accepted_row]
    if not accepted:
        return {}, keep
    names = sorted(
        {str(row[0]) for row in accepted} | {str(row[1]) for row in accepted}
    )
    indices = {name: index for index, name in enumerate(names)}
    matrix = np.zeros((len(accepted) + 1, len(names)), dtype=float)
    target = np.zeros(len(accepted) + 1, dtype=float)
    for row_index, (traverse, tie, residual) in enumerate(accepted):
        matrix[row_index, indices[str(traverse)]] = 1.0
        matrix[row_index, indices[str(tie)]] = -1.0
        target[row_index] = -float(residual)
    # Zero-mean anchor removes the constant null space without privileging one line.
    matrix[-1, :] = 1.0
    solution, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    return {name: float(solution[index]) for name, index in indices.items()}, keep


def residual_statistics(crossovers, corrections, keep=None):
    rows = list(crossovers)
    if not rows:
        return {"count": 0, "rms_before": None, "rms_after": None}
    if keep is None:
        keep = np.ones(len(rows), dtype=bool)
    before = []
    after = []
    for accepted, (traverse, tie, residual) in zip(keep, rows):
        if not accepted:
            continue
        value = float(residual)
        before.append(value)
        after.append(
            value + corrections.get(str(traverse), 0.0) - corrections.get(str(tie), 0.0)
        )
    if not before:
        return {"count": 0, "rms_before": None, "rms_after": None}
    before = np.asarray(before)
    after = np.asarray(after)
    return {
        "count": int(before.size),
        "rms_before": float(np.sqrt(np.mean(before**2))),
        "rms_after": float(np.sqrt(np.mean(after**2))),
        "median_after": float(np.median(after)),
    }


def evaluate_polynomial_correction(coefficients, position):
    """Evaluate constant/linear/quadratic line corrections on ``[-1, 1]``."""
    coefficients = np.asarray(coefficients, dtype=float)
    position = np.asarray(position, dtype=float)
    return sum(value * position**degree for degree, value in enumerate(coefficients))


def robust_polynomial_line_corrections(
    crossovers,
    order=1,
    outlier_sigma=4.5,
    damping=0.01,
    maximum_iterations=8,
):
    """Solve robust per-line polynomial corrections at crossover positions.

    Rows are ``(line_a, line_b, residual, position_a, position_b)`` with
    normalized positions in ``[-1, 1]``. Constant terms use a zero-mean anchor;
    higher-order coefficients are damped so sparse crossover networks cannot
    create unconstrained end-of-line swings.
    """
    rows = list(crossovers)
    order = int(order)
    if order < 0 or order > 2:
        raise ValueError("polynomial correction order must be between 0 and 2")
    if not rows:
        return {}, np.zeros(0, dtype=bool)
    names = sorted({str(row[0]) for row in rows} | {str(row[1]) for row in rows})
    name_index = {name: index for index, name in enumerate(names)}
    width = order + 1
    residuals = np.asarray([float(row[2]) for row in rows], dtype=float)
    median = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - median)))
    keep = np.isfinite(residuals)
    if mad > 0.0 and outlier_sigma > 0.0:
        keep &= np.abs(residuals - median) <= outlier_sigma * 1.4826 * mad

    solution = np.zeros(len(names) * width, dtype=float)
    for _iteration in range(max(1, int(maximum_iterations))):
        accepted = np.flatnonzero(keep)
        if accepted.size == 0:
            return {}, keep
        data_matrix = np.zeros((accepted.size, solution.size), dtype=float)
        target = np.empty(accepted.size, dtype=float)
        for matrix_row, row_index in enumerate(accepted):
            line_a, line_b, residual, position_a, position_b = rows[row_index]
            basis_a = np.asarray(
                [float(position_a) ** degree for degree in range(width)]
            )
            basis_b = np.asarray(
                [float(position_b) ** degree for degree in range(width)]
            )
            start_a = name_index[str(line_a)] * width
            start_b = name_index[str(line_b)] * width
            data_matrix[matrix_row, start_a : start_a + width] = basis_a
            data_matrix[matrix_row, start_b : start_b + width] = -basis_b
            target[matrix_row] = -float(residual)

        constraints = []
        constraint_target = []
        anchor = np.zeros(solution.size, dtype=float)
        anchor[0::width] = 1.0
        constraints.append(anchor)
        constraint_target.append(0.0)
        if order > 0 and damping > 0.0:
            scale = math.sqrt(float(damping))
            for line_index in range(len(names)):
                for degree in range(1, width):
                    row = np.zeros(solution.size, dtype=float)
                    row[line_index * width + degree] = scale * degree
                    constraints.append(row)
                    constraint_target.append(0.0)
        matrix = np.vstack([data_matrix, np.asarray(constraints)])
        rhs = np.r_[target, constraint_target]
        solution, *_ = np.linalg.lstsq(matrix, rhs, rcond=None)

        post = np.full(len(rows), np.nan, dtype=float)
        for row_index, (line_a, line_b, residual, position_a, position_b) in enumerate(rows):
            start_a = name_index[str(line_a)] * width
            start_b = name_index[str(line_b)] * width
            post[row_index] = float(residual) + float(
                evaluate_polynomial_correction(
                    solution[start_a : start_a + width], position_a
                )
                - evaluate_polynomial_correction(
                    solution[start_b : start_b + width], position_b
                )
            )
        accepted_post = post[keep & np.isfinite(post)]
        if accepted_post.size < 3 or outlier_sigma <= 0.0:
            break
        post_median = float(np.median(accepted_post))
        post_mad = float(np.median(np.abs(accepted_post - post_median)))
        if post_mad <= np.finfo(float).eps:
            break
        updated = keep & (
            np.abs(post - post_median) <= outlier_sigma * 1.4826 * post_mad
        )
        if np.array_equal(updated, keep):
            break
        keep = updated
    return {
        name: solution[index * width : (index + 1) * width].copy()
        for name, index in name_index.items()
    }, keep


def polynomial_residual_statistics(crossovers, corrections, keep=None):
    """Return crossover RMS before/after polynomial line correction."""
    rows = list(crossovers)
    if keep is None:
        keep = np.ones(len(rows), dtype=bool)
    before, after = [], []
    for accepted, (line_a, line_b, residual, position_a, position_b) in zip(
        keep, rows
    ):
        if not accepted:
            continue
        value = float(residual)
        before.append(value)
        after.append(
            value
            + float(evaluate_polynomial_correction(corrections[str(line_a)], position_a))
            - float(evaluate_polynomial_correction(corrections[str(line_b)], position_b))
        )
    if not before:
        return {"count": 0, "rms_before": None, "rms_after": None}
    before = np.asarray(before)
    after = np.asarray(after)
    return {
        "count": int(before.size),
        "rms_before": float(np.sqrt(np.mean(before**2))),
        "rms_after": float(np.sqrt(np.mean(after**2))),
        "median_after": float(np.median(after)),
    }
