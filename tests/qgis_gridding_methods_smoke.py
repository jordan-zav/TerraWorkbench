"""Check real QGIS integration, cardinal samples and raster registration."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(os.environ['QGIS_PREFIX_PATH'])/'python/plugins'))
import numpy as np
from osgeo import gdal
from qgis.core import QgsApplication, QgsProcessingProvider, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
from processing.core.Processing import Processing
import processing
from TerraWorkbench.algorithms.survey_gridding import SurveyPointGriddingAlgorithm
from TerraWorkbench.algorithms.sinc_interpolation import SincInterpolationAlgorithm


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
Processing.initialize()
provider = Provider()
QgsApplication.processingRegistry().addProvider(provider)
with tempfile.TemporaryDirectory() as folder:
    points = QgsVectorLayer('Point?crs=EPSG:32617&field=z:double', 'test', 'memory')
    features = []
    for y in range(7):
        for x in range(7):
            f = QgsFeature(points.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000+x, 4600000+y)))
            f.setAttributes([float(2*x-3*y+10)])
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
print('PASS: TPS compatibility, minimum curvature, regular sinc and raster expansion registration')
