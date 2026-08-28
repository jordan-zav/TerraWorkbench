"""Raster conversion helpers shared by TerraWorkbench algorithms."""

from dataclasses import dataclass
import os
from typing import Optional

import numpy as np
from osgeo import gdal
from qgis.core import QgsProcessingException

from .dependencies import import_xarray


@dataclass
class RasterGrid:
    """Raster values and georeferencing read from a QGIS layer."""

    values: np.ndarray
    geotransform: tuple
    projection: str
    nodata: Optional[float]
    metadata: dict
    source_path: str


@dataclass
class OrientedGrid:
    """An xarray grid plus the flips needed to restore raster row order."""

    data: object
    flip_vertical: bool
    flip_horizontal: bool


def _physical_source(layer):
    source = layer.source().split("|", 1)[0]
    if not source or not os.path.exists(source):
        raise QgsProcessingException(
            "The input raster must be backed by a local file. Save temporary or "
            "remote layers to GeoTIFF before running this algorithm."
        )
    return source


def read_raster(layer, band_number):
    """Read one raster band as float64 using the GDAL bundled with QGIS."""
    source = _physical_source(layer)
    dataset = gdal.Open(source, gdal.GA_ReadOnly)
    if dataset is None:
        raise QgsProcessingException("GDAL could not open the input raster.")
    if band_number < 1 or band_number > dataset.RasterCount:
        raise QgsProcessingException("The selected raster band does not exist.")

    band = dataset.GetRasterBand(band_number)
    values = band.ReadAsArray()
    if values is None:
        raise QgsProcessingException("GDAL could not read the selected raster band.")

    grid = RasterGrid(
        values=np.asarray(values, dtype=np.float64),
        geotransform=tuple(dataset.GetGeoTransform()),
        projection=dataset.GetProjection(),
        nodata=band.GetNoDataValue(),
        metadata=dataset.GetMetadata() or {},
        source_path=source,
    )
    dataset = None
    return grid


def nodata_mask(grid):
    """Return invalid and declared NoData cells."""
    mask = ~np.isfinite(grid.values)
    if grid.nodata is not None:
        if np.isnan(grid.nodata):
            mask |= np.isnan(grid.values)
        else:
            mask |= np.isclose(grid.values, grid.nodata)
    return mask


def to_regular_data_array(grid):
    """Convert a north-up projected raster into Harmonica grid convention."""
    transform = grid.geotransform
    if not np.isclose(transform[2], 0.0) or not np.isclose(transform[4], 0.0):
        raise QgsProcessingException(
            "Rotated rasters are not supported. Warp the raster to a north-up grid first."
        )
    if np.isclose(transform[1], 0.0) or np.isclose(transform[5], 0.0):
        raise QgsProcessingException("The raster has an invalid pixel size.")
    if nodata_mask(grid).any():
        raise QgsProcessingException(
            "FFT transformations require a complete regular grid without NoData or "
            "non-finite cells. Fill or crop gaps before running this algorithm."
        )

    rows, columns = grid.values.shape
    easting = transform[0] + (np.arange(columns) + 0.5) * transform[1]
    northing = transform[3] + (np.arange(rows) + 0.5) * transform[5]
    values = grid.values

    flip_vertical = rows > 1 and northing[1] < northing[0]
    flip_horizontal = columns > 1 and easting[1] < easting[0]
    if flip_vertical:
        northing = northing[::-1]
        values = np.flipud(values)
    if flip_horizontal:
        easting = easting[::-1]
        values = np.fliplr(values)

    xarray = import_xarray()
    data = xarray.DataArray(
        values,
        coords={"northing": northing, "easting": easting},
        dims=("northing", "easting"),
        name="field",
    )
    return OrientedGrid(data, flip_vertical, flip_horizontal)


def restore_raster_order(values, orientation):
    """Restore top-to-bottom and left-to-right order of the source raster."""
    restored = np.asarray(values, dtype=np.float64)
    if orientation.flip_horizontal:
        restored = np.fliplr(restored)
    if orientation.flip_vertical:
        restored = np.flipud(restored)
    return restored


def write_geotiff(output_path, values, grid, description, output_nodata=None):
    """Write a georeferenced float64 GeoTIFF."""
    rows, columns = values.shape
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(
        output_path,
        columns,
        rows,
        1,
        gdal.GDT_Float64,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"],
    )
    if dataset is None:
        raise QgsProcessingException(
            "Could not create the output GeoTIFF. Check the destination and file locks."
        )

    dataset.SetGeoTransform(grid.geotransform)
    dataset.SetProjection(grid.projection)
    dataset.SetMetadata(grid.metadata)
    band = dataset.GetRasterBand(1)
    band.WriteArray(np.asarray(values, dtype=np.float64))
    band.SetDescription(description)
    if output_nodata is not None:
        band.SetNoDataValue(float(output_nodata))
    band.FlushCache()
    dataset.FlushCache()
    dataset = None
    return output_path
