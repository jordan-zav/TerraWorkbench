"""Grid geophysical survey points into a regular projected GeoTIFF."""

from __future__ import annotations

import math

import numpy as np
from osgeo import gdal
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
)

from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..i18n import translate
from ..basic_processing import ThinPlateGridder


class SurveyPointGriddingAlgorithm(QgsProcessingAlgorithm):
    processing_domain = "SPACE / POINTS"
    implementation_details = (
        ("Numerical backend", "SciPy cKDTree / RBFInterpolator thin_plate_spline, NumPy"),
        ("Host and raster I/O", "QGIS Processing and GDAL"),
        ("Compatibility", "TPS is not RANGRID; local TPS is an approximation, not a global minimum-curvature solution"),
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
                )],
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_SIZE,
                self.tr(
                    "Cell size in output CRS units (0 = automatic from point density)"
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
            "TPS_SMOOTHING", self.tr("TPS smoothing (normalized coordinates; not tension)"),
            type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            "TPS_NEIGHBORS", self.tr("Local TPS neighbors"),
            type=PROCESSING_NUMBER_INTEGER, defaultValue=64, minValue=3, maxValue=512))
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

        coordinates = []
        values = []
        total = source.featureCount()
        for index, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                return {}
            geometry = feature.geometry()
            if not geometry or geometry.isEmpty():
                continue
            point = geometry.centroid().asPoint()
            if transform is not None:
                point = transform.transform(point)
            try:
                value = float(feature[value_field])
            except (TypeError, ValueError):
                continue
            if (
                math.isfinite(point.x())
                and math.isfinite(point.y())
                and math.isfinite(value)
            ):
                coordinates.append((point.x(), point.y()))
                values.append(value)
            if total > 0 and index % 10000 == 0:
                feedback.setProgress(min(20.0, 20.0 * index / total))
        if len(values) < 3:
            raise QgsProcessingException(
                "At least three finite survey points are required."
            )
        coordinates = np.asarray(coordinates, dtype=np.float64)
        values = np.asarray(values, dtype=np.float64)
        minimum = coordinates.min(axis=0)
        maximum = coordinates.max(axis=0)
        width, height = maximum - minimum
        if width <= 0.0 or height <= 0.0:
            raise QgsProcessingException(
                "The survey points do not span a two-dimensional area."
            )

        cell_size = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        if cell_size <= 0.0:
            cell_size = math.sqrt(width * height / len(values))
            feedback.pushInfo(
                f"Automatic cell size from survey density: {cell_size:.3f} CRS units."
            )
        columns = int(math.ceil(width / cell_size)) + 1
        rows = int(math.ceil(height / cell_size)) + 1
        cell_count = rows * columns
        if cell_count > 100_000_000:
            raise QgsProcessingException(
                f"Requested grid has {cell_count:,} cells. Increase cell size to stay below 100 million."
            )
        radius = self.parameterAsDouble(parameters, self.SEARCH_RADIUS, context)
        query_radius = np.inf if radius <= 0.0 else radius
        method = self.parameterAsInt(parameters, self.METHOD, context)
        if method not in (0, 1, 2, 3):
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
        tree = cKDTree(coordinates)
        tps = None
        smoothing = self.parameterAsDouble(parameters, "TPS_SMOOTHING", context)
        if method >= 2:
            tps_neighbors = self.parameterAsInt(parameters, "TPS_NEIGHBORS", context) if method == 3 else 0
            try:
                tps = ThinPlateGridder(coordinates, values, smoothing, tps_neighbors)
            except (ValueError, np.linalg.LinAlgError) as error:
                raise QgsProcessingException(str(error)) from error
            feedback.pushInfo(f"TPS: {tps.duplicate_count} coincident observations averaged; "
                              f"neighbors={tps.neighbors or 'global'}; normalized smoothing={smoothing}. "
                              "Search radius masks output by nearest-point distance; it does not restrict TPS fitting points.")
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
                "INTERPOLATION": ("IDW", "Nearest neighbor", "Global thin-plate spline", "Local thin-plate spline approximation")[method],
                "CELL_SIZE": str(cell_size),
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
        band = dataset.GetRasterBand(1)
        nodata = -3.4028234663852886e38
        band.SetNoDataValue(nodata)
        x_centers = minimum[0] + np.arange(columns) * cell_size
        block_rows = 128
        for row_start in range(0, rows, block_rows):
            if feedback.isCanceled():
                dataset = None
                return {}
            row_end = min(rows, row_start + block_rows)
            y_centers = maximum[1] - np.arange(row_start, row_end) * cell_size
            grid_x, grid_y = np.meshgrid(x_centers, y_centers)
            query = np.column_stack((grid_x.ravel(), grid_y.ravel()))
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
                band.WriteArray(result.reshape(row_end - row_start, columns).astype(np.float32), 0, row_start)
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
            band.WriteArray(result.reshape(row_end - row_start, columns), 0, row_start)
            feedback.setProgress(20.0 + 80.0 * row_end / rows)
        band.SetDescription(f"Gridded {value_field}")
        band.FlushCache()
        dataset.FlushCache()
        dataset = None
        return {self.OUTPUT: output}

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
            "Interpolates a numeric channel from survey points to a regular GeoTIFF. "
            "Geographic inputs are automatically reprojected to the local WGS 84 UTM zone "
            "unless a projected CRS is chosen. Cell size 0 estimates spacing from point "
            "density. Search radius 0 fills the complete bounding rectangle, which is ready "
            "for FFT filters but extrapolates at edges and across unsampled gaps. Set a finite "
            "radius to constrain extrapolation and leave unsupported cells as NoData. IDW is "
            "deterministic and does not perform line leveling."
        ) + "\n\n" + self.tr(
            "Global thin-plate spline minimizes bending with an affine polynomial and is limited to 2000 unique points. Local TPS uses a configurable neighborhood and is not a global minimum-curvature solution. Coincident values are averaged. Smoothing uses isotropically normalized coordinates; it is not tension. Search radius only masks TPS output by distance to the nearest observation. No RANGRID equivalence is claimed."
        ) + "\n\n" + self.tr(
            "Numerical backend: NumPy and SciPy (RBFInterpolator, cKDTree). Raster I/O: QGIS and GDAL."
        )
