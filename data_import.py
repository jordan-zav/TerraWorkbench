"""Import survey grids into analysis-ready GeoTIFF without changing their sources."""

from __future__ import annotations

from pathlib import Path
import re
from defusedxml import ElementTree as ET

import numpy as np
from osgeo import gdal, osr
from qgis.core import QgsProcessingException

from .delimited_text import detect_delimited_layout, regular_coordinate_axes
from .dependencies import import_harmonica


GEOSOFT_SIGNATURE = b"!CBD"


def read_sidecar_metadata(source):
    """Read useful Geosoft XML metadata while tolerating namespaces and variants."""
    source = Path(source)
    candidates = (Path(str(source) + ".xml"), source.with_suffix(".xml"))
    xml_path = next((path for path in candidates if path.is_file()), None)
    if xml_path is None:
        return {}
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError):
        return {}
    values = {}
    for element in root.iter():
        key = element.tag.rsplit("}", 1)[-1].strip().lower()
        text = " ".join(part.strip() for part in element.itertext() if part.strip())
        if text and key not in values:
            values[key] = text
        for attribute, attribute_value in element.attrib.items():
            attribute_key = attribute.rsplit("}", 1)[-1].strip().lower()
            if attribute_value and attribute_key not in values:
                values[attribute_key] = attribute_value.strip()
    aliases = {
        "TITLE": ("title", "dataset_title", "name"),
        "EPSG": ("wellknown_epsg", "epsg", "epsg_code"),
        "SURVEY_START": (
            "surveystartdate",
            "survey_start_date",
            "start_date",
            "survey_start",
        ),
        "SURVEY_END": ("surveyenddate", "survey_end_date", "end_date", "survey_end"),
        "LINE_DIRECTION": ("linedirection", "line_direction", "flight_line_direction"),
        "LINE_SPACING": ("linespacing", "line_spacing", "flight_line_spacing"),
        "DATUM": ("datum", "horizontal_datum"),
        "PROJECTION": ("projection", "map_projection"),
        "UPDATED": ("update_date", "date_updated", "modified"),
    }
    metadata = {"METADATA_SIDECAR": str(xml_path)}
    for output_key, possible_keys in aliases.items():
        value = next((values[key] for key in possible_keys if key in values), None)
        if value:
            metadata[output_key] = value
    if "EPSG" not in metadata:
        match = re.search(r"\bEPSG\D{0,8}(\d{4,6})\b", " ".join(values.values()), re.I)
        if match:
            metadata["EPSG"] = match.group(1)
    return metadata


def _projection_from_metadata(metadata):
    epsg = metadata.get("EPSG", "")
    match = re.search(r"\d{4,6}", epsg)
    if not match:
        return ""
    spatial_reference = osr.SpatialReference()
    if spatial_reference.ImportFromEPSG(int(match.group())) != 0:
        return ""
    return spatial_reference.ExportToWkt()


def import_oasis_montaj_grid(source, output):
    """Convert an Oasis montaj binary GRD using Harmonica's proven reader."""
    source, output = Path(source), Path(output)
    data = import_harmonica().load_oasis_montaj_grid(source)
    if "easting" not in data.coords or "northing" not in data.coords:
        raise QgsProcessingException(
            "The GRD does not expose regular easting/northing coordinates."
        )
    east = np.asarray(data.coords["easting"], dtype=float)
    north = np.asarray(data.coords["northing"], dtype=float)
    values = np.asarray(data.values, dtype=np.float64)
    if values.ndim != 2 or east.size < 2 or north.size < 2:
        raise QgsProcessingException("The GRD is not a two-dimensional regular grid.")
    if east[1] < east[0]:
        east, values = east[::-1], np.fliplr(values)
    if north[1] > north[0]:
        north, values = north[::-1], np.flipud(values)
    dx, dy = abs(float(east[1] - east[0])), abs(float(north[1] - north[0]))
    if not np.allclose(np.diff(east), dx) or not np.allclose(
        np.abs(np.diff(north)), dy
    ):
        raise QgsProcessingException("The GRD coordinates are not evenly spaced.")
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = gdal.GetDriverByName("GTiff").Create(
        str(output),
        east.size,
        north.size,
        1,
        gdal.GDT_Float64,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"],
    )
    if dataset is None:
        raise QgsProcessingException(f"Could not create output GeoTIFF: {output}")
    dataset.SetGeoTransform((east[0] - dx / 2, dx, 0.0, north[0] + dy / 2, 0.0, -dy))
    metadata = read_sidecar_metadata(source)
    projection = _projection_from_metadata(metadata)
    if projection:
        dataset.SetProjection(projection)
    metadata.update(
        {
            "SOURCE_FORMAT": "Oasis montaj GRD",
            "SOURCE_FILE": source.name,
            "IMPORTER": "TerraWorkbench/Harmonica",
        }
    )
    dataset.SetMetadata({key: str(value) for key, value in metadata.items()})
    nodata = -3.4028234663852886e38
    band = dataset.GetRasterBand(1)
    band.WriteArray(np.where(np.isfinite(values), values, nodata))
    band.SetNoDataValue(nodata)
    band.SetDescription(metadata.get("TITLE", source.stem))
    band.FlushCache()
    dataset.FlushCache()
    dataset = None
    return str(output), metadata


def list_raster_subdatasets(source):
    dataset = gdal.OpenEx(str(source), gdal.OF_RASTER | gdal.OF_READONLY)
    if dataset is None:
        return []
    subdatasets = dataset.GetSubDatasets() or []
    dataset = None
    return subdatasets


def list_vector_layers(source):
    """Return vector and table layer names exposed by a GDAL container."""
    dataset = gdal.OpenEx(str(source), gdal.OF_VECTOR | gdal.OF_READONLY)
    if dataset is None:
        return []
    names = []
    for index in range(dataset.GetLayerCount()):
        layer = dataset.GetLayerByIndex(index)
        if layer is not None and layer.GetName():
            names.append(layer.GetName())
    dataset = None
    return names


def import_delimited_grid(source, output):
    """Import a complete regular X/Y/value CSV or whitespace XYZ table."""
    source, output = Path(source), Path(output)
    with source.open("r", encoding="utf-8-sig", errors="replace") as source_file:
        first_line = source_file.readline()
    delimiter, has_header = detect_delimited_layout(first_line)
    if has_header:
        table = np.genfromtxt(
            source,
            delimiter=delimiter,
            names=True,
            dtype=float,
            encoding="utf-8-sig",
            invalid_raise=True,
        )
        names = list(table.dtype.names or ())
        lowered = {name.lower().replace("_", ""): name for name in names}

        def choose(candidates):
            return next((lowered[key] for key in candidates if key in lowered), None)

        x_name = choose(("x", "easting", "east", "longitude", "lon"))
        y_name = choose(("y", "northing", "north", "latitude", "lat"))
        z_name = choose(("z", "value", "field", "mag", "magnetic", "gravity", "data"))
        if not x_name or not y_name:
            raise QgsProcessingException(
                "CSV needs X/easting/longitude and Y/northing/latitude columns."
            )
        if not z_name:
            remaining = [name for name in names if name not in {x_name, y_name}]
            if len(remaining) != 1:
                raise QgsProcessingException(
                    "Choose/export a CSV with one unambiguous grid value column."
                )
            z_name = remaining[0]
        x, y, z = (
            np.atleast_1d(table[x_name]),
            np.atleast_1d(table[y_name]),
            np.atleast_1d(table[z_name]),
        )
        geographic_columns = x_name.lower() in {
            "longitude",
            "lon",
        } and y_name.lower() in {"latitude", "lat"}
    else:
        table = np.loadtxt(source, delimiter=delimiter, ndmin=2)
        if table.shape[1] < 3:
            raise QgsProcessingException(
                "ASCII XYZ needs at least three columns: X Y value."
            )
        x, y, z = table[:, 0], table[:, 1], table[:, 2]
        geographic_columns = False
    valid = np.isfinite(x) & np.isfinite(y)
    x, y, z = x[valid], y[valid], z[valid]
    try:
        east, north, dx, dy = regular_coordinate_axes(x, y)
    except ValueError as error:
        raise QgsProcessingException(str(error)) from error
    values = np.full((north.size, east.size), np.nan, dtype=np.float64)
    x_indices = np.searchsorted(east, x)
    y_indices = north.size - 1 - np.searchsorted(north, y)
    values[y_indices, x_indices] = z
    metadata = read_sidecar_metadata(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = gdal.GetDriverByName("GTiff").Create(
        str(output),
        east.size,
        north.size,
        1,
        gdal.GDT_Float64,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"],
    )
    dataset.SetGeoTransform(
        (east[0] - dx[0] / 2, dx[0], 0.0, north[-1] + dy[0] / 2, 0.0, -dy[0])
    )
    projection = _projection_from_metadata(metadata)
    if not projection and geographic_columns:
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(4326)
        projection = spatial_reference.ExportToWkt()
        metadata["EPSG"] = "4326"
    if projection:
        dataset.SetProjection(projection)
    nodata = -3.4028234663852886e38
    metadata.update(
        {
            "SOURCE_FORMAT": "Delimited regular grid",
            "SOURCE_FILE": source.name,
            "IMPORTER": "TerraWorkbench",
        }
    )
    dataset.SetMetadata({key: str(value) for key, value in metadata.items()})
    band = dataset.GetRasterBand(1)
    band.WriteArray(np.where(np.isfinite(values), values, nodata))
    band.SetNoDataValue(nodata)
    dataset.FlushCache()
    dataset = None
    return str(output), metadata


def import_survey_grid(source, output, subdataset=None):
    """Import GRD or any GDAL-readable regular grid to GeoTIFF."""
    source = Path(source)
    if not source.exists():
        raise QgsProcessingException(f"Input does not exist: {source}")
    if source.is_file() and source.suffix.lower() == ".grd":
        return import_oasis_montaj_grid(source, output)
    if source.is_file() and source.suffix.lower() == ".gdb":
        with source.open("rb") as stream:
            signature = stream.read(4)
        if signature == GEOSOFT_SIGNATURE:
            raise QgsProcessingException(
                "This is a GeoDatabase (Oasis montaj), not an Esri FileGDB. "
                "Open it with TerraWorkbench's dedicated GeoDatabase inventory/export "
                "command, which uses the public GX Developer reader when available."
            )
    if source.is_file() and source.suffix.lower() == ".csv":
        return import_delimited_grid(source, output)
    input_name = subdataset or str(source)
    dataset = gdal.OpenEx(input_name, gdal.OF_RASTER | gdal.OF_READONLY)
    if dataset is None:
        if source.suffix.lower() in {".csv", ".xyz", ".txt"}:
            try:
                return import_delimited_grid(source, output)
            except (OSError, ValueError) as error:
                raise QgsProcessingException(
                    f"Could not parse delimited grid: {error}"
                ) from error
        label = (
            "CSV/ASCII must form a regular GDAL XYZ/AAIGrid/GXF grid"
            if source.suffix.lower() in {".csv", ".xyz", ".txt", ".asc"}
            else "GDAL could not open this raster"
        )
        raise QgsProcessingException(f"{label}: {source}")
    subdatasets = dataset.GetSubDatasets() or []
    if dataset.RasterCount == 0 and subdatasets and subdataset is None:
        dataset = None
        raise QgsProcessingException(
            "This container has multiple raster datasets. Select one: "
            + "; ".join(description for _name, description in subdatasets[:12])
        )
    dataset = None
    translated = gdal.Translate(
        str(output),
        input_name,
        format="GTiff",
        creationOptions=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=2"],
    )
    if translated is None:
        raise QgsProcessingException("GDAL failed while converting the selected grid.")
    translated.SetMetadataItem("IMPORTER", "TerraWorkbench/GDAL")
    translated.SetMetadataItem("SOURCE_FILE", source.name)
    translated.FlushCache()
    translated = None
    return str(output), {"SOURCE_FORMAT": "GDAL", "SOURCE_FILE": source.name}
