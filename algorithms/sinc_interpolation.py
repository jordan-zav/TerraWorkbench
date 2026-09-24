"""Cardinal sin(x)/x interpolation of archaeological survey grids."""

import json
import numpy as np
from qgis.core import QgsProcessingException, QgsProcessingParameterNumber
from .base import RasterAlgorithmBase
from ..gridding_methods import SincGridder
from ..qgis_compat import PROCESSING_NUMBER_INTEGER
from ..raster_io import nodata_mask, write_geotiff


class SincInterpolationAlgorithm(RasterAlgorithmBase):
    processing_domain = "SPACE / GRID"

    def name(self):
        return "sinc_interpolation"

    def displayName(self):
        return self.tr("Sin(x)/x grid interpolation")

    def group(self):
        return self.tr("Survey data preparation")

    def groupId(self):
        return "survey_data_preparation"

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        for key, label, value, maximum in (
            ("FACTOR_X", "Interpolation expansion X", 2, 16),
            ("FACTOR_Y", "Interpolation expansion Y", 2, 16),
            ("LOBES", "Sinc support lobes", 4, 32),
        ):
            self.addParameter(QgsProcessingParameterNumber(
                key, self.tr(label), type=PROCESSING_NUMBER_INTEGER,
                defaultValue=value, minValue=1, maxValue=maximum))

    def shortHelpString(self):
        return self.tr("Interpolate a regular grid using separable windowed sin(x)/x. Original sample centres are retained. Missing support remains NoData. Expansion adds samples, not measured resolution. Independent Lanczos implementation; Geoplot equivalence is not certified.")

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context, require_projected=True)
        gt = grid.geotransform
        if gt[2] or gt[4] or gt[1] <= 0 or gt[5] >= 0:
            raise QgsProcessingException("A north-up raster with positive X spacing is required.")
        fx = self.parameterAsInt(parameters, "FACTOR_X", context)
        fy = self.parameterAsInt(parameters, "FACTOR_Y", context)
        lobes = self.parameterAsInt(parameters, "LOBES", context)
        rows, cols = grid.values.shape
        nx, ny = (cols-1)*fx+1, (rows-1)*fy+1
        if nx*ny > 10_000_000:
            raise QgsProcessingException("Sinc output exceeds 10 million cells; reduce expansion.")
        x = gt[0]+(np.arange(cols)+.5)*gt[1]
        y = gt[3]+(np.arange(rows)+.5)*gt[5]
        xx, yy = np.meshgrid(x, y)
        valid = ~nodata_mask(grid)
        try:
            model = SincGridder(np.column_stack((xx[valid], yy[valid])),
                               grid.values[valid], (gt[1], -gt[5]), radius=lobes)
            result = np.empty((ny, nx))
            xo = x[0]+np.arange(nx)*gt[1]/fx
            yo = y[0]+np.arange(ny)*gt[5]/fy
            for row in range(ny):
                result[row] = model.evaluate(np.column_stack((xo, np.full(nx, yo[row]))), feedback.isCanceled)
                feedback.setProgress(100*(row+1)/ny)
        except InterruptedError:
            return {}
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        grid.geotransform = (x[0]-gt[1]/fx/2, gt[1]/fx, 0,
                             y[0]-gt[5]/fy/2, 0, gt[5]/fy)
        grid.metadata = dict(grid.metadata, TW_PROCESS=self.name(),
                             TW_SINC=json.dumps(model.metadata),
                             TW_EXPANSION=f"{fx},{fy}")
        output = self.output_path(parameters, context)
        write_geotiff(output, result, grid, self.displayName(), output_nodata=np.nan)
        return {self.OUTPUT: output}
