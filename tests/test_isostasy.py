import unittest
from importlib.util import find_spec

import numpy as np

from isostasy import airy_prisms, airy_root_effect


class IsostasyTests(unittest.TestCase):
    def test_mass_conservation_and_partial_blocks(self):
        h = np.arange(35.).reshape(5, 7) * 100 - 1000
        water = np.maximum(-h, 0)
        x, y = np.arange(7) * 1000., np.arange(5) * 1000.
        fine, rho = airy_prisms(x, y, h, water_thickness=water)
        coarse, rc = airy_prisms(x, y, h, water_thickness=water, block_size=3)
        def mass(p, r):
            return np.sum(np.prod(p[:, 1::2] - p[:, ::2], axis=1) * r)
        self.assertAlmostEqual(mass(fine, rho) / mass(coarse, rc), 1., places=12)
        self.assertEqual(len(coarse), 6)
        self.assertAlmostEqual(mass(fine, rho), -np.sum(2670*h + 1040*water)*1e6, delta=1.)

    @unittest.skipUnless(find_spec("harmonica"), "Harmonica optional test backend")
    def test_water_load_against_harmonica(self):
        import harmonica as hm
        h = np.array([[100., -1000.], [500., 0.]])
        water = np.array([[50., 1000.], [0., 0.]])
        p, rho = airy_prisms([0, 1000], [0, 1000], h, water_thickness=water)
        moho = hm.isostatic_moho_airy(h, layers={"water": (water, 1040.)},
                                    density_crust=2670., density_mantle=3070.,
                                    reference_depth=30000.)
        root = moho.ravel() - 30000
        np.testing.assert_allclose(p[:, 5] - p[:, 4], np.abs(root[root != 0]))
        np.testing.assert_array_equal(np.sign(rho), -np.sign(root[root != 0]))

    @unittest.skipUnless(find_spec("harmonica"), "Harmonica optional test backend")
    def test_wide_uniform_root_approaches_infinite_slab(self):
        p, rho = airy_prisms([-1e8, 1e8], [-1e8, 1e8], np.full((2, 2), 1000.))
        g = airy_root_effect(([0.], [0.], [0.]), p, rho)
        expected = -2 * np.pi * 6.67430e-11 * 2670 * 1000 * 1e5
        np.testing.assert_allclose(g, expected, rtol=3e-4)

    @unittest.skipUnless(find_spec("harmonica"), "Harmonica optional test backend")
    def test_stations_mask_chunking_and_cancellation(self):
        p, rho = airy_prisms([0, 1000], [0, 1000], np.ones((2, 2))*1000)
        xyz = ([0, 500, np.nan], [0, 500, 1000], [0, 0, 0])
        a = airy_root_effect(xyz, p, rho, chunk_size=1)
        b = airy_root_effect(xyz, p, rho, chunk_size=3)
        np.testing.assert_allclose(a, b)
        self.assertTrue(np.isnan(a[-1]))
        self.assertTrue(np.all(a[:2] < 0))
        with self.assertRaises(InterruptedError):
            airy_root_effect(xyz, p, rho, cancelled=lambda: True)
        with self.assertRaises(ValueError):
            airy_root_effect(xyz, p, rho, max_interactions=7)

    def test_no_silent_missing_load_or_invalid_model(self):
        for h in [np.array([[0, np.nan], [1, 2]]), np.full((2, 2), -10000)]:
            with self.assertRaises(ValueError):
                airy_prisms([0, 1000], [0, 1000], h)
        for kwargs in [dict(density_mantle=np.nan), dict(block_size=0),
                       dict(water_thickness=-1), dict(max_cells=3)]:
            with self.assertRaises(ValueError):
                airy_prisms([0, 1000], [0, 1000], np.ones((2, 2)), **kwargs)


if __name__ == "__main__":
    unittest.main()
