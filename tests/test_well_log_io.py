"""Synthetic LAS metadata, null handling, unit conversion and value round trip."""

import numpy as np
import pytest

from terraworkbench_core.well_log_io import read_las_text, update_las_curves


LAS = """~Version
 VERS. 2.0 : LAS version
 WRAP. NO : One line per depth step
~Well
 STRT.FT 0 : Start
 STOP.FT 20 : Stop
 STEP.FT 10 : Step
 NULL. -999.25 : Missing
 WELL. Synthetic well : Well name
~Curve
 DEPT.FT : Measured depth
 RHOB.G/C3 : Bulk density
 RES.OHM.M : Resistivity
~Parameter
 KB.M 100 : Elevation, supplied reference only
~Other
Synthetic benchmark, not a field dataset.
~ASCII
0 2.4 100
10 -999.25 200
20 2.6 300
"""


def test_las_depth_units_nulls_metadata_and_roundtrip():
    pytest.importorskip("lasio")
    result = read_las_text(LAS)
    np.testing.assert_allclose(result["depth_m"], [0.0, 3.048, 6.096])
    assert np.isnan(result["curve_values"][1, 1])
    assert result["curves"][1]["unit"] == "G/C3"
    assert any(
        item["mnemonic"] == "WELL" and item["value"] == "Synthetic well"
        for item in result["sections"]["Well"]
    )
    values = result["curve_values"].copy()
    values[:, 2] *= 2
    updated = update_las_curves(LAS, values)
    reread = read_las_text(updated["text"])
    np.testing.assert_allclose(reread["curve_values"], values, equal_nan=True)
    assert reread["curves"] == result["curves"]
    assert reread["original_depth_unit"].lower() == "ft"


def test_las_reject_unknown_units_and_depth_mutation():
    pytest.importorskip("lasio")
    unknown = LAS.replace("DEPT.FT", "DEPT.UNKNOWN")
    with pytest.raises(ValueError, match="Depth unit"):
        read_las_text(unknown)
    explicit = read_las_text(unknown, depth_unit_override="ft")
    assert (
        explicit["depth_unit_override"] == "ft"
        and explicit["original_depth_unit"] == "UNKNOWN"
    )
    values = read_las_text(LAS)["curve_values"]
    values[:, 0] += 1
    with pytest.raises(ValueError, match="depth"):
        update_las_curves(LAS, values)


def test_las_writer_preserves_small_and_large_float_channels():
    pytest.importorskip("lasio")
    values = read_las_text(LAS)["curve_values"]
    values[:, 1] = [1.23456789123456e-8, 1000000.123456789, -3.141592653589793e-12]
    updated = update_las_curves(LAS, values)
    reread = read_las_text(updated["text"])
    np.testing.assert_array_equal(reread["curve_values"], values)


def test_las_finite_null_collision_is_rejected_instead_of_lost():
    pytest.importorskip("lasio")
    values = read_las_text(LAS)["curve_values"]
    values[0, 1] = -999.25
    with pytest.raises(ValueError, match="NULL"):
        update_las_curves(LAS, values)
