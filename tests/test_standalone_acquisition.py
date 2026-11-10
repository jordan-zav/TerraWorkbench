"""Standalone acquisition kernels, physical conventions and adapter extraction."""

from datetime import datetime
import inspect

import numpy as np
import pytest

from terraworkbench_core.coordinates import reproject_xy
from terraworkbench_core.geomagnetism import igrf_field
from terraworkbench_core.terrain_gravity import terrain_correction_prisms


def test_legacy_qc_helpers_are_the_same_objects():
    import compat.preprocessing as legacy
    from terraworkbench_core import preprocessing as core

    for name, value in vars(core).items():
        if not name.startswith("__") and callable(value):
            assert getattr(legacy, name) is value
    assert legacy.QC_SPACING == core.QC_SPACING


def test_real_igrf_matches_sdk_in_chunks_and_records_coefficients():
    ppigrf = pytest.importorskip("ppigrf")
    longitude = np.array([-75.0, 0.0, 5.32415])
    latitude = np.array([-10.0, 0.0, 60.39299])
    height = np.array([0.0, 1.0, 0.5])
    expected = ppigrf.igrf(longitude, latitude, height, datetime(2025, 1, 1))
    actual = igrf_field(longitude, latitude, height, "2025-01-01", chunk_size=1)
    for key, values in zip(("east_nt", "north_nt", "up_nt"), expected):
        np.testing.assert_allclose(
            actual[key], np.asarray(values).reshape(-1), rtol=1e-13
        )
    np.testing.assert_allclose(
        actual["total_nt"],
        np.sqrt(sum(np.asarray(v).reshape(-1) ** 2 for v in expected)),
    )
    assert len(actual["recipe"]["coefficient_sha256"]) == 64
    assert actual["recipe"]["axes"] == "east,north,up"
    assert (
        actual["recipe"]["epoch_range"][0] <= 2025 <= actual["recipe"]["epoch_range"][1]
    )
    with pytest.raises(ValueError, match="outside coefficient"):
        igrf_field(longitude, latitude, height, "2200-01-01")
    assert inspect.signature(ppigrf.igrf).parameters["coeff_fn"].default


@pytest.mark.parametrize(
    "arguments",
    [
        ([0], [91], [0]),
        ([181], [0], [0]),
        ([0, 1], [0], [0]),
        ([0], [0], [float("nan")]),
    ],
)
def test_igrf_rejects_invalid_geometry_before_engine(arguments):
    with pytest.raises(ValueError):
        igrf_field(*arguments, "2025-01-01")


def test_igrf_cancellation_and_work_budget():
    with pytest.raises(RuntimeError, match="canceled"):
        igrf_field([0], [0], [0], "2025-01-01", canceled=lambda: True)
    with pytest.raises(ValueError):
        igrf_field([0, 1], [0, 1], [0, 0], "2025-01-01", max_points=1)


@pytest.mark.parametrize(
    "z", [np.zeros((2, 3)), np.array([[10.0, 5.0, -2.0], [3.0, 7.0, -4.0]])]
)
def test_terrain_blocks_match_original_prism_layer(z):
    hm = pytest.importorskip("harmonica")
    x, y = np.arange(3.0) * 10, np.arange(2.0) * 10
    density = np.where(z >= 0, 2670.0, 1040.0 - 2670.0)
    layer = hm.prism_layer((x, y), z, reference=0.0, properties={"density": density})
    xx, yy = np.meshgrid(x, y)
    expected_effect = layer.prism_layer.gravity(
        (xx, yy, z + 1.0), field="g_z", thickness_threshold=0.001
    )
    expected_plate = hm.bouguer_correction(
        z, density_crust=2670.0, density_water=1040.0
    )
    actual = terrain_correction_prisms(
        x,
        y,
        z,
        density_crust=2670.0,
        density_water=1040.0,
        clearance_m=1.0,
        block_size=2,
    )
    np.testing.assert_allclose(actual["prism_effect_mgal"], expected_effect, atol=1e-12)
    np.testing.assert_allclose(
        actual["terrain_mgal"], expected_plate - expected_effect, atol=1e-12
    )
    assert actual["recipe"]["interactions"] == 36
    assert actual["recipe"]["gravity_positive"] == "down"


def test_terrain_budgets_nulls_and_cancellation():
    options = dict(
        easting=[0, 1],
        northing=[0, 1],
        elevation_m=np.ones((2, 2)),
        density_crust=2670.0,
        density_water=1040.0,
        clearance_m=1.0,
    )
    with pytest.raises(ValueError, match="budget"):
        terrain_correction_prisms(**options, max_interactions=15)
    with pytest.raises(ValueError, match="budget"):
        terrain_correction_prisms(**options, max_cells=3)
    with pytest.raises(RuntimeError, match="canceled"):
        terrain_correction_prisms(**options, canceled=lambda: True)
    options["elevation_m"][0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        terrain_correction_prisms(**options)


def test_reprojection_reference_roundtrip_masks_and_vertical_refusal():
    pytest.importorskip("pyproj")
    result = reproject_xy(
        [-75, -75, np.nan], [0, -10, -5], "EPSG:4326", "EPSG:32718", block_size=1
    )
    np.testing.assert_allclose(result["x"][:2], 500000.0, atol=1e-7)
    np.testing.assert_allclose(
        result["y"][:2], [10000000.0, 8894587.50869892], atol=1e-5
    )
    assert (
        not result["valid"][2] and np.isnan(result["x"][2]) and np.isnan(result["y"][2])
    )
    back = reproject_xy(result["x"], result["y"], "EPSG:32718", "EPSG:4326")
    np.testing.assert_allclose(back["x"][:2], [-75, -75], atol=1e-9)
    np.testing.assert_allclose(back["y"][:2], [0, -10], atol=1e-9)
    assert result["recipe"]["vertical_transformation"] is False
    with pytest.raises(ValueError, match="2-D"):
        reproject_xy([0], [0], "EPSG:4979", "EPSG:4326")
    with pytest.raises(RuntimeError, match="canceled"):
        reproject_xy([0], [0], "EPSG:4326", "EPSG:32718", canceled=lambda: True)
