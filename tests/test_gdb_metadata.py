"""Geometry protocols and unknown metadata never require GX or a licence."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np

from terraworkbench_core.gdb_archive import encode_metadata


def test_geometry_protocols_include_coordinates_and_reference_system():
    cs = SimpleNamespace(name="UTM", esri_wkt="PROJCRS[test]")
    values = [SimpleNamespace(xyz=(1, 2, 3), coordinate_system=cs),
              SimpleNamespace(p0=SimpleNamespace(xyz=(1, 2, 3)),
                              p1=SimpleNamespace(xyz=(4, 5, 6)), coordinate_system=cs),
              SimpleNamespace(pp=np.array([[1., 2., 3.], [4., 5., 6.]]), coordinate_system=cs)]
    for value in values:
        changes = []
        result = encode_metadata(value, conversions=changes)
        assert result["coordinates"] in ([1, 2, 3], [[1, 2, 3], [4, 5, 6]])
        assert result["coordinate_system"] == {"name": "UTM", "wkt": "PROJCRS[test]"}
        assert not any(item["lossy"] for item in changes)


def test_arrays_dates_and_unknown_types_are_explicit():
    class Invented:
        def __repr__(self):
            return "invented metadata"

    changes = []
    result = encode_metadata({"array": np.array([[1, 2], [3, 4]], dtype="int16"),
                              "date": date(2026, 11, 12),
                              "time": datetime(2026, 11, 12, tzinfo=timezone.utc),
                              "unknown": Invented()}, conversions=changes)
    assert result["array"] == [[1, 2], [3, 4]]
    assert result["date"] == "2026-11-12" and result["time"] == "2026-11-12T00:00:00+00:00"
    assert result["unknown"] == {"type": "Invented", "repr": "invented metadata"}
    assert any(item["path"] == "unknown" and item["lossy"] for item in changes)
    assert any(item["path"] == "array" and item["dtype"] == "<i2" for item in changes)


def test_cycles_and_broken_repr_or_geometry_do_not_abort():
    class Broken:
        @property
        def xyz(self):
            raise ValueError("geometry unavailable")

        def __repr__(self):
            raise ValueError("repr unavailable")

    cycle = []
    cycle.append(cycle)
    changes = []
    result = encode_metadata({"cycle": cycle, "broken": Broken()}, conversions=changes)
    assert result["cycle"][0]["type"] == "list"
    assert "repr failed" in result["broken"]["repr"]
    assert any("geometry unavailable" in item.get("error", "") for item in changes)


def test_numpy_dates_and_extended_scalars_cannot_recurse():
    result = encode_metadata({"date": np.datetime64("2026-11-12"), "extended": np.longdouble("1.25")})
    assert result["date"] == "2026-11-12"
    assert isinstance(result["extended"], (dict, float))
