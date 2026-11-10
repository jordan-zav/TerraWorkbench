"""Reduced field-format failures; public survey bytes stay outside the repo."""

import numpy as np
import pytest

from terraworkbench_core.radiometry import ternary_rgb
from terraworkbench_core.survey_text_import import inspect_text, parsed_rows


@pytest.mark.parametrize("shape", [(), (7,), (2, 4), (2, 3, 4)])
def test_normalized_ternary_accepts_channel_and_grid_shapes(shape):
    k = np.arange(np.prod(shape) or 1, dtype=float).reshape(shape)
    u, th = k * 2, k * 3
    actual = ternary_rgb(k, u, th, 0, 100, normalize=True)
    assert actual.shape == (3, *shape)
    if k.size > 1:
        valid = k > k.min()
        np.testing.assert_array_equal(actual[:, valid], 85.0)
        assert np.isnan(actual[:, ~valid]).all()
    else:
        assert np.isnan(actual).all()


def test_xyz_suggestions_import_all_lines_and_keep_projected_roles(tmp_path):
    path = tmp_path / "radiometry.xyz"
    path.write_text(
        "/ITM_X ITM_Y DATE LINE LONG LAT C_POT_DLU C_URA_DLU C_THO_DLU\n"
        "Line 9001\n"
        "543043.32 616936.81 20210826 9001.00 -8.8351 52.3011 1.23 .95 6.70\n"
        "543061.59 616874.31 20210826 9001.00 -8.8348 52.3006 1.24 .90 6.03\n"
        "Line 9002\n"
        "543079.65 616811.96 20210827 9002.00 -8.8345 52.3000 * .85 5.92\n"
    )
    options, _, _ = inspect_text(path)
    assert options.columns[0].name == "ITM_X"
    assert [c.name for c in options.columns if c.role == "x"] == ["ITM_X"]
    assert [c.name for c in options.columns if c.role == "y"] == ["ITM_Y"]
    records = list(parsed_rows(path, options))
    assert len(records) == 3
    assert records[-1][1][6] is None
    assert records[-1][1][3] == "9002.00"


def test_xyz_marker_detection_does_not_change_ordinary_slash_or_line_values(tmp_path):
    path = tmp_path / "ordinary.txt"
    path.write_text("name x y\nLinework 1 2\nTieback 3 4\n")
    options, _, _ = inspect_text(path)
    assert not any(p.strip() in ("Line", "Tie") for p in options.comments)
    assert len(list(parsed_rows(path, options))) == 2


def test_xyz_without_repeated_line_channel_does_not_discard_section_identity(tmp_path):
    path = tmp_path / "section_only.xyz"
    path.write_text("/X Y MAG\nLine 001\n1 2 3\nLine 002\n4 5 6\n")
    options, _, _ = inspect_text(path)
    assert not any(p.strip() in ("Line", "Tie") for p in options.comments)
