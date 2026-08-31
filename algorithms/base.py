"""Shared Processing algorithm foundations."""

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBand,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)

from ..raster_io import read_raster
from ..i18n import translate
from ..crs_utils import require_metre_projected_crs


class RasterAlgorithmBase(QgsProcessingAlgorithm):
    """Base class for one-band raster algorithms."""

    INPUT = "INPUT"
    BAND = "BAND"
    OUTPUT = "OUTPUT"

    def add_raster_parameters(self):
        self.addParameter(
            QgsProcessingParameterRasterLayer(self.INPUT, self.tr("Input raster"))
        )
        self.addParameter(
            QgsProcessingParameterBand(
                self.BAND,
                self.tr("Input band"),
                parentLayerParameterName=self.INPUT,
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT, self.tr("Output GeoTIFF")
            )
        )

    def input_grid(
        self, parameters, context, require_projected=False, require_metric=False
    ):
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        if layer is None or not layer.isValid():
            raise QgsProcessingException("A valid input raster is required.")
        if require_projected and layer.crs().isGeographic():
            raise QgsProcessingException(
                "This transformation requires a projected CRS. Reproject the raster "
                "to a suitable metric CRS before processing."
            )
        if require_metric:
            try:
                require_metre_projected_crs(
                    layer.crs().toWkt(), "This physical transformation"
                )
            except ValueError as error:
                raise QgsProcessingException(str(error)) from error
        band = self.parameterAsInt(parameters, self.BAND, context)
        return read_raster(layer, band)

    def output_path(self, parameters, context):
        return self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

    def group(self):
        return self.tr("Gravity and magnetics")

    def groupId(self):
        return "gravity_magnetics"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return translate(text)
