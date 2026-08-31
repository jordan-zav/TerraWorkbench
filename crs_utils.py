"""Coordinate-system checks and direction conversions for physical workflows."""

from __future__ import annotations

import math

from osgeo import osr


def spatial_reference(wkt):
    """Return a traditional-axis GDAL spatial reference from WKT."""
    reference = osr.SpatialReference()
    if not wkt or reference.ImportFromWkt(str(wkt)) != 0:
        raise ValueError("The coordinate reference system is missing or invalid.")
    if hasattr(reference, "SetAxisMappingStrategy"):
        reference.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return reference


def require_metre_projected_crs(wkt, operation="This operation"):
    """Reject geographic and non-metre projected coordinates for physical models."""
    reference = spatial_reference(wkt)
    if not reference.IsProjected():
        raise ValueError(f"{operation} requires a projected CRS in metres.")
    factor = float(reference.GetLinearUnits())
    if not math.isfinite(factor) or not math.isclose(
        factor, 1.0, rel_tol=0.0, abs_tol=1e-9
    ):
        unit = reference.GetLinearUnitsName() or "unknown units"
        raise ValueError(
            f"{operation} requires projected coordinates in metres; the CRS uses "
            f"{unit} ({factor:g} metres per unit). Reproject the input first."
        )
    return reference


def grid_convergence_degrees(wkt, easting, northing):
    """Return true-north azimuth clockwise from grid north at one projected point."""
    source = spatial_reference(wkt)
    if not source.IsProjected():
        raise ValueError("Grid convergence requires a projected CRS.")
    geographic = osr.SpatialReference()
    geographic.ImportFromEPSG(4326)
    if hasattr(geographic, "SetAxisMappingStrategy"):
        geographic.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_geographic = osr.CoordinateTransformation(source, geographic)
    to_projected = osr.CoordinateTransformation(geographic, source)
    longitude, latitude, _height = to_geographic.TransformPoint(
        float(easting), float(northing)
    )
    step = 1e-5 if latitude < 89.99 else -1e-5
    x0, y0, _ = to_projected.TransformPoint(longitude, latitude)
    x1, y1, _ = to_projected.TransformPoint(longitude, latitude + step)
    direction = 1.0 if step > 0.0 else -1.0
    delta_east = direction * (x1 - x0)
    delta_north = direction * (y1 - y0)
    if not all(math.isfinite(value) for value in (delta_east, delta_north)):
        raise ValueError("Could not calculate grid convergence at the data centre.")
    return math.degrees(math.atan2(delta_east, delta_north))


def raster_center(grid):
    """Return projected centre coordinates from a raster geotransform."""
    rows, columns = grid.values.shape
    transform = grid.geotransform
    return (
        transform[0] + columns * 0.5 * transform[1] + rows * 0.5 * transform[2],
        transform[3] + columns * 0.5 * transform[4] + rows * 0.5 * transform[5],
    )
