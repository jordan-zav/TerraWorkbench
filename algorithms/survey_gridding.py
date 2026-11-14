"""Grid geophysical survey points into a regular projected GeoTIFF."""

from __future__ import annotations

import math
import json

import numpy as np
from osgeo import gdal
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsProcessing,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsVariantUtils,
    QgsWkbTypes,
    QgsProcessingException,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
)

from .base import ProcessingAlgorithmBase

from ..qgis_plugin.qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..ui.i18n import translate
from ..compat.basic_processing import ThinPlateGridder
from ..terraworkbench_core.gridding_methods import (
    BidirectionalGridder, MinimumCurvatureGridder, MinimumCurvatureNodeLimitError, SincGridder,
    _MULTILEVEL_NODE_LIMIT, minimum_curvature_cell_size, suggest_flight_cell_size,
)


class SurveyPointGriddingAlgorithm(ProcessingAlgorithmBase):
    processing_domain = "SPACE / POINTS"
    implementation_details = (
        ("Numerical backend", "NumPy / SciPy cKDTree, multilevel minimum-curvature and windowed sinc solvers"),
        ("Host and raster I/O", "QGIS Processing and GDAL"),
    )
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    TARGET_CRS = "TARGET_CRS"
    METHOD = "METHOD"
    CELL_SIZE = "CELL_SIZE"
    POWER = "POWER"
    NEIGHBORS = "NEIGHBORS"
    SEARCH_RADIUS = "SEARCH_RADIUS"
    OUTPUT = "OUTPUT"
    ALLOW_LARGE_GRID = "ALLOW_LARGE_MINIMUM_CURVATURE_GRID"
    NODE_LIMIT_MESSAGE = (
        "Minimum curvature needs {nodes:,} working nodes; the limit is {limit:,}. "
        "Try a cell size of at least {size:.3g} in CRS units, or reduce the extent."
    )

    def createCustomParametersWidget(self, parent=None):
        from ..ui.survey_gridding_dialog import SurveyGriddingDialog

        return SurveyGriddingDialog(self, parent=parent)

    def _node_limit_message(self, nodes, size):
        return self.tr(self.NODE_LIMIT_MESSAGE).format(
            nodes=nodes, limit=_MULTILEVEL_NODE_LIMIT, size=size
        ) + " " + self.tr("To proceed, enable Allow large minimum-curvature grids in Advanced parameters.")

    def name(self):
        return "grid_survey_points"

    def displayName(self):
        return self.tr("Grid survey points to GeoTIFF")

    def group(self):
        return self.tr("Survey data preparation")

    def groupId(self):
        return "survey_data_preparation"

    def createInstance(self):
        return type(self)()

    def tr(self, text):
        return translate(text)

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, self.tr("Survey point layer")
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.VALUE_FIELD,
                self.tr("Numeric channel to grid"),
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                self.tr(
                    "Projected output CRS (blank = source CRS or automatic local UTM)"
                ),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.METHOD,
                self.tr("Interpolation method"),
                options=[self.tr(label) for label in (
                    "Inverse distance weighting (IDW)", "Nearest neighbor",
                    "Minimum curvature (global thin-plate spline)",
                    "Local thin-plate spline (approximation)",
                    "Sinc(x)/x (windowed 2D interpolator)",
                    "Minimum curvature (multilevel solver)", "Bidirectional flight-line gridding",
                )],
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_SIZE,
                self.tr(
                    "Cell size in output CRS units (0 = automatic)"
                ),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.POWER,
                self.tr("IDW power"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=2.0,
                minValue=0.1,
                maxValue=20.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.NEIGHBORS,
                self.tr("Maximum neighbors"),
                type=PROCESSING_NUMBER_INTEGER,
                defaultValue=12,
                minValue=1,
                maxValue=256,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SEARCH_RADIUS,
                self.tr("Search radius (0 = unlimited, complete FFT-ready rectangle)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.0,
                minValue=0.0,
            )
        )
        self.addParameter(QgsProcessingParameterNumber(
            "DUMMY_VALUE", self.tr("Numeric dummy value (optional)"),
            type=PROCESSING_NUMBER_DOUBLE, optional=True))
        self.addParameter(QgsProcessingParameterField(
            "LINE_FIELD", self.tr("Flight-line ID field"), parentLayerParameterName=self.INPUT,
            optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            "LINE_SPACING_DIVISOR", self.tr("Automatic cell size: fraction of flight-line spacing"),
            options=["1/4", "1/5"], defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            "CROSS_METHOD", self.tr("Cross-line interpolation"),
            options=[self.tr("Piecewise linear"), self.tr("Shape-preserving cubic (PCHIP)")], defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            "LINE_TREND", self.tr("Remove and restore a planar trend"), defaultValue=False))
        for key, label in (
            ("LINE_GAP", "Maximum gap between flight lines (0 = unlimited)"),
            ("SAMPLE_GAP", "Maximum gap along a flight line (0 = unlimited)"),
            ("LINE_BLANKING", "Bidirectional blanking distance (0 = disabled)"),
        ):
            self.addParameter(QgsProcessingParameterNumber(
                key, self.tr(label), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "BOUNDARY", self.tr("Survey coverage polygon (survey_boundary)"),
            types=[QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            "RANGRID_AVERAGE", self.tr("Average observations within each cell before minimum curvature"),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            "TPS_SMOOTHING", self.tr("TPS smoothing (normalized coordinates; not tension)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "TPS_NEIGHBORS", self.tr("Local TPS neighbors"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=64, minValue=3, maxValue=512))
        allow_large_grid = QgsProcessingParameterBoolean(
            self.ALLOW_LARGE_GRID, self.tr("Allow large minimum-curvature grids"),
            defaultValue=False,
        )
        allow_large_grid.setFlags(
            allow_large_grid.flags() | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(allow_large_grid)
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_TOLERANCE", self.tr("Minimum-curvature tolerance (channel units)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.01258, minValue=1e-12))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_PASS_TOLERANCE", self.tr("Minimum-curvature pass tolerance (%)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=99.0, minValue=0.1, maxValue=100.0))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_MAX_ITERATIONS", self.tr("Minimum-curvature maximum iterations"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=100, minValue=1, maxValue=10000))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_TENSION", self.tr("Minimum-curvature internal tension (0–1)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterEnum(
            "RANGRID_COARSE_GRID", self.tr("Minimum-curvature starting coarse grid"),
            options=["16", "8", "4", "2", "1"], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_SEARCH_RADIUS", self.tr("Minimum-curvature starting search radius"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_BLANKING", self.tr("Minimum-curvature blanking distance"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_DESAMPLE", self.tr("Minimum-curvature desample factor"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=1, minValue=1, maxValue=64))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_WEIGHT_POWER", self.tr("Minimum-curvature weighting power"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=2.0, minValue=0.1, maxValue=20.0))
        self.addParameter(QgsProcessingParameterNumber(
            "RANGRID_WEIGHT_SLOPE", self.tr("Minimum-curvature weighting slope"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0, maxValue=1000.0))
        self.addParameter(QgsProcessingParameterNumber(
            "SINC_RADIUS", self.tr("Sinc(x)/x support radius (sample spacings)"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=4, minValue=1, maxValue=32))
        self.addParameter(QgsProcessingParameterNumber(
            "SINC_SPACING", self.tr("Sinc original X sample spacing (required)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "SINC_SPACING_Y", self.tr("Sinc original Y spacing (0 = X spacing)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "SINC_BLANKING", self.tr("Sinc(x)/x blanking distance"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT, self.tr("Gridded GeoTIFF")
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("A valid survey point layer is required.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        if source.fields().indexOf(value_field) < 0:
            raise QgsProcessingException(f"Channel does not exist: {value_field}")
        source_crs = source.sourceCrs()
        target_crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        if not target_crs.isValid():
            if not source_crs.isValid():
                raise QgsProcessingException("Choose a projected output CRS.")
            target_crs = self._automatic_target_crs(source, source_crs)
        if target_crs.isGeographic():
            raise QgsProcessingException(
                "Gridding requires a projected CRS with linear units. Choose a suitable UTM CRS."
            )
        transform = None
        if source_crs.isValid() and source_crs != target_crs:
            transform = QgsCoordinateTransform(
                source_crs, target_crs, context.transformContext()
            )

        method = self.parameterAsInt(parameters, self.METHOD, context)
        line_field = self.parameterAsString(parameters, "LINE_FIELD", context)
        if method == 6 and not line_field:
            raise QgsProcessingException(self.tr("Choose a flight-line ID field for bidirectional gridding."))
        if line_field and source.fields().indexOf(line_field) < 0:
            raise QgsProcessingException(self.tr("The flight-line ID field does not exist."))
        dummy = (self.parameterAsDouble(parameters, "DUMMY_VALUE", context)
                 if parameters.get("DUMMY_VALUE") not in (None, "") else None)
        blocks = []
        block = np.empty((65536, 4 if line_field else 3))
        used = 0
        line_codes = {}
        total = source.featureCount()
        request = QgsFeatureRequest().setSubsetOfAttributes(
            [value_field, line_field] if line_field else [value_field], source.fields())
        for index, feature in enumerate(source.getFeatures(request)):
            if feedback.isCanceled():
                return {}
            geometry = feature.geometry()
            if not geometry or geometry.isEmpty():
                continue
            point = geometry.asPoint() if geometry.type() == QgsWkbTypes.PointGeometry and not geometry.isMultipart() else geometry.centroid().asPoint()
            if transform is not None:
                point = transform.transform(point)
            try:
                value = float(feature[value_field])
            except (TypeError, ValueError):
                continue
            if math.isfinite(point.x()) and math.isfinite(point.y()) and math.isfinite(value) and value != dummy:
                block[used, :3] = point.x(), point.y(), value
                if line_field:
                    label = feature[line_field]
                    if QgsVariantUtils.isNull(label):
                        continue
                    block[used, 3] = line_codes.setdefault(label, len(line_codes))
                used += 1
                if used == len(block):
                    blocks.append(block)
                    block = np.empty_like(block)
                    used = 0
            if total > 0 and index % 10000 == 0:
                feedback.setProgress(min(20.0, 20.0 * index / total))
        blocks.append(block[:used])
        observations = np.concatenate(blocks)
        del blocks, block
        if len(observations) < 3:
            raise QgsProcessingException("At least three finite survey points are required.")
        coordinates = np.ascontiguousarray(observations[:, :2])
        values = observations[:, 2].copy()
        line_ids = observations[:, 3].astype(np.int32) if line_field else None
        del observations
        try:
            bidirectional = BidirectionalGridder(
                coordinates, values, line_ids,
                trend=self.parameterAsBool(parameters, "LINE_TREND", context),
                cross_method=("linear", "pchip")[self.parameterAsInt(parameters, "CROSS_METHOD", context)],
                blanking_distance=self.parameterAsDouble(parameters, "LINE_BLANKING", context),
                max_line_gap=self.parameterAsDouble(parameters, "LINE_GAP", context),
                max_sample_gap=self.parameterAsDouble(parameters, "SAMPLE_GAP", context),
            ) if method == 6 else None
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        minimum = coordinates.min(axis=0)
        maximum = coordinates.max(axis=0)
        width, height = maximum - minimum
        if width <= 0.0 or height <= 0.0:
            raise QgsProcessingException(
                "The survey points do not span a two-dimensional area."
            )

        cell_size = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        if cell_size <= 0.0:
            divisor = 4 + self.parameterAsInt(parameters, "LINE_SPACING_DIVISOR", context)
            try:
                if bidirectional is not None:
                    cell_size = bidirectional.line_spacing/divisor
                elif line_ids is not None:
                    cell_size = suggest_flight_cell_size(coordinates, line_ids, divisor)
                else:
                    cell_size = math.sqrt(width * height / len(values))
            except ValueError as error:
                raise QgsProcessingException(str(error)) from error
            feedback.pushInfo(self.tr("Automatic cell size: {size:.3f} CRS units.").format(size=cell_size))
        columns = int(math.ceil(width / cell_size)) + 1
        rows = int(math.ceil(height / cell_size)) + 1
        cell_count = rows * columns
        allow_large_grid = self.parameterAsBool(parameters, self.ALLOW_LARGE_GRID, context)
        working_nodes = (rows+4)*(columns+4)
        if method == 5 and working_nodes > _MULTILEVEL_NODE_LIMIT and not allow_large_grid:
            raise QgsProcessingException(self._node_limit_message(
                working_nodes, minimum_curvature_cell_size(width, height)
            ))
        if cell_count > 100_000_000:
            raise QgsProcessingException(
                f"Requested grid has {cell_count:,} cells. Increase cell size to stay below 100 million."
            )
        radius = self.parameterAsDouble(parameters, self.SEARCH_RADIUS, context)
        query_radius = np.inf if radius <= 0.0 else radius
        if method not in range(7):
            raise QgsProcessingException("Unknown interpolation method.")
        neighbors = min(
            self.parameterAsInt(parameters, self.NEIGHBORS, context), len(values)
        )
        power = self.parameterAsDouble(parameters, self.POWER, context)

        try:
            from scipy.spatial import cKDTree
        except ImportError as error:
            raise QgsProcessingException(
                "SciPy is required for survey gridding. Use TerraWorkbench's built-in dependency manager."
            ) from error
        tree = cKDTree(coordinates) if method in (0, 1, 2, 3) else None
        tps = None
        minimum_curvature = None
        sinc = None
        smoothing = self.parameterAsDouble(parameters, "TPS_SMOOTHING", context)
        if method in (2, 3):
            tps_neighbors = self.parameterAsInt(parameters, "TPS_NEIGHBORS", context) if method == 3 else 0
            try:
                tps = ThinPlateGridder(coordinates, values, smoothing, tps_neighbors)
            except (ValueError, np.linalg.LinAlgError) as error:
                raise QgsProcessingException(str(error)) from error
            feedback.pushInfo(f"TPS: {tps.duplicate_count} coincident observations averaged; "
                              f"neighbors={tps.neighbors or 'global'}; normalized smoothing={smoothing}. "
                              "Search radius masks output by nearest-point distance; it does not restrict TPS fitting points.")
        if method == 5:
            coarse_options = (16, 8, 4, 2, 1)
            coarse_index = self.parameterAsInt(parameters, "RANGRID_COARSE_GRID", context)
            coarse_grid = coarse_options[max(0, min(coarse_index, len(coarse_options) - 1))]
            rangrid_radius = self.parameterAsDouble(parameters, "RANGRID_SEARCH_RADIUS", context)
            try:
                minimum_curvature = MinimumCurvatureGridder(
                    coordinates,
                    values,
                    cell_size,
                    average_cells=self.parameterAsBool(parameters, "RANGRID_AVERAGE", context),
                    blanking_distance=self.parameterAsDouble(parameters, "RANGRID_BLANKING", context),
                    desample_factor=self.parameterAsInt(parameters, "RANGRID_DESAMPLE", context),
                    search_radius=rangrid_radius,
                    weighting_power=self.parameterAsDouble(parameters, "RANGRID_WEIGHT_POWER", context),
                    weighting_slope=self.parameterAsDouble(parameters, "RANGRID_WEIGHT_SLOPE", context),
                    tolerance=self.parameterAsDouble(parameters, "RANGRID_TOLERANCE", context),
                    pass_tolerance=self.parameterAsDouble(parameters, "RANGRID_PASS_TOLERANCE", context),
                    max_iterations=self.parameterAsInt(parameters, "RANGRID_MAX_ITERATIONS", context),
                    tension=self.parameterAsDouble(parameters, "RANGRID_TENSION", context),
                    coarse_grid=coarse_grid,
                    allow_large_grid=allow_large_grid,
                )
            except ValueError as error:
                raise QgsProcessingException(str(error)) from error
        if method == 4:
            sinc_spacing = self.parameterAsDouble(parameters, "SINC_SPACING", context)
            if sinc_spacing <= 0.0:
                raise QgsProcessingException("Specify the original sample spacing for sinc, independently of output cell size.")
            try:
                sinc = SincGridder(
                    coordinates,
                    values,
                    (sinc_spacing, self.parameterAsDouble(parameters, "SINC_SPACING_Y", context) or sinc_spacing),
                    radius=self.parameterAsInt(parameters, "SINC_RADIUS", context),
                    blanking_distance=self.parameterAsDouble(parameters, "SINC_BLANKING", context),
                )
            except ValueError as error:
                raise QgsProcessingException(str(error)) from error
            feedback.pushInfo(
                "Sinc(x)/x: windowed two-dimensional interpolator; "
                f"spacing={sinc_spacing:g}, radius={sinc.radius} sample spacings."
            )
        x_centers = minimum[0] + np.arange(columns) * cell_size
        y_ascending = (maximum[1] - np.arange(rows) * cell_size)[::-1]
        boundary = self._coverage_mask(parameters, context, target_crs)
        solved = None
        try:
            if minimum_curvature is not None:
                solved = minimum_curvature.grid(
                    x_centers, y_ascending, canceled=feedback.isCanceled,
                    progress=lambda fraction: feedback.setProgress(20.0 + 60.0 * fraction),
                )[::-1]
            elif bidirectional is not None:
                solved = bidirectional.grid(x_centers, y_ascending, canceled=feedback.isCanceled)[::-1]
        except InterruptedError:
            return {}
        except MinimumCurvatureNodeLimitError as error:
            raise QgsProcessingException(self._node_limit_message(
                error.nodes, error.suggested_cell_size
            )) from error
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        dataset = gdal.GetDriverByName("GTiff").Create(
            output,
            columns,
            rows,
            1,
            gdal.GDT_Float32,
            options=[
                "TILED=YES",
                "COMPRESS=DEFLATE",
                "PREDICTOR=3",
                "BIGTIFF=IF_SAFER",
            ],
        )
        if dataset is None:
            raise QgsProcessingException("Could not create the output GeoTIFF.")
        origin_x = minimum[0] - 0.5 * cell_size
        origin_y = maximum[1] + 0.5 * cell_size
        dataset.SetGeoTransform((origin_x, cell_size, 0.0, origin_y, 0.0, -cell_size))
        dataset.SetProjection(target_crs.toWkt())
        dataset.SetMetadata(
            {
                "SOURCE_FORMAT": "QGIS survey point layer",
                "VALUE_FIELD": value_field,
                "INTERPOLATION": (
                    "IDW",
                    "Nearest neighbor",
                    "Global thin-plate spline",
                    "Local thin-plate spline approximation",
                    "Sinc(x)/x windowed 2D interpolator",
                    "Minimum curvature (multilevel)",
                    "Bidirectional flight-line gridding",
                )[method],
                "CELL_SIZE": str(cell_size),
                "DUMMY_VALUE": "" if dummy is None else str(dummy),
                "SEARCH_RADIUS": "unlimited" if radius <= 0.0 else str(radius),
                "NEIGHBORS": str(neighbors),
                "IDW_POWER": str(power),
            }
        )
        if tps is not None:
            import scipy
            dataset.SetMetadataItem("TPS_BACKEND", "SciPy RBFInterpolator " + scipy.__version__)
            dataset.SetMetadataItem("TPS_SMOOTHING", str(smoothing))
            dataset.SetMetadataItem("TPS_NEIGHBORS", str(tps.neighbors or "global"))
            dataset.SetMetadataItem("TPS_COORDINATE_SCALE", str(tps.scale))
            dataset.SetMetadataItem("TPS_DUPLICATES_AVERAGED", str(tps.duplicate_count))
            dataset.SetMetadataItem("TPS_RADIUS_MEANING", "Output nearest-point distance mask only")
        dataset.SetMetadataItem("COVERAGE_MASK", str(boundary is not None))
        if minimum_curvature is not None:
            dataset.SetMetadataItem("RANGRID_ALGORITHM", "Independent multilevel minimum-curvature solver")
            dataset.SetMetadataItem("RANGRID_TOLERANCE", str(minimum_curvature.tolerance))
            dataset.SetMetadataItem("RANGRID_PASS_TOLERANCE", str(minimum_curvature.pass_tolerance))
            dataset.SetMetadataItem("RANGRID_MAX_ITERATIONS", str(minimum_curvature.max_iterations))
            dataset.SetMetadataItem("RANGRID_TENSION", str(minimum_curvature.tension))
            dataset.SetMetadataItem("RANGRID_COARSE_GRID", str(minimum_curvature.coarse_grid))
            dataset.SetMetadataItem("RANGRID_SEARCH_RADIUS", str(minimum_curvature.search_radius))
            dataset.SetMetadataItem("RANGRID_BLANKING", str(minimum_curvature.blanking_distance))
            dataset.SetMetadataItem("RANGRID_DESAMPLE", str(minimum_curvature.desample_factor))
            dataset.SetMetadataItem("RANGRID_WEIGHT_POWER", str(minimum_curvature.weighting_power))
            dataset.SetMetadataItem("RANGRID_WEIGHT_SLOPE", str(minimum_curvature.weighting_slope))
            dataset.SetMetadataItem("RANGRID_PROPRIETARY_EQUIVALENCE", "false")
        if sinc is not None:
            dataset.SetMetadataItem("SINC_ALGORITHM", "Windowed two-dimensional sinc(x)/x interpolator")
            dataset.SetMetadataItem("SINC_SPACING_X", str(sinc.spacing[0]))
            dataset.SetMetadataItem("SINC_SPACING_Y", str(sinc.spacing[1]))
            dataset.SetMetadataItem("SINC_RADIUS", str(sinc.radius))
            dataset.SetMetadataItem("SINC_BLANKING", str(sinc.blanking_distance))
        if bidirectional is not None:
            dataset.SetMetadataItem("FLIGHT_LINE_SPACING", str(bidirectional.line_spacing))
            dataset.SetMetadataItem("CROSS_METHOD", bidirectional.cross_method)
            dataset.SetMetadataItem("LINE_TREND", str(bidirectional.trend))
            dataset.SetMetadataItem("LINE_BLANKING", str(bidirectional.blanking_distance))
            dataset.SetMetadataItem("MAX_LINE_GAP", str(bidirectional.max_line_gap))
            dataset.SetMetadataItem("MAX_SAMPLE_GAP", str(bidirectional.max_sample_gap))
        band = dataset.GetRasterBand(1)
        nodata = -3.4028234663852886e38
        band.SetNoDataValue(nodata)
        if minimum_curvature is not None:
            dataset.SetMetadataItem("TW_MINIMUM_CURVATURE", json.dumps(minimum_curvature.metadata))
            if not minimum_curvature.metadata["converged"]:
                feedback.reportError("Minimum curvature reached the iteration limit without meeting convergence tolerance.", fatalError=False)
            feedback.pushInfo(f"Minimum-curvature levels: {minimum_curvature.metadata['levels']}")
        block_rows = max(1, min(128, 65536 // columns))
        for row_start in range(0, rows, block_rows):
            if feedback.isCanceled():
                dataset = None
                return {}
            row_end = min(rows, row_start + block_rows)
            y_centers = maximum[1] - np.arange(row_start, row_end) * cell_size
            grid_x, grid_y = np.meshgrid(x_centers, y_centers)
            query = np.column_stack((grid_x.ravel(), grid_y.ravel()))
            if solved is not None:
                result = solved[row_start:row_end].ravel()
                if boundary is not None:
                    result = np.where(boundary(query), result, np.nan)
                if np.any(np.abs(result[np.isfinite(result)]) > np.finfo(np.float32).max):
                    dataset = None
                    raise QgsProcessingException("Interpolation output exceeds Float32 range.")
                result = np.where(np.isfinite(result), result, nodata).astype(np.float32)
                band.WriteArray(result.reshape(row_end - row_start, columns), 0, row_start)
                feedback.setProgress(80.0 + 20.0 * row_end / rows)
                continue
            if tps is not None:
                distances, _ = tree.query(query, k=1)
                supported = distances <= query_radius
                result = np.full(len(query), nodata, dtype=np.float64)
                # Bound TPS evaluation memory independently of raster width.
                indices = np.flatnonzero(supported)
                try:
                    for start in range(0, len(indices), 2048):
                        if feedback.isCanceled():
                            dataset = None
                            return {}
                        selected = indices[start:start + 2048]
                        result[selected] = tps(query[selected])
                except ValueError as error:
                    dataset = None
                    raise QgsProcessingException(str(error)) from error
                if np.any(np.abs(result[supported]) > np.finfo(np.float32).max):
                    dataset = None
                    raise QgsProcessingException("TPS output exceeds Float32 range; rescale the input.")
                if boundary is not None:
                    result[~boundary(query)] = nodata
                band.WriteArray(result.reshape(row_end - row_start, columns).astype(np.float32), 0, row_start)
                feedback.setProgress(20.0 + 80.0 * row_end / rows)
                continue
            if sinc is not None:
                try:
                    result = sinc.evaluate(query, canceled=feedback.isCanceled)
                except InterruptedError:
                    dataset = None
                    return {}
                if np.any(np.abs(result[np.isfinite(result)]) > np.finfo(np.float32).max):
                    dataset = None
                    raise QgsProcessingException("Interpolation output exceeds Float32 range.")
                result = np.where(np.isfinite(result), result, nodata).astype(np.float32)
                if boundary is not None:
                    result[~boundary(query)] = nodata
                band.WriteArray(result.reshape(row_end - row_start, columns), 0, row_start)
                feedback.setProgress(20.0 + 80.0 * row_end / rows)
                continue
            k = 1 if method == 1 else neighbors
            distances, indices = tree.query(
                query, k=k, distance_upper_bound=query_radius, workers=-1
            )
            if k == 1:
                valid = np.isfinite(distances) & (indices < len(values))
                result = np.full(query.shape[0], nodata, dtype=np.float32)
                result[valid] = values[indices[valid]]
            else:
                distances = np.asarray(distances)
                indices = np.asarray(indices)
                valid = np.isfinite(distances) & (indices < len(values))
                safe_indices = np.where(valid, indices, 0)
                exact = valid & (distances <= np.finfo(float).eps)
                weights = np.zeros_like(distances, dtype=np.float64)
                weights[valid & ~exact] = 1.0 / distances[valid & ~exact] ** power
                weighted = np.sum(weights * values[safe_indices], axis=1)
                weight_sum = np.sum(weights, axis=1)
                result = np.full(query.shape[0], nodata, dtype=np.float64)
                usable = weight_sum > 0.0
                result[usable] = weighted[usable] / weight_sum[usable]
                exact_rows = np.any(exact, axis=1)
                if np.any(exact_rows):
                    first_exact = np.argmax(exact[exact_rows], axis=1)
                    exact_indices = safe_indices[exact_rows, first_exact]
                    result[exact_rows] = values[exact_indices]
                result = result.astype(np.float32)
            if boundary is not None:
                result[~boundary(query)] = nodata
            band.WriteArray(result.reshape(row_end - row_start, columns), 0, row_start)
            feedback.setProgress(20.0 + 80.0 * row_end / rows)
        band.SetDescription(f"Gridded {value_field}")
        band.FlushCache()
        dataset.FlushCache()
        dataset = None
        return {self.OUTPUT: output}

    def _coverage_mask(self, parameters, context, target_crs):
        from qgis.core import QgsGeometry, QgsPointXY

        source = self.parameterAsSource(parameters, "BOUNDARY", context)
        if source is None:
            return None
        if not source.sourceCrs().isValid():
            raise QgsProcessingException(self.tr("The coverage polygon needs a valid CRS."))
        transform = QgsCoordinateTransform(source.sourceCrs(), target_crs, context.transformContext())
        polygons = []
        for feature in source.getFeatures():
            polygon = feature.geometry()
            if not polygon.isEmpty():
                polygon.transform(transform)
                polygons.append(polygon)
        coverage = QgsGeometry.unaryUnion(polygons)
        if coverage.isEmpty():
            raise QgsProcessingException(self.tr("The coverage polygon is empty."))
        try:
            from shapely import from_wkb, intersects_xy, prepare
        except ImportError:
            engine = QgsGeometry.createGeometryEngine(coverage.constGet())
            engine.prepareGeometry()

            def intersects(query):
                # Bind the coverage so the engine's const geometry stays alive.
                point_factory = QgsGeometry.fromPointXY
                return np.fromiter(
                    (engine.intersects(point_factory(QgsPointXY(x, y)).constGet()) for x, y in query),
                    dtype=bool, count=len(query)) if not coverage.isEmpty() else np.zeros(len(query), dtype=bool)
        else:
            shape = from_wkb(bytes(coverage.asWkb()))
            prepare(shape)

            def intersects(query):
                return intersects_xy(shape, query[:, 0], query[:, 1])

        return intersects

    @staticmethod
    def _automatic_target_crs(source, source_crs):
        if not source_crs.isGeographic():
            return source_crs
        center = source.sourceExtent().center()
        longitude, latitude = center.x(), center.y()
        zone = max(1, min(60, int(math.floor((longitude + 180.0) / 6.0)) + 1))
        epsg = (32600 if latitude >= 0.0 else 32700) + zone
        return QgsCoordinateReferenceSystem(f"EPSG:{epsg}")

    def shortHelpString(self):
        return self.tr(
            "Grid a numeric survey channel in a projected CRS. With a flight-line ID field, "
            "automatic cell size uses one quarter or one fifth of the median line spacing. "
            "Without line IDs, automatic cell size uses point density. Bidirectional gridding "
            "requires roughly parallel flight lines. Select production lines and exclude tie lines. "
            "Distance limits and the coverage polygon write unsupported cells as NoData."
        )
