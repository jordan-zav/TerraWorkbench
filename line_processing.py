"""Numerical helpers for traverse/tie-line leveling."""

from __future__ import annotations

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
