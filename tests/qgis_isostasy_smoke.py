"""Regional Airy adapter regression in a real QGIS process."""
import json
import os
from pathlib import Path
import sys
import tempfile
import faulthandler
import gc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication, QgsProcessingContext, QgsProcessingFeedback, QgsProcessingException, QgsRasterLayer
from osgeo import gdal, osr
import numpy as np


def main():
    faulthandler.dump_traceback_later(45, repeat=True)
    print("Initializing QGIS", flush=True)
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    print("Loading gravity backend", flush=True)
    from TerraWorkbench.algorithms.gravity_corrections import AiryIsostaticAnomalyAlgorithm, AiryFFTAnomalyAlgorithm
    from TerraWorkbench.dependencies import import_harmonica
    from TerraWorkbench.isostasy import airy_prisms, airy_root_effect
    hm = import_harmonica()
    print("Running regional adapter", flush=True)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(26910)
    with tempfile.TemporaryDirectory() as folder:
        def layer(name, data, gt):
            path = str(Path(folder) / (name + ".tif"))
            ds = gdal.GetDriverByName("GTiff").Create(path, data.shape[1], data.shape[0], 1, gdal.GDT_Float64)
            ds.SetProjection(srs.ExportToWkt())
            ds.SetGeoTransform(gt)
            ds.GetRasterBand(1).SetNoDataValue(-99999.)
            ds.GetRasterBand(1).WriteArray(data)
            ds = None
            return QgsRasterLayer(path, name)

        gt = (500000, 500, 0, 5500000, 0, -500)
        model_gt = (480000, 10000, 0, 5520000, 0, -10000)
        bouguer = np.full((3, 4), -100.)
        bouguer[0, 1] = -99999
        height = np.full((3, 4), 1500.)
        height[2, 3] = -99999
        h = np.arange(25).reshape(5, 5)*50.
        water = np.full((5, 5), 20.)
        alg = AiryIsostaticAnomalyAlgorithm()
        alg.initAlgorithm()
        context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
        output = str(Path(folder) / "result.tif")
        params = dict(INPUT=layer("bouguer", bouguer, gt), BAND=1,
                      ELEVATION=layer("height", height, gt), ELEVATION_BAND=1,
                      REGIONAL=layer("regional", h, model_gt), WATER=layer("water", water, model_gt),
                      DENSITY_CRUST=2670., DENSITY_MANTLE=3070., DENSITY_WATER=1040.,
                      REFERENCE_DEPTH=30000., BLOCK_SIZE=2, MAX_CELLS=100,
                      MAX_INTERACTIONS=100000., OUTPUT=output)
        alg.processAlgorithm(params, context, feedback)
        ds = gdal.Open(output)
        result = ds.ReadAsArray()
        assert result[0, 1] == -99999 and result[2, 3] == -99999
        assert json.loads(ds.GetMetadata()["TW_ISOSTASY"])["block_size"] == 2
        p, rho = airy_prisms(485000+np.arange(5)*10000, 5475000+np.arange(5)*10000,
                             h[::-1], water_thickness=water[::-1], block_size=2)
        rr, cc = np.indices(height.shape)
        expected = -100 - airy_root_effect((500250+cc*500, 5499750-rr*500,
                                            np.full(height.shape, 1500.)), p, rho,
                                           gravity_backend=hm.prism_gravity)
        valid = result != -99999
        np.testing.assert_allclose(result[valid], expected[valid], atol=1e-10)
        ds = None
        # Legacy calls without regional/water arguments retain the prism-layer result.
        clean = np.arange(12).reshape(3, 4)*50.+500
        params.update(ELEVATION=layer("legacy", clean, gt))
        for key in ("REGIONAL", "WATER", "BLOCK_SIZE", "MAX_INTERACTIONS", "DENSITY_WATER"):
            params.pop(key)
        alg.processAlgorithm(params, context, feedback)
        x, y = 500250+np.arange(4)*500, 5498750+np.arange(3)*500
        root = 2670/400*clean[::-1]
        old = hm.prism_layer((x, y), -30000-root, reference=-30000,
                             properties={"density": np.full(root.shape, -400.)})
        xx, yy = np.meshgrid(x, y)
        expected = -100-old.prism_layer.gravity((xx, yy, clean[::-1]), field="g_z")[::-1]
        ds = gdal.Open(output)
        result = ds.ReadAsArray()
        valid = result != -99999
        np.testing.assert_allclose(result[valid], expected[valid], atol=1e-9)
        ds = None
        params["MAX_INTERACTIONS"] = 1
        try:
            alg.processAlgorithm(params, context, feedback)
            raise AssertionError("Expected work-limit rejection")
        except QgsProcessingException as error:
            assert "max_interactions" in str(error)
        params["ELEVATION"] = layer("missing_model", height, gt)
        try:
            alg.processAlgorithm(params, context, feedback)
            raise AssertionError("Expected missing-load rejection")
        except QgsProcessingException as error:
            assert "Regional load model contains NoData" in str(error)
        spectral = AiryFFTAnomalyAlgorithm()
        spectral.initAlgorithm()
        fft_params = dict(INPUT=params["INPUT"], BAND=1,
                          REGIONAL=layer("fft_load", np.full((5, 5), 1000.), model_gt),
                          DENSITY_CRUST=2670., DENSITY_MANTLE=3270.,
                          DENSITY_WATER=1040., REFERENCE_DEPTH=30000., HEIGHT=0.,
                          TOLERANCE=1e-7, MAX_CELLS=100, OUTPUT=output)
        spectral.processAlgorithm(fft_params, context, feedback)
        ds = gdal.Open(output)
        result = ds.ReadAsArray()
        assert result[0, 1] == -99999
        assert result[2, 3] != -99999  # constant plane does not require terrain heights
        np.testing.assert_allclose(result[result != -99999], -100+2*np.pi*6.67430e-6*2670*1000)
        assert json.loads(ds.GetMetadata()["TW_ISOSTASY"])["boundary"] == "periodic"
        ds = None
        fft_params["REGIONAL"] = layer("fft_far", np.ones((5,5)), (800000,10000,0,5800000,0,-10000))
        try:
            spectral.processAlgorithm(fft_params, context, feedback)
            raise AssertionError("Expected sampling-domain rejection")
        except QgsProcessingException as error:
            assert "out of bounds" in str(error)
        fft_params.clear()
        params.clear()
        del context
        gc.collect()
        print("PASS: regional prisms and periodic FFT; masks, water, metadata, bounds, work limits and legacy parity")
    app.exitQgis()
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    main()
