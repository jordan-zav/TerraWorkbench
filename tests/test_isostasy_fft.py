"""Physical and boundary checks for the periodic Parker Airy solver."""
from importlib.util import find_spec
import unittest

import numpy as np

from isostasy import airy_prisms, airy_root_effect_fft


class AiryFFTTests(unittest.TestCase):
    def test_uniform_load_keeps_dc_and_sign(self):
        for h in (-500., 0., 1000.):
            for height in (0., 2000.):
                effect, info = airy_root_effect_fft(np.full((12, 16), h), (500., 800.),
                                                    boundary="periodic", observation_height=height)
                np.testing.assert_allclose(effect, -2*np.pi*6.67430e-6*2670*h, atol=1e-10)
                self.assertEqual(info["dc_term"], "preserved")
                self.assertEqual(info["fitted_offset_mgal"], 0)

    def test_linear_limit_and_upward_attenuation(self):
        x = np.arange(64)*1000.
        h = np.broadcast_to(.1*np.cos(2*np.pi*x/64000), (32, 64)).copy()
        for height in (0., 10000.):
            effect, _ = airy_root_effect_fft(h, (1000., 1000.), boundary="periodic",
                                             observation_height=height, tolerance_mgal=1e-10)
            expected = -2*np.pi*6.67430e-6*2670*h*np.exp(-2*np.pi*(30000+height)/64000)
            np.testing.assert_allclose(effect, expected, atol=1e-8)

    def test_water_load_and_periodic_translation(self):
        rng = np.random.default_rng(3)
        h = rng.uniform(-1000, 1000, (32, 40))
        water = np.maximum(-h, 0)
        a, _ = airy_root_effect_fft(h, (1000., 1000.), boundary="periodic", water_thickness=water)
        equivalent = h+1040/2670*water
        b, _ = airy_root_effect_fft(np.roll(equivalent, 7, axis=1), (1000., 1000.), boundary="periodic")
        np.testing.assert_allclose(np.roll(a, 7, axis=1), b, atol=1e-10)

    def test_rejects_gaps_boundary_and_unconverged_series(self):
        h = np.ones((4, 4))*1000
        for extra in [dict(boundary="finite"), dict(spacing=(0, 1)),
                      dict(density_mantle=2670), dict(max_cells=4),
                      dict(observation_height=-29000), dict(max_terms=3),
                      dict(water_thickness=-1), dict(tolerance_mgal=np.nan)]:
            options = dict(spacing=(1000., 1000.), boundary="periodic")
            options.update(extra)
            with self.assertRaises(ValueError):
                airy_root_effect_fft(h, **options)
        h[0, 0] = np.nan
        with self.assertRaises(ValueError):
            airy_root_effect_fft(h, (1000, 1000), boundary="periodic")
        with self.assertRaises(InterruptedError):
            airy_root_effect_fft(np.zeros((4, 4)), (1000, 1000), boundary="periodic", cancelled=lambda: True)

    @unittest.skipUnless(find_spec("harmonica"), "Independent prism backend")
    def test_independent_periodic_prism_sum(self):
        import harmonica as hm
        n, dx = 24, 4000.
        x = np.arange(n)*dx
        xx, yy = np.meshgrid(x, x)
        h = 500 + 100*np.cos(2*np.pi*xx/(n*dx))*np.cos(2*np.pi*yy/(n*dx))
        effect, _ = airy_root_effect_fft(h, (dx, dx), boundary="periodic", tolerance_mgal=1e-9)
        p, rho = airy_prisms(x, x, h, density_mantle=3270.)
        flat, frho = airy_prisms(x, x, np.full_like(h, 500.), density_mantle=3270.)
        tiled, baseline = [], []
        for i in range(-6, 7):
            for j in range(-6, 7):
                shift = np.array([i,i,j,j,0,0])*n*dx
                tiled.append(p+shift)
                baseline.append(flat+shift)
        rows, cols = np.array([0, 4, 12, 18]), np.array([0, 8, 12, 16])
        xyz = (x[cols], x[rows], np.zeros(4))
        direct = hm.prism_gravity(xyz, np.concatenate(tiled), np.tile(rho, 169), field="g_z")
        direct -= hm.prism_gravity(xyz, np.concatenate(baseline), np.tile(frho, 169), field="g_z")
        # Analytic infinite baseline supplies the otherwise truncated DC mass.
        direct -= 2*np.pi*6.67430e-6*2670*500
        np.testing.assert_allclose(effect[rows, cols], direct, atol=.01)


if __name__ == "__main__":
    unittest.main()
