import numpy as np

from line_processing import residual_statistics, robust_line_corrections


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
