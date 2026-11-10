import numpy as np
import pytest

pytest.importorskip("harmonica")

from terraworkbench_core.adaptive_terrain import terrain_gravity_adaptive


def fixture():
    x, y = np.arange(13.0) * 25.0, np.arange(9.0) * 30.0
    yy, xx = np.meshgrid(y, x, indexing="ij")
    z = 30.0 * np.sin(xx / 100.0) * np.cos(yy / 80.0)
    return x, y, z


def direct(x, y, z, stations, reference=0.0):
    hm = pytest.importorskip("harmonica")
    layer = hm.prism_layer(
        (x, y),
        z,
        reference=reference,
        properties={"density": np.where(z >= reference, 2670.0, 1040.0 - 2670.0)},
    )
    return layer.prism_layer.gravity(tuple(stations.T), field="g_z", parallel=False)


@pytest.mark.parametrize("leaf", [1, 17, 128])
def test_exact_tree_matches_direct_prisms_and_input_preservation(leaf):
    x, y, z = fixture()
    stations = np.array(
        [[30.0, 50.0, 80.0], [100.0, 140.0, 40.0], [400.0, -100.0, -30.0]]
    )
    original = z.copy()
    result = terrain_gravity_adaptive(
        x,
        y,
        z,
        stations,
        density_crust=2670.0,
        density_water=1040.0,
        reference_elevation_m=0.0,
        absolute_tolerance_mgal=0.0,
        leaf_cells=leaf,
    )
    np.testing.assert_allclose(
        result["prism_effect_mgal"], direct(x, y, z, stations), atol=1e-11
    )
    assert np.all(result["truncation_bound_mgal"] == 0)
    assert np.all(result["monopole_count"] == 0)
    assert result["recipe"]["exact_prism_evaluations"] == np.count_nonzero(z) * len(
        stations
    )
    np.testing.assert_array_equal(z, original)


def test_far_field_error_bound_signed_mass_and_tolerance_refinement():
    x, y, z = fixture()
    stations = np.array(
        [[5000.0, 6000.0, 2000.0], [7000.0, -5000.0, -1000.0], [40.0, 60.0, 50.0]]
    )
    expected = direct(x, y, z, stations)
    counts = []
    for tolerance in (1e-3, 1e-6, 1e-10, 0.0):
        result = terrain_gravity_adaptive(
            x,
            y,
            z,
            stations,
            density_crust=2670.0,
            density_water=1040.0,
            reference_elevation_m=0.0,
            absolute_tolerance_mgal=tolerance,
            leaf_cells=8,
        )
        error = abs(result["prism_effect_mgal"] - expected)
        assert np.all(error <= result["truncation_bound_mgal"] + 1e-11)
        assert np.all(result["truncation_bound_mgal"] <= tolerance * (1 + 1e-12))
        counts.append(result["recipe"]["exact_prism_evaluations"])
        if tolerance == 1e-3:
            assert result["monopole_count"][:2].min() > 0
            assert result["exact_prism_count"][:2].max() == 0
    assert counts == sorted(counts)


def test_reference_plane_translation_and_zero_model():
    x, y, z = fixture()
    stations = np.array([[30.0, 50.0, 80.0], [5000.0, 4000.0, 1000.0]])
    options = dict(
        density_crust=2670.0, density_water=1040.0, absolute_tolerance_mgal=1e-7
    )
    base = terrain_gravity_adaptive(
        x, y, z, stations, reference_elevation_m=0.0, **options
    )
    shifted = terrain_gravity_adaptive(
        x + 500000,
        y + 6000000,
        z + 125.0,
        stations + [500000, 6000000, 125.0],
        reference_elevation_m=125.0,
        **options,
    )
    np.testing.assert_allclose(
        shifted["prism_effect_mgal"], base["prism_effect_mgal"], atol=1e-10
    )
    zero = terrain_gravity_adaptive(
        x, y, np.zeros_like(z), stations, reference_elevation_m=0.0, **options
    )
    assert np.all(zero["prism_effect_mgal"] == 0)
    assert zero["recipe"]["exact_prism_evaluations"] == 0


def test_budgets_invalid_geometry_and_cancellation():
    x, y, z = fixture()
    options = dict(
        easting=x,
        northing=y,
        elevation_m=z,
        observation_xyz=[[30.0, 50.0, 80.0]],
        density_crust=2670.0,
        density_water=1040.0,
        reference_elevation_m=0.0,
        absolute_tolerance_mgal=0.0,
    )
    for invalid in (
        dict(max_cells=2),
        dict(max_tree_nodes=1, leaf_cells=1),
        dict(max_node_visits=1, leaf_cells=1),
        dict(max_prism_evaluations=1),
        dict(absolute_tolerance_mgal=-1.0),
        dict(easting=x[::-1]),
        dict(elevation_m=z + np.nan),
    ):
        with pytest.raises(ValueError):
            terrain_gravity_adaptive(**dict(options, **invalid))
    with pytest.raises(RuntimeError, match="canceled"):
        terrain_gravity_adaptive(**options, canceled=lambda: True)
