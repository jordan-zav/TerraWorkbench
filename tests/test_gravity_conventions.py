import json

import numpy as np
import pytest

from gravity_corrections import land_gravity_reduction, normal_gravity_somigliana, normal_gravity_grs80


def test_default_model_unchanged_and_custom_model_explicit():
    np.testing.assert_allclose(normal_gravity_grs80([0., 45., 90.]),
                               [978032.67715, 980619.9203, 983218.6369], atol=.0001, rtol=0)
    assert normal_gravity_somigliana(0., equator_mgal=980000.) == 980000.
    with pytest.raises(ValueError):
        normal_gravity_grs80(91.)
    with pytest.raises(ValueError):
        normal_gravity_somigliana(0., eccentricity_squared=1.)


def test_reduction_separates_observation_and_ground_heights():
    args = dict(height_reference="MSL", density_kg_m3=2500., slab_coefficient=.04)
    products, recipe = land_gravity_reduction([980100.], [0.], [1000.], [200.], equator_mgal=980000., **args)
    np.testing.assert_allclose(products["free_air_anomaly"], [408.6])
    np.testing.assert_allclose(products["bouguer_slab"], [20.])
    np.testing.assert_allclose(products["simple_bouguer_anomaly"], [388.6])
    assert json.loads(json.dumps(recipe))["equator_mgal"] == 980000.
    with pytest.raises(ValueError):
        land_gravity_reduction([1.], [0.], [1.], [-1.], **args)
    with pytest.raises(ValueError):
        land_gravity_reduction([1., 2.], [0.], [1.], [1.], **args)


def test_reduction_preserves_missing_observations():
    products, _ = land_gravity_reduction([np.nan], [0.], [1.], [1.],
        height_reference="ellipsoid", density_kg_m3=2500., slab_coefficient=.04)
    assert np.isnan(products["simple_bouguer_anomaly"][0])
