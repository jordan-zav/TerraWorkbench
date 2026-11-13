"""Adapt point observations from existing GDB importers to SurveyStore."""

from pathlib import Path
from uuid import uuid4


def _available_name(store, name):
    existing = {row["name"] for row in store.databases()}
    base, suffix = name, 2
    while name in existing:
        name = f"{base} ({suffix})"
        suffix += 1
    return name


def import_geosoft_observations(store, path, name, manifest, canceled=None):
    from .data_import import read_sidecar_metadata, _projection_from_metadata
    from ..terraworkbench_core.survey_text_import import ColumnSpec, TextImportOptions
    import csv

    metadata = read_sidecar_metadata(manifest.get("source") or path)
    metadata.update(
        {
            "crs": manifest.get("coordinate_system", {}).get("wkt")
            or _projection_from_metadata(metadata),
            "x_field": manifest.get("x_field"),
            "y_field": manifest.get("y_field"),
            "line_field": "LINE",
            "line_metadata": {row["name"]: row for row in manifest.get("lines", [])},
            "source_format": "Geosoft GeoDatabase",
        }
    )
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        fields = next(csv.reader(stream))
    options = TextImportOptions(
        columns=[
            ColumnSpec(field, "text" if field in {"SOURCE_FORMAT", "LINE"} else "float")
            for field in fields
        ],
        null_values=("", "nan", "NaN", "inf", "-inf"),
    )
    return store.import_file(
        path,
        name=_available_name(store, name),
        metadata=metadata,
        canceled=canceled,
        text_options=options,
    )


def import_filegdb_points(store, source, layer_name, name, canceled=None):
    """Stream a native point feature class without editing its FileGDB."""
    from osgeo import gdal, ogr
    import pyarrow as pa
    import pyarrow.parquet as pq

    from .data_import import read_sidecar_metadata

    source = Path(source)
    dataset = gdal.OpenEx(str(source), gdal.OF_VECTOR | gdal.OF_READONLY)
    if dataset is None:
        raise ValueError("Cannot open the FileGDB.")
    layer = dataset.GetLayerByName(layer_name)
    if layer is None or ogr.GT_Flatten(layer.GetGeomType()) != ogr.wkbPoint:
        raise ValueError("A single-point FileGDB feature class is required.")
    reference = layer.GetSpatialRef()
    definition = layer.GetLayerDefn()
    fields = [definition.GetFieldDefn(i) for i in range(definition.GetFieldCount())]
    names = [field.GetName() for field in fields]

    def coordinate_name(axis):
        name = f"geometry_{axis}"
        while name.casefold() in {field.casefold() for field in names}:
            name = "source_" + name
        return name

    x, y = coordinate_name("x"), coordinate_name("y")
    arrow_types = {
        ogr.OFTInteger: pa.int64(),
        ogr.OFTInteger64: pa.int64(),
        ogr.OFTReal: pa.float64(),
    }
    schema = pa.schema(
        [(x, pa.float64()), (y, pa.float64())]
        + [
            (field.GetName(), arrow_types.get(field.GetType(), pa.string()))
            for field in fields
        ]
    )
    path = store.root / "results" / f".filegdb_{uuid4().hex}.parquet"
    metadata = read_sidecar_metadata(source)
    metadata.update(
        {
            "crs": reference.ExportToWkt() if reference else None,
            "x_field": x,
            "y_field": y,
            "source_format": "Esri FileGDB",
            "source_layer": layer_name,
            "source_dataset": str(source),
        }
    )
    try:
        with pq.ParquetWriter(path, schema) as writer:
            columns = [[] for _ in schema]
            for index, feature in enumerate(layer):
                if index % 4096 == 0 and canceled and canceled():
                    raise InterruptedError("Survey import cancelled.")
                point = feature.GetGeometryRef()
                xy = (
                    (point.GetX(), point.GetY())
                    if point and not point.IsEmpty()
                    else (None, None)
                )
                values = [feature.GetField(i) for i in range(len(fields))]
                for column, field, value in zip(columns, schema, (*xy, *values)):
                    column.append(
                        str(value)
                        if value is not None and pa.types.is_string(field.type)
                        else value
                    )
                if len(columns[0]) == 4096:
                    writer.write_table(pa.Table.from_arrays(columns, schema=schema))
                    columns = [[] for _ in schema]
            if columns[0]:
                writer.write_table(pa.Table.from_arrays(columns, schema=schema))
        return store.import_file(
            path,
            name=_available_name(store, name),
            metadata=metadata,
            canceled=canceled,
        )
    finally:
        path.unlink(missing_ok=True)
