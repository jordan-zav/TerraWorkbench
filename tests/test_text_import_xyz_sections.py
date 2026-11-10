"""Reduced sectioned field-export failures; no original survey records."""

import pytest
from terraworkbench_core.survey_text_import import inspect_text, parsed_rows


@pytest.mark.parametrize("marker", ["Line", "Tie", "Tie_line", "TieLine", "TIE_LINE"])
@pytest.mark.parametrize("slash", ["/", "/ "])
@pytest.mark.parametrize("space", [" ", "\t"])
def test_separate_slash_header_tie_markers_and_projected_roles(
    tmp_path, marker, slash, space
):
    path = tmp_path / "example.xyz"
    path.write_text(
        "/ Example survey\n"
        + slash
        + "SECOND LINE LAT LONG UTMXNAD83 UTMYNAD83 VALUE\n"
        + marker
        + space
        + "001\n"
        + "1 001 54 -123 450000 6000000 2.5\n"
        + "2 001 54 -123 450100 6000100 3.5\n"
        + marker
        + space
        + "002\n"
        + "3 002 54 -123 450200 6000200 *\n"
    )
    options, _, _ = inspect_text(path)
    assert options.header_row == 2 and options.data_row == 4
    assert [c.name for c in options.columns] == [
        "SECOND",
        "LINE",
        "LAT",
        "LONG",
        "UTMXNAD83",
        "UTMYNAD83",
        "VALUE",
    ]
    assert [c.name for c in options.columns if c.role == "x"] == ["UTMXNAD83"]
    assert [c.name for c in options.columns if c.role == "y"] == ["UTMYNAD83"]
    rows = list(parsed_rows(path, options))
    assert len(rows) == 3 and rows[-1][1][1] == "002" and rows[-1][1][-1] is None


def test_explicit_xy_preferred_to_additional_latitude_longitude(tmp_path):
    path = tmp_path / "points.csv"
    path.write_text(
        "Latitude,Longitude,x,y,signal\n54,-123,450000,6000000,5\n54,-123,450100,6000100,6\n"
    )
    options, _, _ = inspect_text(path)
    assert [c.name for c in options.columns if c.role == "x"] == ["x"]
    assert [c.name for c in options.columns if c.role == "y"] == ["y"]
