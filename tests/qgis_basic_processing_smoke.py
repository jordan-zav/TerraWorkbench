"""Run with python-qgis-ltr.bat; no survey data or Oasis needed."""

import os
import gc
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python" / "plugins"))

import numpy as np
from osgeo import gdal
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsRasterLayer, QgsVectorLayer, QgsProcessingException,
                       QgsProcessingContext)
from qgis.PyQt import sip
import processing
from processing.core.Processing import Processing
from TerraWorkbench.provider import TerraWorkbenchProvider
from TerraWorkbench.workflow_dock import available_algorithms
from TerraWorkbench import i18n


def main():
    app = QgsApplication([], False)
    app.initQgis()
    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    ids = {a.name() for a in available_algorithms()}
    assert {"smooth_nine_point", "automatic_gain_control", "circular_median"} <= ids
    original_language = i18n.language
    try:
        labels = []
        for code in ("en", "es", "pt"):
            i18n.language = lambda code=code: code
            labels.append(QgsApplication.processingRegistry().algorithmById(
                "terraworkbench:smooth_nine_point").displayName())
        assert len(set(labels)) == 3
    finally:
        i18n.language = original_language
    with tempfile.TemporaryDirectory(prefix="tw_basic_") as folder:
        context = QgsProcessingContext()
        points = QgsVectorLayer("Point?crs=EPSG:32617&field=z:double", "points", "memory")
        features = []
        for x, y in [(0, 0), (0, 4), (4, 0), (4, 4), (2, 2)]:
            feature = QgsFeature(points.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000+x, 4000000+y)))
            feature.setAttributes([float(10+2*x-y)])
            features.append(feature)
        points.dataProvider().addFeatures(features)
        points.updateExtents()
        for method in (0, 1, 2, 3):
            path = str(Path(folder) / f"grid_{method}.tif")
            processing.run("terraworkbench:grid_survey_points", {
                "INPUT": points, "VALUE_FIELD": "z", "CELL_SIZE": 1.,
                "METHOD": method, "SEARCH_RADIUS": 1.1, "TPS_NEIGHBORS": 5,
                "OUTPUT": path,
            }, context=context)
            ds = gdal.Open(path)
            source = ds.ReadAsArray()
            mask = source == ds.GetRasterBand(1).GetNoDataValue()
            assert mask.any() and (~mask).any()
            transform, projection = ds.GetGeoTransform(), ds.GetProjection()
            if method >= 2:
                yy, xx = np.indices(source.shape)
                np.testing.assert_allclose(source[~mask], (10+2*xx-(4-yy))[~mask], atol=1e-5)
            ds = None
        current = path
        for name, params in [("smooth_nine_point", {"PASSES": 2}),
                             ("automatic_gain_control", {"WINDOW": 3}),
                             ("circular_median", {"RADIUS": 2})]:
            output = str(Path(folder) / f"{name}.tif")
            input_layer = QgsRasterLayer(current, "input")
            processing.run("terraworkbench:"+name, {"INPUT": input_layer,
                           "BAND": 1, "OUTPUT": output, **params}, context=context)
            sip.delete(input_layer)
            ds = gdal.Open(output)
            result = ds.ReadAsArray()
            assert ds.GetGeoTransform() == transform and ds.GetProjection() == projection
            assert np.isnan(ds.GetRasterBand(1).GetNoDataValue())
            np.testing.assert_array_equal(np.isnan(result), mask)
            assert np.isfinite(result[~mask]).all()
            assert "SciPy" in ds.GetMetadata()["TW_BACKEND"]
            ds = None
            current = output
        input_layer = QgsRasterLayer(current, "input")
        try:
            processing.run("terraworkbench:automatic_gain_control", {
                "INPUT": input_layer, "WINDOW": 4,
                "OUTPUT": str(Path(folder) / "invalid.tif")}, context=context)
        except QgsProcessingException:
            pass
        else:
            raise AssertionError("Even AGC window accepted")
        finally:
            sip.delete(input_layer)
        context.temporaryLayerStore().removeAllMapLayers()
        del context
        gc.collect()
    print("PASS: four gridders, smoothing -> AGC, NoData, metadata, georeferencing and stack registration")
    # QGIS/Qt native teardown is owned by process exit, as in other smoke tests.


if __name__ == "__main__":
    main()
