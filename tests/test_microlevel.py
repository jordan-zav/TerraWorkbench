import numpy as np

from microlevel import microlevel_grid


def test_microlevel_removes_line_corrugation_without_changing_mean():
    rows, columns = 128, 96
    x = np.arange(columns)
    corrugation = np.tile(4.0 * np.sin(2.0 * np.pi * x / 8.0), (rows, 1))
    geology = np.tile(np.linspace(-10.0, 10.0, rows)[:, None], (1, columns))
    data = geology + corrugation
    corrected, correction = microlevel_grid(data, 25.0, 25.0, 0.0, 300.0, 2000.0)
    assert np.isclose(corrected.mean(), data.mean(), atol=1e-10)
    assert np.std(corrected - geology) < np.std(corrugation) * 0.2
    assert np.std(correction) > 1.0
