import csv

import numpy as np
import pytest

from terraworkbench_core.survey_map import build_survey_map
from terraworkbench_core.survey_store import SurveyStore


def survey(tmp_path, fields, rows, metadata=None):
    pytest.importorskip("pyarrow")
    pytest.importorskip("pyproj")
    pytest.importorskip("shapely")
    store = SurveyStore(tmp_path / "workspace", create=True)
    source = tmp_path / "survey.csv"
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)
    database = store.import_file(
        source, metadata={"crs": "EPSG:27700", **(metadata or {})}
    )
    return store, database


def test_parallel_traverses_and_perpendicular_ties(tmp_path):
    rows = [
        (e, n, f"L{i}", 2024)
        for i, e in enumerate((0, 100, 200), 1)
        for n in range(0, 401, 20)
    ]
    rows += [
        (e, n, f"T{i}", 2024)
        for i, n in enumerate((50, 300), 1)
        for e in range(-100, 301, 20)
    ]
    store, database = survey(tmp_path, ("easting", "northing", "line", "year"), rows)
    result = build_survey_map(store, database)
    assert result.summary["counts"] == {"traverse": 3, "tie": 2, "other": 0}
    assert result.summary["traverse_spacing_m"] == pytest.approx(100)
    assert result.summary["tie_spacing_m"] == pytest.approx(250)
    assert result.summary["total_km"] == pytest.approx(2)
    assert result.boundary.is_valid
    assert all(
        segment.type_source == "prefix" and segment.date_start == "2024"
        for segment in result.segments
    )


def test_metadata_overrides_prefix_and_fiducial_splits_gaps(tmp_path):
    rows = [
        (15, 0, "L01", 2),
        (1020, 0, "L01", 5),
        (0, 0, "L01", 1),
        (1010, 0, "L01", 4),
        (25, 0, "L01", 3),
        (2, 2, "L99", 1),
    ]
    metadata = {
        "LINE_SPACING": 20,
        "line_metadata": {"L01": {"kind": "tie", "date": "2014-11-01", "number": 81}},
    }
    store, database = survey(tmp_path, ("x", "y", "line", "fiducial"), rows, metadata)
    result = build_survey_map(store, database, max_gap_m=100)
    assert result.summary["line_ids"] == 2 and result.summary["mapped_lines"] == 1
    assert len(result.segments) == 2 and result.samples.num_rows == 6
    first, second = result.segments
    np.testing.assert_array_equal(first.xy[:, 0], [0, 15, 25])
    np.testing.assert_array_equal(second.xy[:, 0], [1010, 1020])
    assert first.type_source == "metadata" and first.kind == "tie"
    assert first.number == "81" and first.date_end == "2014-11-01"
    assert result.boundary.geom_type == "MultiPolygon"


def test_no_line_channel_and_single_sample(tmp_path):
    store, database = survey(
        tmp_path,
        ("longitude", "latitude", "value"),
        [(-2, 53, 8), ("", 53, 9)],
        {"crs": "EPSG:4326", "LINE_SPACING": 1000},
    )
    result = build_survey_map(store, database, sample_columns=("value",))
    assert not result.summary["has_line_channel"]
    assert result.summary["invalid_samples"] == 1
    assert not result.segments and result.samples["value"].to_pylist() == ["8"]
    assert result.boundary.area > 0
    assert result.summary["boundary_method"] == "concave_hull"
    assert result.summary["boundary_closing_m"] == 0


def test_time_orders_vertices_when_fiducial_is_incomplete(tmp_path):
    rows = [
        (400020, 200000, "L01", 3, "2025-04-01T10:02:00"),
        (400000, 200000, "L01", "", "2025-04-01T10:00:00"),
        (400010, 200000, "L01", 2, "2025-04-01T10:01:00"),
    ]
    store, database = survey(tmp_path, ("x", "y", "line", "fiducial", "time"), rows)
    segment, = build_survey_map(store, database).segments
    np.testing.assert_array_equal(segment.xy[:, 0], [400000, 400010, 400020])


def test_orientation_requires_coherent_parallel_and_tie_families(tmp_path):
    rows = [
        (e, n, label)
        for e, label in zip((0, 100, 200, 300), ("a", "b", "c", "d"))
        for n in range(0, 101, 10)
    ]
    rows += [
        (e, n, label)
        for n, label in ((25, "m"), (75, "n"))
        for e in range(-100, 401, 10)
    ]
    rows += [(e, e, "diagonal") for e in range(0, 100, 10)]
    store, database = survey(tmp_path, ("x", "y", "line"), rows)
    result = build_survey_map(store, database)
    assert result.summary["counts"] == {"traverse": 4, "tie": 2, "other": 1}
    assert all(
        segment.type_source == "direction"
        for segment in result.segments
        if segment.kind != "other"
    )


def test_invalid_sample_breaks_line_and_default_detects_outlier_step(tmp_path):
    rows = [(x, 0, "FL1-2") for x in [0, 10, 20, 30, 2000, 2010, 2020]]
    rows += [(x, 20, "FL2-1") for x in [0, 10, "", 30, 40]]
    store, database = survey(tmp_path, ("x", "y", "line_and_segment"), rows)
    result = build_survey_map(store, database)
    assert result.summary["segments"] == 4
    assert result.summary["invalid_samples"] == 1
    assert result.summary["counts"]["traverse"] == 2
    assert result.summary["total_km"] == pytest.approx(0.07)


def test_host_boundary_backend_needs_no_shapely_qgis_or_qt(tmp_path, monkeypatch):
    import builtins

    store, database = survey(
        tmp_path, ("x", "y", "line"), [(0, 0, "TL-X-1"), (10, 0, "TL-X-1")]
    )
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"shapely", "qgis", "PyQt5", "PyQt6"}:
            raise ImportError(f"Forbidden dependency: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    calls = []
    sentinel = object()

    def boundary(lines, samples, radius, factor):
        calls.append((lines, samples, radius, factor))
        return sentinel

    result = build_survey_map(store, database, boundary_builder=boundary)
    assert result.boundary is sentinel
    assert result.summary["counts"] == {"traverse": 0, "tie": 1, "other": 0}
    assert result.segments[0].type_source == "prefix"
    assert len(calls[0][0]) == 1 and calls[0][3] == 1.0
    assert calls[0][2].spacing_m is None
    assert calls[0][2].degenerate_buffer_m == 5.0


def test_spacing_and_boundary_preserve_two_differently_oriented_blocks(tmp_path):
    rows = [
        (x, y, f"FL{i}") for i, x in enumerate((0, 100, 200)) for y in range(0, 401, 20)
    ]
    rows += [
        (x, y, f"FL{i + 3}")
        for i, y in enumerate((0, 100, 200))
        for x in range(10000, 10401, 20)
    ]
    store, database = survey(tmp_path, ("x", "y", "line"), rows)
    result = build_survey_map(store, database)
    assert result.summary["traverse_spacing_m"] == pytest.approx(100)
    assert result.summary["traverse_azimuth_deg"] is None
    assert list(result.summary["line_spacing_m"].values()) == pytest.approx([100] * 6)
    assert result.boundary.geom_type == "MultiPolygon"
    assert len(result.boundary.geoms) == 2


def test_boundary_fills_small_hole_keeps_large_hole_and_removes_tiny_part():
    from shapely.geometry import Point
    from terraworkbench_core.survey_map import BoundaryPlan, _shapely_boundary

    small = np.array([(0, 0), (40, 0), (40, 40), (0, 40), (0, 0)])
    large = np.array([(300, 0), (500, 0), (500, 200), (300, 200), (300, 0)])
    tiny = np.array([(1000, 0), (1001, 0)])
    plan = BoundaryPlan(10, (5, 5, 5), 10, 2500, 100, 1, 5)
    boundary = _shapely_boundary(
        [small, large, tiny], np.concatenate([small, large]), plan, 1
    )
    assert boundary.is_valid and len(boundary.geoms) == 2
    assert boundary.contains(Point(20, 20))
    assert not boundary.contains(Point(400, 100))
    assert not boundary.intersects(Point(1000, 0))
    assert sum(len(poly.interiors) for poly in boundary.geoms) == 1


def test_boundary_without_spacing_uses_concave_sample_hull():
    from shapely.geometry import Point
    from terraworkbench_core.survey_map import BoundaryPlan, _shapely_boundary

    samples = np.array(
        [
            (x, y)
            for x in range(0, 101, 10)
            for y in range(0, 101, 10)
            if x <= 20 or y <= 20
        ]
    )
    plan = BoundaryPlan(None, (), 0, 0, 0, 1, 5)
    boundary = _shapely_boundary([], samples, plan, 1)
    assert boundary.is_valid and boundary.covers(Point(10, 80))
    assert not boundary.covers(Point(45, 45))


def test_spacing_excludes_sister_segments_and_crossing_chords():
    from terraworkbench_core.survey_map import _spacing

    tracks = {
        "FL1-1": np.array([(0, 0), (0, 1000)]),
        "FL1-2": np.array([(20, 0), (20, 1000)]),
        "FL2-1": np.array([(100, 0), (100, 1000)]),
        "FL3-1": np.array([(-50, 0), (50, 1000)]),
    }
    lines = {name: {"xy": points} for name, points in tracks.items()}
    classes = {name: ("traverse", "prefix") for name in tracks}
    _, _, local = _spacing(lines, classes, "traverse")
    assert local["FL1-1"] == pytest.approx(100)
    assert local["FL1-2"] == pytest.approx(80)
