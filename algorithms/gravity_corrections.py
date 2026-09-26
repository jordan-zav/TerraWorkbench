"""Explicit gravity-reduction products for land surveys."""

from __future__ import annotations

import numpy as np
import json
from osgeo import osr
from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBand,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
)

from .base import RasterAlgorithmBase
from ..dependencies import import_harmonica
from ..gravity_corrections import (
    airy_moho_depth,
    complete_bouguer_anomaly,
    curvature_correction,
    free_air_anomaly,
    free_air_correction,
    gravity_disturbance,
    normal_gravity_grs80,
    simple_bouguer_anomaly,
)
from ..qgis_compat import PROCESSING_NUMBER_DOUBLE, PROCESSING_NUMBER_INTEGER
from ..raster_io import (
    nodata_mask,
    read_raster,
    restore_raster_order,
    to_regular_data_array,
    write_geotiff,
)
from ..isostasy import airy_prisms, airy_root_effect, airy_root_effect_fft


HARMONICA_GRAVITY_DETAILS = (
    ("Numerical backend", "TerraWorkbench gravity equations using NumPy"),
    ("Bouguer/prism backend", "Harmonica >=0.7,<0.8"),
    ("Host and raster I/O", "QGIS Processing and GDAL"),
)


class GravityCorrectionBase(RasterAlgorithmBase):
    """Shared utilities and metadata for gravity reductions."""
    processing_domain = "PHYSICAL MODEL / SPATIAL GRID"
    implementation_details = (
        ("Numerical backend", "TerraWorkbench gravity equations using NumPy"),
        ("Host and raster I/O", "QGIS Processing and GDAL"),
    )

    ELEVATION = "ELEVATION"
    ELEVATION_BAND = "ELEVATION_BAND"
    DENSITY_CRUST = "DENSITY_CRUST"
    DENSITY_WATER = "DENSITY_WATER"
    VERTICAL_GRADIENT = "VERTICAL_GRADIENT"

    def group(self):
        return self.tr("Gravity corrections and anomalies")

    def groupId(self):
        return "gravity_corrections"

    def add_elevation_parameters(self):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.ELEVATION,
                self.tr("Geometric elevation raster (m, ellipsoid referenced)"),
            )
        )
        self.addParameter(
            QgsProcessingParameterBand(
                self.ELEVATION_BAND,
                self.tr("Elevation band"),
                parentLayerParameterName=self.ELEVATION,
                defaultValue=1,
            )
        )

    def add_density_parameters(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DENSITY_CRUST,
                self.tr("Reduction/crust density (kg/m³)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=2670.0,
                minValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DENSITY_WATER,
                self.tr("Water density (kg/m³)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=1040.0,
                minValue=0.0,
            )
        )

    def add_vertical_gradient_parameter(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                self.VERTICAL_GRADIENT,
                self.tr("Free-air vertical gradient (mGal/m)"),
                type=PROCESSING_NUMBER_DOUBLE,
                defaultValue=0.3086,
                minValue=0.0,
            )
        )

    def elevation_grid(self, parameters, context):
        layer = self.parameterAsRasterLayer(parameters, self.ELEVATION, context)
        if layer is None or not layer.isValid():
            raise QgsProcessingException("A valid geometric elevation raster is required.")
        band = self.parameterAsInt(parameters, self.ELEVATION_BAND, context)
        return read_raster(layer, band)

    @staticmethod
    def require_matching(reference, other, label):
        same_shape = reference.values.shape == other.values.shape
        same_transform = np.allclose(
            reference.geotransform, other.geotransform, rtol=0.0, atol=1e-7
        )
        source = osr.SpatialReference()
        target = osr.SpatialReference()
        same_crs = bool(reference.projection and other.projection)
        if same_crs:
            same_crs = (
                source.ImportFromWkt(reference.projection) == 0
                and target.ImportFromWkt(other.projection) == 0
                and bool(source.IsSame(target))
            )
        if not (same_shape and same_transform and same_crs):
            raise QgsProcessingException(
                f"{label} must have the same extent, pixel grid and CRS as the input raster."
            )

    @staticmethod
    def latitude_grid(grid):
        rows, columns = grid.values.shape
        transform = grid.geotransform
        column_grid, row_grid = np.meshgrid(np.arange(columns), np.arange(rows))
        x = (
            transform[0]
            + (column_grid + 0.5) * transform[1]
            + (row_grid + 0.5) * transform[2]
        )
        y = (
            transform[3]
            + (column_grid + 0.5) * transform[4]
            + (row_grid + 0.5) * transform[5]
        )
        source = osr.SpatialReference()
        if not grid.projection or source.ImportFromWkt(grid.projection) != 0:
            raise QgsProcessingException("The raster needs a valid CRS to derive latitude.")
        target = osr.SpatialReference()
        target.ImportFromEPSG(4326)
        if hasattr(source, "SetAxisMappingStrategy"):
            source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        if source.IsSame(target):
            return y
        points = np.column_stack((x.ravel(), y.ravel())).tolist()
        converted = osr.CoordinateTransformation(source, target).TransformPoints(points)
        return np.asarray([point[1] for point in converted]).reshape(rows, columns)

    @staticmethod
    def output_values(output, values, reference, description, mask=None):
        output_nodata = reference.nodata if reference.nodata is not None else -99999.0
        result = np.asarray(values, dtype=np.float64).copy()
        if mask is not None:
            result[np.asarray(mask, dtype=bool)] = output_nodata
        write_geotiff(output, result, reference, description, output_nodata)

    def anomaly_inputs(self, parameters, context):
        observed = self.input_grid(parameters, context)
        elevation = self.elevation_grid(parameters, context)
        self.require_matching(observed, elevation, "Elevation raster")
        latitude = self.latitude_grid(observed)
        normal = normal_gravity_grs80(latitude)
        mask = nodata_mask(observed) | nodata_mask(elevation)
        return observed, elevation, normal, mask


class NormalGravityAlgorithm(GravityCorrectionBase):
    def name(self):
        return "normal_gravity_grs80"

    def displayName(self):
        return self.tr("01 Normal gravity — GRS80 latitude field")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(parameters, context)
        feedback.setProgress(20)
        values = normal_gravity_grs80(self.latitude_grid(grid))
        output = self.output_path(parameters, context)
        self.output_values(output, values, grid, "GRS80 normal gravity (mGal)", nodata_mask(grid))
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr(
            "Creates normal gravity on the GRS80 ellipsoid from the latitude of every pixel center using Somigliana's formula. The input values are ignored; the raster supplies the grid and CRS. Output is mGal."
        )


class LatitudeCorrectionAlgorithm(GravityCorrectionBase):
    def name(self):
        return "gravity_disturbance_grs80"

    def displayName(self):
        return self.tr("02 Latitude correction — gravity disturbance (GRS80)")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()

    def processAlgorithm(self, parameters, context, feedback):
        observed = self.input_grid(parameters, context)
        normal = normal_gravity_grs80(self.latitude_grid(observed))
        values = gravity_disturbance(observed.values, normal)
        output = self.output_path(parameters, context)
        self.output_values(output, values, observed, "Observed minus GRS80 normal gravity (mGal)", nodata_mask(observed))
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr(
            "Subtracts GRS80 normal gravity at each pixel latitude from observed gravity. Input observed gravity and output disturbance are in mGal. Instrument drift and Earth tides must already be corrected."
        )


class FreeAirCorrectionAlgorithm(GravityCorrectionBase):
    def name(self):
        return "free_air_correction"

    def displayName(self):
        return self.tr("03 Free-air correction")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_vertical_gradient_parameter()

    def processAlgorithm(self, parameters, context, feedback):
        elevation = self.input_grid(parameters, context)
        gradient = self.parameterAsDouble(parameters, self.VERTICAL_GRADIENT, context)
        values = free_air_correction(elevation.values, gradient)
        output = self.output_path(parameters, context)
        self.output_values(output, values, elevation, "Free-air correction (mGal)", nodata_mask(elevation))
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Calculates FAC = vertical_gradient × geometric height. Input height is metres and output is mGal; the default gradient is 0.3086 mGal/m.")


class FreeAirAnomalyAlgorithm(GravityCorrectionBase):
    def name(self):
        return "free_air_anomaly"

    def displayName(self):
        return self.tr("04 Free-air anomaly — observed gravity + elevation")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_elevation_parameters()
        self.add_vertical_gradient_parameter()

    def processAlgorithm(self, parameters, context, feedback):
        observed, elevation, normal, mask = self.anomaly_inputs(parameters, context)
        gradient = self.parameterAsDouble(parameters, self.VERTICAL_GRADIENT, context)
        values = free_air_anomaly(observed.values, normal, elevation.values, gradient)
        output = self.output_path(parameters, context)
        self.output_values(output, values, observed, "Free-air anomaly (mGal)", mask)
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class CurvatureCorrectionAlgorithm(GravityCorrectionBase):
    def name(self):
        return "bullard_b_curvature"

    def displayName(self):
        return self.tr("05 Earth curvature correction — Bullard B")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_CRUST, self.tr("Reduction density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=2670.0, minValue=1.0))

    def processAlgorithm(self, parameters, context, feedback):
        elevation = self.input_grid(parameters, context)
        density = self.parameterAsDouble(parameters, self.DENSITY_CRUST, context)
        values = curvature_correction(elevation.values, density)
        output = self.output_path(parameters, context)
        self.output_values(output, values, elevation, "Bullard B curvature correction (mGal)", nodata_mask(elevation))
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Lambert/Bullard-B spherical-cap correction for non-negative land elevation. The polynomial is density-scaled from 2670 kg/m³. Subtract this positive correction when forming CBA = SBA + terrain - Bullard B.")


class SimpleBouguerAnomalyAlgorithm(GravityCorrectionBase):
    implementation_details = HARMONICA_GRAVITY_DETAILS
    def name(self):
        return "simple_bouguer_anomaly"

    def displayName(self):
        return self.tr("06 Simple Bouguer anomaly")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_elevation_parameters()
        self.add_density_parameters()
        self.add_vertical_gradient_parameter()

    def processAlgorithm(self, parameters, context, feedback):
        observed, elevation, normal, mask = self.anomaly_inputs(parameters, context)
        harmonica = import_harmonica()
        bouguer = harmonica.bouguer_correction(
            elevation.values,
            density_crust=self.parameterAsDouble(parameters, self.DENSITY_CRUST, context),
            density_water=self.parameterAsDouble(parameters, self.DENSITY_WATER, context),
        )
        values = simple_bouguer_anomaly(
            observed.values,
            normal,
            elevation.values,
            bouguer,
            self.parameterAsDouble(parameters, self.VERTICAL_GRADIENT, context),
        )
        output = self.output_path(parameters, context)
        self.output_values(output, values, observed, "Simple Bouguer anomaly (mGal)", mask)
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class TerrainCorrectionAlgorithm(GravityCorrectionBase):
    implementation_details = HARMONICA_GRAVITY_DETAILS
    MAX_CELLS = "MAX_CELLS"
    CLEARANCE = "CLEARANCE"

    def name(self):
        return "terrain_correction_prisms"

    def displayName(self):
        return self.tr("07 Terrain correction — DEM prisms")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_density_parameters()
        self.addParameter(QgsProcessingParameterNumber(self.CLEARANCE, self.tr("Observation clearance above DEM (m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=1.0, minValue=0.001))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_CELLS, self.tr("Safety limit: DEM cells"), type=PROCESSING_NUMBER_INTEGER, defaultValue=10000, minValue=4, maxValue=100000))

    def processAlgorithm(self, parameters, context, feedback):
        grid = self.input_grid(
            parameters, context, require_projected=True, require_metric=True
        )
        if nodata_mask(grid).any():
            raise QgsProcessingException("Terrain correction requires a complete DEM without NoData. Fill or crop gaps first.")
        cell_count = int(grid.values.size)
        maximum = self.parameterAsInt(parameters, self.MAX_CELLS, context)
        if cell_count > maximum:
            raise QgsProcessingException(f"DEM has {cell_count:,} cells, exceeding the {maximum:,}-cell safety limit. Resample/crop it or deliberately raise the limit.")
        orientation = to_regular_data_array(grid)
        data = orientation.data
        topography = np.asarray(data.values, dtype=np.float64)
        crust = self.parameterAsDouble(parameters, self.DENSITY_CRUST, context)
        water = self.parameterAsDouble(parameters, self.DENSITY_WATER, context)
        density = np.where(topography >= 0.0, crust, water - crust)
        harmonica = import_harmonica()
        feedback.pushInfo(f"Forward modelling {cell_count:,} terrain prisms at {cell_count:,} stations.")
        feedback.setProgress(15)
        layer = harmonica.prism_layer(
            (np.asarray(data.easting), np.asarray(data.northing)),
            topography,
            reference=0.0,
            properties={"density": density},
        )
        east, north = np.meshgrid(np.asarray(data.easting), np.asarray(data.northing))
        upward = topography + self.parameterAsDouble(parameters, self.CLEARANCE, context)
        effect = layer.prism_layer.gravity(
            (east.ravel(), north.ravel(), upward.ravel()),
            field="g_z",
            thickness_threshold=0.001,
        ).reshape(topography.shape)
        plate = np.asarray(harmonica.bouguer_correction(topography, density_crust=crust, density_water=water))
        correction = plate - effect
        values = restore_raster_order(correction, orientation)
        output = self.output_path(parameters, context)
        self.output_values(output, values, grid, "Terrain correction from DEM prisms (mGal)")
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Computes the difference between the infinite Bouguer plate and the exact rectangular-prism attraction of the supplied projected DEM, evaluated just above each cell. Output is the terrain term added to the simple Bouguer anomaly. The DEM extent defines the outer correction radius; use a sufficiently broad, filled DEM and inspect edge effects. Cost grows approximately with cells squared.")


class CompleteBouguerAnomalyAlgorithm(GravityCorrectionBase):
    implementation_details = HARMONICA_GRAVITY_DETAILS
    TERRAIN = "TERRAIN"
    TERRAIN_BAND = "TERRAIN_BAND"

    def name(self):
        return "complete_bouguer_anomaly"

    def displayName(self):
        return self.tr("08 Complete Bouguer anomaly — land")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_elevation_parameters()
        self.addParameter(QgsProcessingParameterRasterLayer(self.TERRAIN, self.tr("Terrain correction raster (mGal)")))
        self.addParameter(QgsProcessingParameterBand(self.TERRAIN_BAND, self.tr("Terrain correction band"), parentLayerParameterName=self.TERRAIN, defaultValue=1))
        self.add_density_parameters()
        self.add_vertical_gradient_parameter()

    def processAlgorithm(self, parameters, context, feedback):
        observed, elevation, normal, mask = self.anomaly_inputs(parameters, context)
        terrain_layer = self.parameterAsRasterLayer(parameters, self.TERRAIN, context)
        terrain = read_raster(terrain_layer, self.parameterAsInt(parameters, self.TERRAIN_BAND, context))
        self.require_matching(observed, terrain, "Terrain correction raster")
        mask |= nodata_mask(terrain)
        crust = self.parameterAsDouble(parameters, self.DENSITY_CRUST, context)
        water = self.parameterAsDouble(parameters, self.DENSITY_WATER, context)
        harmonica = import_harmonica()
        bouguer = harmonica.bouguer_correction(elevation.values, density_crust=crust, density_water=water)
        curvature = curvature_correction(elevation.values, crust)
        values = complete_bouguer_anomaly(
            observed.values, normal, elevation.values, bouguer, terrain.values, curvature,
            self.parameterAsDouble(parameters, self.VERTICAL_GRADIENT, context),
        )
        output = self.output_path(parameters, context)
        self.output_values(output, values, observed, "Complete Bouguer anomaly (mGal)", mask)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Forms the land complete Bouguer anomaly as observed - GRS80 normal + free-air - Bouguer plate + terrain - Bullard B. Inputs must be aligned rasters. Drift, tides and meter calibration must already be resolved.")


class AiryMohoAlgorithm(GravityCorrectionBase):
    REFERENCE_DEPTH = "REFERENCE_DEPTH"
    DENSITY_MANTLE = "DENSITY_MANTLE"

    def name(self):
        return "airy_isostatic_moho"

    def displayName(self):
        return self.tr("09 Airy isostatic Moho depth")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterNumber(self.REFERENCE_DEPTH, self.tr("Reference Moho depth (m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=25000.0, minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_CRUST, self.tr("Crust density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=2670.0, minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_MANTLE, self.tr("Mantle density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=3070.0, minValue=1.0))

    def processAlgorithm(self, parameters, context, feedback):
        elevation = self.input_grid(parameters, context)
        try:
            values = airy_moho_depth(
                elevation.values,
                self.parameterAsDouble(parameters, self.REFERENCE_DEPTH, context),
                self.parameterAsDouble(parameters, self.DENSITY_CRUST, context),
                self.parameterAsDouble(parameters, self.DENSITY_MANTLE, context),
            )
        except ValueError as error:
            raise QgsProcessingException(str(error)) from error
        output = self.output_path(parameters, context)
        self.output_values(output, values, elevation, "Airy isostatic Moho depth (m)", nodata_mask(elevation))
        feedback.setProgress(100)
        return {self.OUTPUT: output}


class AiryIsostaticAnomalyAlgorithm(AiryMohoAlgorithm):
    implementation_details = HARMONICA_GRAVITY_DETAILS
    MAX_CELLS = "MAX_CELLS"
    REGIONAL = "REGIONAL"
    WATER = "WATER"
    BLOCK_SIZE = "BLOCK_SIZE"
    MAX_INTERACTIONS = "MAX_INTERACTIONS"

    def name(self):
        return "airy_isostatic_anomaly"

    def displayName(self):
        return self.tr("10 Airy isostatic residual anomaly")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.add_elevation_parameters()
        self.parameterDefinition(self.ELEVATION).setDescription(self.tr("Observation height raster (m, same vertical datum as model)"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.REGIONAL, self.tr("Regional basement/topobathymetry (m; band 1; optional, defaults to elevation)"), optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.WATER, self.tr("Water thickness on regional grid (m; band 1; optional, defaults to zero)"), optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_WATER, self.tr("Water density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=1040.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(self.BLOCK_SIZE, self.tr("Regional model aggregation factor (test convergence)"), type=PROCESSING_NUMBER_INTEGER, defaultValue=1, minValue=1, maxValue=10000))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_INTERACTIONS, self.tr("Safety limit: station/prism pairs"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=200000000, minValue=1, maxValue=1e12))
        self.addParameter(QgsProcessingParameterNumber(self.REFERENCE_DEPTH, self.tr("Reference Moho depth (m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=25000.0, minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_CRUST, self.tr("Crust density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=2670.0, minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_MANTLE, self.tr("Mantle density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=3070.0, minValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_CELLS, self.tr("Safety limit: model cells"), type=PROCESSING_NUMBER_INTEGER, defaultValue=10000, minValue=4, maxValue=10000000))

    def processAlgorithm(self, parameters, context, feedback):
        bouguer = self.input_grid(
            parameters, context, require_projected=True, require_metric=True
        )
        elevation = self.elevation_grid(parameters, context)
        self.require_matching(bouguer, elevation, "Elevation raster")
        regional_layer = self.parameterAsRasterLayer(parameters, self.REGIONAL, context)
        model = read_raster(regional_layer, 1) if regional_layer is not None else elevation
        source, target = osr.SpatialReference(), osr.SpatialReference()
        if (source.ImportFromWkt(bouguer.projection) != 0 or target.ImportFromWkt(model.projection) != 0
                or not source.IsSame(target)):
            raise QgsProcessingException("Regional model must use the same projected metric CRS as observations.")
        if nodata_mask(model).any():
            raise QgsProcessingException("Regional load model contains NoData. Supply a complete regional basement raster; missing loads cannot be treated as zero.")
        orientation = to_regular_data_array(model)
        water = 0.
        water_layer = self.parameterAsRasterLayer(parameters, self.WATER, context)
        if water_layer is not None:
            water_grid = read_raster(water_layer, 1)
            self.require_matching(model, water_grid, "Water thickness")
            water = np.asarray(to_regular_data_array(water_grid).data.values)
        mask = nodata_mask(bouguer) | nodata_mask(elevation)
        if mask.all():
            raise QgsProcessingException("No valid Bouguer/observation-height pairs.")
        rows, cols = np.indices(bouguer.values.shape)
        gt = bouguer.geotransform
        east = gt[0] + (cols + .5) * gt[1] + (rows + .5) * gt[2]
        north = gt[3] + (cols + .5) * gt[4] + (rows + .5) * gt[5]
        height = np.where(mask, np.nan, elevation.values)
        crust = self.parameterAsDouble(parameters, self.DENSITY_CRUST, context)
        mantle = self.parameterAsDouble(parameters, self.DENSITY_MANTLE, context)
        reference_depth = self.parameterAsDouble(parameters, self.REFERENCE_DEPTH, context)
        block = self.parameterAsInt(parameters, self.BLOCK_SIZE, context)
        water_density = self.parameterAsDouble(parameters, self.DENSITY_WATER, context)
        try:
            prisms, density = airy_prisms(
                np.asarray(orientation.data.easting), np.asarray(orientation.data.northing),
                np.asarray(orientation.data.values), reference_depth=reference_depth,
                density_crust=crust, density_mantle=mantle, water_thickness=water,
                density_water=water_density, block_size=block,
                max_cells=self.parameterAsInt(parameters, self.MAX_CELLS, context))
            feedback.pushInfo(f"Finite Cartesian model: {len(prisms):,} root prisms, {(~mask).sum():,} stations. Test regional extent and aggregation convergence.")
            root_effect = airy_root_effect(
                (east, north, height), prisms, density,
                max_interactions=self.parameterAsDouble(parameters, self.MAX_INTERACTIONS, context),
                progress=lambda fraction: feedback.setProgress(100 * fraction),
                cancelled=feedback.isCanceled, gravity_backend=import_harmonica().prism_gravity)
        except (ValueError, InterruptedError) as error:
            raise QgsProcessingException(str(error)) from error
        values = bouguer.values - root_effect
        bouguer.metadata = dict(bouguer.metadata, TW_ISOSTASY=json.dumps(dict(
            model="finite Cartesian Airy", reference_depth_m=reference_depth,
            density_crust=crust, density_mantle=mantle, density_water=water_density,
            regional_source=model.source_path, water_source=water_grid.source_path if water_layer is not None else None,
            block_size=block, prisms=len(prisms), far_zone="none", formula="Bouguer - root_g_z")))
        output = self.output_path(parameters, context)
        self.output_values(output, values, bouguer, "Airy isostatic residual anomaly (mGal)", mask)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Subtracts finite Cartesian Airy root gravity from Bouguer. Observation heights must align with Bouguer; the independent regional basement may be larger and coarser in the same metric CRS. All heights share one vertical datum. Water thickness is explicit, including lakes. Observation NoData is preserved; regional load gaps are rejected. Aggregation averages load and conserves mass, not exact geometry. Test resolution and regional extent. No spherical/global far-zone effect is included; this is not a proprietary survey reproduction.")


class AiryFFTAnomalyAlgorithm(AiryMohoAlgorithm):
    """Explicit periodic-domain alternative; legacy finite solver is unchanged."""

    implementation_details = (
        ("Numerical backend", "NumPy and SciPy: Parker series with periodic boundaries"),
        ("Host and raster I/O", "QGIS Processing and GDAL"),
    )

    REGIONAL = "REGIONAL"
    WATER = "WATER"
    HEIGHT = "HEIGHT"
    TOLERANCE = "TOLERANCE"
    MAX_CELLS = "MAX_CELLS"

    def name(self):
        return "airy_isostatic_anomaly_fft"

    def displayName(self):
        return self.tr("11 Airy isostatic residual (periodic FFT)")

    def initAlgorithm(self, config=None):
        self.add_raster_parameters()
        self.addParameter(QgsProcessingParameterRasterLayer(self.REGIONAL, self.tr("Regional basement/topobathymetry (m; band 1; periodic domain)")))
        self.addParameter(QgsProcessingParameterRasterLayer(self.WATER, self.tr("Water thickness on regional grid (m; band 1; optional, defaults to zero)"), optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.REFERENCE_DEPTH, self.tr("Reference Moho depth (m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=30000., minValue=1.))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_CRUST, self.tr("Crust density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=2670., minValue=1.))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_MANTLE, self.tr("Mantle density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=3270., minValue=1.))
        self.addParameter(QgsProcessingParameterNumber(self.DENSITY_WATER, self.tr("Water density (kg/m³)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=1040., minValue=0.))
        self.addParameter(QgsProcessingParameterNumber(self.HEIGHT, self.tr("Constant observation height above model datum (m)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0., minValue=-10000., maxValue=100000.))
        self.addParameter(QgsProcessingParameterNumber(self.TOLERANCE, self.tr("FFT series term tolerance (mGal)"), type=PROCESSING_NUMBER_DOUBLE, defaultValue=0.00001, minValue=1e-10, maxValue=1.))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_CELLS, self.tr("Safety limit: model cells"), type=PROCESSING_NUMBER_INTEGER, defaultValue=4000000, minValue=4, maxValue=16000000))

    def processAlgorithm(self, parameters, context, feedback):
        from scipy.interpolate import RegularGridInterpolator

        bouguer = self.input_grid(parameters, context, require_projected=True, require_metric=True)
        regional = self.parameterAsRasterLayer(parameters, self.REGIONAL, context)
        if regional is None or not regional.isValid():
            raise QgsProcessingException("A complete regional load raster is required for periodic FFT Airy.")
        model = read_raster(regional, 1)
        source, target = osr.SpatialReference(), osr.SpatialReference()
        if (source.ImportFromWkt(bouguer.projection) != 0 or target.ImportFromWkt(model.projection) != 0
                or not source.IsSame(target)):
            raise QgsProcessingException("Regional model must use the same projected metric CRS as observations.")
        orientation = to_regular_data_array(model)
        data = orientation.data
        x, y = np.asarray(data.easting), np.asarray(data.northing)
        if len(x) < 2 or len(y) < 2:
            raise QgsProcessingException("FFT Airy needs at least two model rows and columns.")
        water, water_source = 0., None
        water_layer = self.parameterAsRasterLayer(parameters, self.WATER, context)
        if water_layer is not None:
            water_grid = read_raster(water_layer, 1)
            self.require_matching(model, water_grid, "Water thickness")
            water = np.asarray(to_regular_data_array(water_grid).data.values)
            water_source = water_grid.source_path
        mask = nodata_mask(bouguer)
        if mask.all():
            raise QgsProcessingException("No valid Bouguer observations.")
        feedback.pushInfo("Periodic FFT boundary: regional load and its mean repeat beyond the supplied rectangle. No fitted offset is applied.")
        try:
            effect, recipe = airy_root_effect_fft(
                np.asarray(data.values), (x[1]-x[0], y[1]-y[0]), boundary="periodic",
                reference_depth=self.parameterAsDouble(parameters, self.REFERENCE_DEPTH, context),
                density_crust=self.parameterAsDouble(parameters, self.DENSITY_CRUST, context),
                density_mantle=self.parameterAsDouble(parameters, self.DENSITY_MANTLE, context),
                density_water=self.parameterAsDouble(parameters, self.DENSITY_WATER, context),
                water_thickness=water, observation_height=self.parameterAsDouble(parameters, self.HEIGHT, context),
                tolerance_mgal=self.parameterAsDouble(parameters, self.TOLERANCE, context),
                max_cells=self.parameterAsInt(parameters, self.MAX_CELLS, context), cancelled=feedback.isCanceled)
            rows, cols = np.indices(bouguer.values.shape)
            gt = bouguer.geotransform
            east = gt[0]+(cols+.5)*gt[1]+(rows+.5)*gt[2]
            north = gt[3]+(cols+.5)*gt[4]+(rows+.5)*gt[5]
            correction = RegularGridInterpolator((y, x), effect, bounds_error=True)(
                np.column_stack((north[~mask], east[~mask])))
        except (ValueError, InterruptedError) as error:
            raise QgsProcessingException(str(error)) from error
        values = np.full(bouguer.values.shape, np.nan)
        values[~mask] = bouguer.values[~mask]-correction
        recipe.update(regional_source=model.source_path, water_source=water_source,
                      model_shape=list(model.values.shape), geotransform=list(model.geotransform),
                      formula="Bouguer - root_g_z", sampling="bilinear, no extrapolation",
                      far_zone="periodic Cartesian repetition, not spherical integration")
        bouguer.metadata = dict(bouguer.metadata, TW_ISOSTASY=json.dumps(recipe))
        output = self.output_path(parameters, context)
        self.output_values(output, values, bouguer, "Periodic FFT Airy isostatic residual (mGal)", mask)
        feedback.setProgress(100)
        return {self.OUTPUT: output}

    def shortHelpString(self):
        return self.tr("Parker-series Airy root gravity on a constant observation plane. The complete regional load grid repeats periodically, including its mean; no fitted offset or gap filling is used. Water thickness is explicit. The regional model and Bouguer must share a metric CRS and vertical datum. Output is bilinearly sampled inside the model and preserves Bouguer NoData. Test domain extent, density and resolution. Periodic boundaries are a physical assumption, not a finite or spherical global model; agreement with a survey does not identify its proprietary recipe.")
