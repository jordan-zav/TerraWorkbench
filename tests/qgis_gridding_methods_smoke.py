"""Check real QGIS integration, cardinal samples and raster registration."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(os.environ['QGIS_PREFIX_PATH'])/'python/plugins'))
import numpy as np
from osgeo import gdal
from qgis.core import QgsProcessingException, QgsProject, QgsApplication, QgsProcessingProvider, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QMessageBox
from processing.core.Processing import Processing
import processing
from TerraWorkbench.algorithms.survey_gridding import SurveyPointGriddingAlgorithm
from TerraWorkbench.algorithms.sinc_interpolation import SincInterpolationAlgorithm
from TerraWorkbench.ui.i18n import set_language


class Provider(QgsProcessingProvider):
    def id(self):
        return 'testgridding'

    def name(self):
        return 'Test gridding'

    def loadAlgorithms(self):
        self.addAlgorithm(SurveyPointGriddingAlgorithm())
        self.addAlgorithm(SincInterpolationAlgorithm())


app = QgsApplication([], False)
app.initQgis()
set_language("en")
Processing.initialize()
provider = Provider()
QgsApplication.processingRegistry().addProvider(provider)
with tempfile.TemporaryDirectory() as folder:
    points = QgsVectorLayer('Point?crs=EPSG:32617&field=z:double&field=flight:integer', 'test', 'memory')
    features = []
    for y in range(7):
        for x in range(7):
            f = QgsFeature(points.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000+x, 4600000+y)))
            f.setAttributes([float(2*x-3*y+10), y])
            features.append(f)
    points.dataProvider().addFeatures(features)
    points.updateExtents()
    for method in (2, 4, 5):
        path = str(Path(folder)/f'method_{method}.tif')
        processing.run('testgridding:grid_survey_points', {
            'INPUT': points, 'VALUE_FIELD': 'z', 'CELL_SIZE': 1.,
            'METHOD': method, 'SINC_SPACING': 1., 'OUTPUT': path})
        ds = gdal.Open(path)
        a = ds.ReadAsArray().astype(float)
        yy, xx = np.mgrid[6:-1:-1, 0:7]
        np.testing.assert_allclose(a, 2*xx-3*yy+10, atol=1e-5)
        gt = ds.GetGeoTransform()
        ds = None
    oversized = str(Path(folder) / "large.tif")
    params = {
        "INPUT": points, "VALUE_FIELD": "z", "CELL_SIZE": 0.0085,
        "METHOD": 5, "RANGRID_COARSE_GRID": 4, "RANGRID_MAX_ITERATIONS": 1,
        "OUTPUT": oversized,
    }
    try:
        processing.run("testgridding:grid_survey_points", params)
    except QgsProcessingException as error:
        assert "500,000" in str(error) and "Allow large minimum-curvature grids" in str(error)
    else:
        raise AssertionError("The default limit must reject the large grid")
    assert not Path(oversized).exists()
    processing.run("testgridding:grid_survey_points", {
        **params, SurveyPointGriddingAlgorithm.ALLOW_LARGE_GRID: True,
    })
    ds = gdal.Open(oversized)
    record = json.loads(ds.GetMetadataItem("TW_MINIMUM_CURVATURE"))
    assert record["working_nodes"] > 500_000 and record["allow_large_grid"]
    assert np.isfinite(ds.ReadAsArray()).all()
    ds = None
    dialog_output = str(Path(os.environ["TEMP"]) / "dialog-large.tif")
    algorithm = QgsApplication.processingRegistry().createAlgorithmById(
        "testgridding:grid_survey_points"
    )
    dialog = algorithm.createCustomParametersWidget()
    QgsProject.instance().addMapLayer(points)
    dialog.setParameters({**params, "OUTPUT": dialog_output})
    accepted = []
    results = []
    dialog.algorithmFinished.connect(lambda ok, result: results.append((ok, result)))

    def answer_limit():
        prompt = QApplication.activeModalWidget()
        if isinstance(prompt, QMessageBox):
            for button in prompt.buttons():
                if button.text() == "Continue only this time":
                    assert "505,521" in prompt.text()
                    accepted.append(True)
                    button.click()
                    return

    timer = QTimer(dialog)
    timer.timeout.connect(answer_limit)
    timer.start(20)
    dialog.show()
    dialog.runAlgorithm()
    deadline = time.monotonic() + 20
    while not any(ok for ok, _ in results) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    timer.stop()
    assert accepted == [True] and Path(dialog_output).is_file(), results
    assert not dialog.mainWidget().createProcessingParameters().get(
        SurveyPointGriddingAlgorithm.ALLOW_LARGE_GRID, False
    )
    dialog.close()

    print("PASS: default node limit, explicit opt-in and one-time dialog retry")
    expanded = str(Path(folder)/'expanded.tif')
    processing.run('testgridding:sinc_interpolation', {
        'INPUT': path, 'FACTOR_X': 2, 'FACTOR_Y': 3, 'OUTPUT': expanded})
    ds = gdal.Open(expanded)
    assert ds.ReadAsArray().shape == (19,13)
    np.testing.assert_allclose(ds.ReadAsArray()[::3,::2], a, atol=1e-10)
    outgt = ds.GetGeoTransform()
    assert abs((outgt[0]+outgt[1]/2)-(gt[0]+gt[1]/2)) < 1e-9
    assert abs((outgt[3]+outgt[5]/2)-(gt[3]+gt[5]/2)) < 1e-9
    ds = None
    boundary = QgsVectorLayer('Polygon?crs=EPSG:32617', 'survey_boundary', 'memory')
    coverage = QgsFeature()
    coverage.setGeometry(QgsGeometry.fromWkt(
        'POLYGON ((500000 4600000, 500006 4600000, 500006 4600006, '
        '500000 4600006, 500000 4600000), (500002 4600002, 500004 4600002, '
        '500004 4600004, 500002 4600004, 500002 4600002))'))
    assert boundary.dataProvider().addFeatures([coverage])[0]
    output = str(Path(folder)/'bidir.tif')
    processing.run('testgridding:grid_survey_points', {
        'INPUT': points, 'VALUE_FIELD': 'z', 'METHOD': 6, 'CELL_SIZE': 0.,
        'LINE_FIELD': 'flight', 'LINE_SPACING_DIVISOR': 1, 'LINE_TREND': True,
        'CROSS_METHOD': 1, 'BOUNDARY': boundary, 'OUTPUT': output})
    ds = gdal.Open(output)
    raster = ds.ReadAsArray()
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    assert ds.GetSpatialRef().GetAuthorityCode(None) == '32617'
    assert abs(ds.GetGeoTransform()[1] - 0.2) < 1e-12
    assert raster.shape == (31, 31)
    assert raster[15, 15] == nodata
    assert raster[30, 0] == 10.
    ds = None
print('PASS: TPS, minimum curvature, sinc, bidirectional flight spacing, polygon mask and CRS')
