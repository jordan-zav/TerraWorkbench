import numpy as np

from line_processing import (
    evaluate_polynomial_correction,
    polynomial_residual_statistics,
    residual_statistics,
    robust_line_corrections,
    robust_polynomial_line_corrections,
)


def test_line_level_solution_reduces_crossover_rms_and_rejects_outlier():
    rows = [
        ("L1", "T1", 10.0),
        ("L2", "T1", -4.0),
        ("L1", "T2", 8.0),
        ("L2", "T2", -6.0),
        ("L1", "T1", 1000.0),
    ]
    corrections, keep = robust_line_corrections(rows, 4.5)
    stats = residual_statistics(rows, corrections, keep)
    assert keep.tolist() == [True, True, True, True, False]
    assert set(corrections) == {"L1", "L2", "T1", "T2"}
    assert stats["rms_after"] < 1e-8
    assert stats["rms_before"] > 5.0


def test_zero_mean_anchor():
    corrections, _ = robust_line_corrections([("L1", "T1", 5.0)])
    assert np.isclose(sum(corrections.values()), 0.0)


def test_polynomial_crossover_leveling_recovers_along_line_drift():
    positions = np.linspace(-1.0, 1.0, 7)
    rows = [
        ("flight", "tie", 5.0 + 3.0 * position, position, position)
        for position in positions
    ]
    corrections, keep = robust_polynomial_line_corrections(
        rows, order=1, damping=1e-12
    )
    stats = polynomial_residual_statistics(rows, corrections, keep)
    assert keep.all()
    assert stats["rms_after"] < 1e-8
    assert stats["rms_before"] > 5.0
    assert evaluate_polynomial_correction(corrections["flight"], 1.0) < 0.0
