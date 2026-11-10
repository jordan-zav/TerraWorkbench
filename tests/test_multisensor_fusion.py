import unittest
import numpy as np
from terraworkbench_core.multisensor_fusion import (
    rgb_composite,
    pca_fusion,
    anomaly_coincidence,
    shift_without_wrap,
)


class FusionTests(unittest.TestCase):
    def test_mask_is_intersection_not_zero_fill(self):
        a = np.arange(25.0).reshape(5, 5)
        b = a.copy()
        b[0, 0] = np.nan
        c = a.copy()
        c[1, 1] = np.nan
        for function in (rgb_composite, pca_fusion, anomaly_coincidence):
            result, metadata = function([a, b, c])
            self.assertEqual(metadata["common_cells"], 23)
            self.assertTrue(np.isnan(result[0, 0]).all())
            self.assertTrue(np.isnan(result[1, 1]).all())

    def test_pca_duplicate_layers_and_reconstruction(self):
        a = np.arange(100.0).reshape(10, 10)
        components, m = pca_fusion([a, 2 * a, -3 * a], percentiles=(0, 100))
        self.assertAlmostEqual(m["explained_variance_ratio"][0], 1)
        reconstructed = components @ np.asarray(m["loadings"]).T * np.asarray(
            m["scales"]
        ) + np.asarray(m["means"])
        np.testing.assert_allclose(
            reconstructed, np.stack([a, 2 * a, -3 * a], axis=-1), atol=1e-11
        )

    def test_pca_unit_scaling_and_constant_layers(self):
        rng = np.random.default_rng(34)
        layers = [rng.normal(size=(20, 20)) for _ in range(3)]
        a, am = pca_fusion(layers)
        b, bm = pca_fusion([layers[0] * 1000, layers[1] * 0.001, layers[2]])
        np.testing.assert_allclose(a, b, atol=1e-10)
        c, cm = pca_fusion([np.ones((5, 5))] * 3)
        self.assertTrue(np.isfinite(c).all())
        self.assertEqual(sum(cm["explained_variance_ratio"]), 0)

    def test_rgb_channels_not_averaged(self):
        a = np.arange(25.0).reshape(5, 5)
        rgb, _ = rgb_composite([a, -a, np.ones_like(a)], percentiles=(0, 100))
        self.assertEqual(rgb[-1, -1, 0], 1)
        self.assertEqual(rgb[-1, -1, 1], 0)
        self.assertEqual(rgb[-1, -1, 2], 0)

    def test_coincidence_known_and_independent(self):
        a = np.zeros((10, 10))
        a[:2] = 1
        codes, m = anomaly_coincidence([a, a, a], 75)
        self.assertEqual(m["class_counts"]["7"], 20)
        self.assertEqual(m["pairs"]["0-1"]["dice"], 1)
        b = np.zeros_like(a)
        b[:, :2] = 1
        _, m = anomaly_coincidence([a, b, b], 75)
        self.assertAlmostEqual(m["pairs"]["0-1"]["overlap_to_independence"], 1)

    def test_shift_preserves_direction_no_wrap(self):
        a = np.arange(25.0).reshape(5, 5)
        b = shift_without_wrap(a, 1, -2)
        np.testing.assert_array_equal(b[1:, :3], a[:-1, 2:])
        self.assertTrue(np.isnan(b[0]).all())
        self.assertTrue(np.isnan(b[:, 3:]).all())

    def test_invalid_parameters(self):
        a = np.ones((5, 5))
        for function, kwargs in (
            (pca_fusion, {"percentiles": (98, 2)}),
            (rgb_composite, {"bounds": [[1, 0]] * 3}),
            (anomaly_coincidence, {"percentile": 100}),
        ):
            with self.assertRaises(ValueError):
                function([a, a, a], **kwargs)
        with self.assertRaises(ValueError):
            pca_fusion([a, np.ones((4, 5)), a])
        with self.assertRaises(ValueError):
            pca_fusion([a * np.nan] * 3)


if __name__ == "__main__":
    unittest.main()
