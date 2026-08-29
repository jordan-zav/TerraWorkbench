import unittest

import numpy as np

from gravity_corrections import (
    airy_moho_depth,
    airy_root_thickness,
    complete_bouguer_anomaly,
    curvature_correction,
    free_air_anomaly,
    free_air_correction,
    normal_gravity_grs80,
    simple_bouguer_anomaly,
)


class GravityCorrectionTests(unittest.TestCase):
    def test_grs80_reference_values(self):
        values = normal_gravity_grs80(np.array([0.0, 45.0, 90.0]))
        self.assertAlmostEqual(values[0], 978032.67715, places=5)
        self.assertAlmostEqual(values[1], 980619.9203, places=3)
        self.assertAlmostEqual(values[2], 983218.6369, places=3)
        self.assertTrue(np.all(np.diff(values) > 0.0))

    def test_free_air_products_have_explicit_signs(self):
        elevation = np.array([0.0, 1000.0])
        correction = free_air_correction(elevation)
        np.testing.assert_allclose(correction, [0.0, 308.6])
        observed = np.array([978100.0, 978100.0])
        normal = np.array([978000.0, 978000.0])
        np.testing.assert_allclose(
            free_air_anomaly(observed, normal, elevation), [100.0, 408.6]
        )

    def test_simple_and_complete_bouguer_sequence(self):
        observed = np.array([978100.0])
        normal = np.array([978000.0])
        elevation = np.array([1000.0])
        plate = np.array([111.9])
        simple = simple_bouguer_anomaly(observed, normal, elevation, plate)
        complete = complete_bouguer_anomaly(
            observed,
            normal,
            elevation,
            plate,
            terrain_mgal=np.array([5.0]),
            curvature_mgal=np.array([1.0]),
        )
        np.testing.assert_allclose(simple, [296.7])
        np.testing.assert_allclose(complete, simple + 4.0)

    def test_curvature_is_land_only_and_density_scaled(self):
        heights = np.array([-100.0, 0.0, 1000.0])
        standard = curvature_correction(heights, 2670.0)
        half = curvature_correction(heights, 1335.0)
        self.assertEqual(standard[0], 0.0)
        self.assertEqual(standard[1], 0.0)
        self.assertGreater(standard[2], 0.0)
        np.testing.assert_allclose(half, 0.5 * standard)

    def test_airy_root_and_moho(self):
        topography = np.array([0.0, 1000.0, -1000.0])
        root = airy_root_thickness(topography, 2670.0, 3070.0)
        np.testing.assert_allclose(root, [0.0, 6675.0, -6675.0])
        np.testing.assert_allclose(
            airy_moho_depth(topography, 25000.0, 2670.0, 3070.0),
            25000.0 + root,
        )
        with self.assertRaises(ValueError):
            airy_root_thickness(topography, 2670.0, 2600.0)


if __name__ == "__main__":
    unittest.main()
