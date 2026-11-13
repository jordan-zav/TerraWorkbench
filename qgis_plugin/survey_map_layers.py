"""Write and display a portable QGIS survey map."""

import json
from pathlib import Path
import re
from uuid import uuid4

from .qgis_compat import qt_enum

SURVEY_PROPERTY = "TerraWorkbench/surveyDatabase"
WORKSPACE_PROPERTY = "TerraWorkbench/surveyWorkspace"


def survey_layer_database(project, layer):
    """Resolve a survey group or a layer opened from its workspace package."""
    if layer is None:
        return None
    database = layer.customProperty(SURVEY_PROPERTY, "")
    workspace = layer.customProperty(WORKSPACE_PROPERTY, "")
    if workspace and database:
        return workspace, database
    node = project.layerTreeRoot().findLayer(layer.id())
    while node is not None:
        identity = str(node.customProperty(SURVEY_PROPERTY, ""))
        root, separator, key = identity.rpartition(":")
        if separator and key == database:
            return root, key
        node = node.parent()
    path = Path(layer.source().split("|", 1)[0])
    match = re.fullmatch(r"survey_([0-9a-f]{32})_[0-9a-f]+\.gpkg", path.name)
    if match and path.parent.name == "results" and (path.parent.parent / "catalog.sqlite").is_file():
        return str(path.parent.parent), match[1]
    return None


def qgis_boundary(lines, samples, plan, factor):
    """Consolidated coverage using the same plan and ring filters as Core."""
    from types import SimpleNamespace
    from qgis.core import QgsGeometry, QgsPointXY
    from qgis.PyQt.QtGui import QTransform
    from ..terraworkbench_core.survey_map import _coverage_rings

    if lines and plan.spacing_m:
        buffers = [
            QgsGeometry.fromPolylineXY([QgsPointXY(float(x), float(y)) for x, y in xy])
            .simplify(plan.simplify_m)
            .buffer(radius, 8)
            for xy, radius in zip(lines, plan.line_buffer_m)
        ]
        boundary = QgsGeometry.unaryUnion(buffers)
        boundary = boundary.buffer(plan.closing_m, 8).buffer(-plan.closing_m, 8)
    else:
        boundary = QgsGeometry.fromMultiPointXY(
            [QgsPointXY(float(x), float(y)) for x, y in samples]
        ).concaveHull(plan.concavity, True)
        if boundary.area() == 0:
            boundary = boundary.buffer(plan.degenerate_buffer_m, 8)
    polygons = (
        boundary.asMultiPolygon() if boundary.isMultipart() else [boundary.asPolygon()]
    )
    rings = [
        [[(point.x(), point.y()) for point in ring] for ring in polygon]
        for polygon in polygons
    ]
    kept = _coverage_rings(rings, plan)
    if not kept:
        raise ValueError(
            "No survey coverage remains above the fragment area threshold."
        )
    boundary = QgsGeometry.fromMultiPolygonXY(
        [[[QgsPointXY(x, y) for x, y in ring] for ring in polygon] for polygon in kept]
    ).simplify(plan.simplify_m)
    if not boundary.isGeosValid():
        boundary = boundary.buffer(0, 8)
    if factor != 1:
        boundary.transform(QTransform.fromScale(1 / factor, 1 / factor))
    if boundary.isNull() or boundary.isEmpty() or not boundary.isGeosValid():
        raise ValueError("Could not construct a valid survey boundary.")
    return SimpleNamespace(wkb=bytes(boundary.asWkb()))


def _ogr_field(ogr, arrow_type):
    import pyarrow.types as types

    if types.is_integer(arrow_type) or types.is_boolean(arrow_type):
        return ogr.OFTInteger64
    if types.is_floating(arrow_type):
        return ogr.OFTReal
    return ogr.OFTString


def write_survey_geopackage(store, database_id, survey, canceled=None, progress=None):
    """Write via a private OGR connection. No QGIS project objects enter the worker."""
    from osgeo import ogr, osr

    root = store.root / "results"
    root.mkdir(exist_ok=True)
    target = root / f"survey_{database_id}_{uuid4().hex[:10]}.gpkg"
    staging = target.with_suffix(".partial.gpkg")
    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(staging))
    if dataset is None:
        raise OSError("Could not create the survey GeoPackage.")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(survey.crs_wkt)

    def create(name, geometry, fields):
        layer = dataset.CreateLayer(name, srs, geometry)
        if layer is None:
            raise OSError(f"Could not create layer {name}.")
        for field, field_type in fields:
            if layer.CreateField(ogr.FieldDefn(field, field_type)):
                raise OSError(f"Could not create field {field}.")
        return layer

    def write(layer, rows):
        definition = layer.GetLayerDefn()
        for index, (geometry, values) in enumerate(rows):
            if index % 1024 == 0:
                if canceled and canceled():
                    raise InterruptedError("Survey map cancelled.")
                if progress:
                    progress(index)
            feature = ogr.Feature(definition)
            feature.SetGeometry(geometry)
            for field_index, value in enumerate(values):
                if value is not None:
                    field = definition.GetFieldDefn(field_index)
                    if field.GetType() == ogr.OFTString:
                        value = str(value)
                    feature.SetField(field_index, value)
            if layer.CreateFeature(feature):
                raise OSError(
                    f"Could not write feature {index + 1} to {layer.GetName()}."
                )

    def line_rows(segments):
        for segment in segments:
            line = ogr.Geometry(ogr.wkbLineString)
            for x, y in segment.xy:
                line.AddPoint_2D(float(x), float(y))
            yield (
                line,
                (
                    segment.line,
                    segment.number,
                    segment.segment,
                    segment.kind,
                    segment.type_source,
                    int(segment.type_source in {"prefix", "direction"}),
                    segment.azimuth,
                    segment.length_m,
                    len(segment.xy),
                    segment.date_start,
                    segment.date_end,
                    segment.spacing_m,
                ),
            )

    def sample_rows():
        offset = 0
        for batch in survey.samples.to_batches(max_chunksize=8192):
            columns = [column.to_pylist() for column in batch.columns]
            for (x, y), values in zip(
                survey.sample_xy[offset : offset + batch.num_rows], zip(*columns)
            ):
                point = ogr.Geometry(ogr.wkbPoint)
                point.AddPoint_2D(float(x), float(y))
                yield point, values
            offset += batch.num_rows

    keys = []
    try:
        if dataset.StartTransaction():
            raise OSError("Could not begin the survey GeoPackage transaction.")
        line_fields = [
            ("line_id", ogr.OFTString),
            ("line_number", ogr.OFTString),
            ("segment", ogr.OFTInteger),
            ("line_type", ogr.OFTString),
            ("type_source", ogr.OFTString),
            ("inferred", ogr.OFTInteger),
            ("azimuth", ogr.OFTReal),
            ("length_m", ogr.OFTReal),
            ("samples", ogr.OFTInteger),
            ("date_start", ogr.OFTString),
            ("date_end", ogr.OFTString),
            ("spacing_m", ogr.OFTReal),
        ]
        for name, kind in (
            ("flight_lines", "traverse"),
            ("tie_lines", "tie"),
            ("other_lines", "other"),
        ):
            segments = [segment for segment in survey.segments if segment.kind == kind]
            if segments:
                write(create(name, ogr.wkbLineString, line_fields), line_rows(segments))
                keys.append(name)
        boundary = ogr.ForceToMultiPolygon(
            ogr.CreateGeometryFromWkb(survey.boundary.wkb)
        )
        write(
            create(
                "survey_boundary", ogr.wkbMultiPolygon, [("summary", ogr.OFTString)]
            ),
            [(boundary, (json.dumps(survey.summary),))],
        )
        keys.append("survey_boundary")
        fields = []
        used = {"fid", "geom"}
        for field in survey.samples.schema:
            name = field.name
            while name.casefold() in used:
                name = "source_" + name
            used.add(name.casefold())
            fields.append((name, _ogr_field(ogr, field.type)))
        write(create("samples", ogr.wkbPoint, fields), sample_rows())
        keys.append("samples")
        if dataset.CommitTransaction():
            raise OSError("Could not commit the survey GeoPackage.")
    except BaseException:
        dataset.RollbackTransaction()
        dataset = None
        staging.unlink(missing_ok=True)
        raise
    dataset = None
    staging.replace(target)
    return target, tuple(keys), survey.summary


def _survey_line_symbol(key):
    from qgis.core import (
        Qgis, QgsEllipseSymbolLayer, QgsLineSymbol, QgsMarkerLineSymbolLayer, QgsMarkerSymbol, QgsProperty,
        QgsSimpleLineSymbolLayer, QgsSymbolLayer,
    )

    tie = key == "tie_lines"
    other = key == "other_lines"
    color = "#d4500f" if tie else "#272e34" if other else "#15191d"
    style = "dot" if other else "solid"
    symbol = QgsLineSymbol.createSimple({
        "line_color": "#ffffff" if other else "255,255,255,140",
        "line_width": "1.05" if tie else "0.50" if other else "0.95",
        "line_style": style,
        "capstyle": "round",
    })
    symbol.appendSymbolLayer(QgsSimpleLineSymbolLayer.create({
        "line_color": color,
        "line_width": "0.55" if tie else "0.24" if other else "0.45",
        "line_style": style,
        "capstyle": "round",
    }))
    if other:
        return symbol

    # Use printed millimetres: metres on the ground / scale denominator × 1000.
    # Keep the centre arrow and symmetric repetitions, leaving at least
    # 7 mm between repeated arrows and the endpoint labels.
    length_mm = '1000 * "length_m" / max(@map_scale, 1)'
    interval = 40
    repetitions = f"floor(max(0, ({length_mm} / 2 - 7) / {interval}))"
    markers = QgsMarkerLineSymbolLayer(True, interval)
    unit = qt_enum(Qgis, "RenderUnit", "Millimeters")
    markers.setIntervalUnit(unit)
    markers.setOffsetAlongLineUnit(unit)
    markers.setAverageAngleLength(1.5)
    # The triangle points up at zero rotation. Turn it to the line's forward axis.
    arrow = QgsEllipseSymbolLayer.create({
        "symbol_name": "triangle",
        "symbol_width": "2.1" if tie else "1.9",
        "symbol_height": "3.4" if tie else "3.2",
        "angle": "90",
        "color": "#ffffff",
        "outline_color": color,
        "outline_width": "0.30" if tie else "0.25",
        "joinstyle": "round",
    })
    markers.setSubSymbol(QgsMarkerSymbol([arrow]))
    for name, expression in (
        ("LayerEnabled", "@map_scale <= 150000"),
        ("Placement", f"if({repetitions} > 0, 'interval', 'centerpoint')"),
        ("OffsetAlongLine", f"{length_mm} / 2 - {interval} * {repetitions}"),
    ):
        markers.setDataDefinedProperty(
            getattr(QgsSymbolLayer.Property, name, None)
            or getattr(QgsSymbolLayer, f"Property{name}"),
            QgsProperty.fromExpression(expression),
        )
    symbol.appendSymbolLayer(markers)
    symbol.setClipFeaturesToExtent(False)
    return symbol


def add_survey_map(project, store, database_id, name, package):
    """Load a completed package and publish one styled group on the GUI thread."""
    from qgis.core import (
        Qgis,
        QgsFillSymbol,
        QgsMarkerSymbol,
        QgsPalLayerSettings,
        QgsTextBufferSettings,
        QgsTextFormat,
        QgsSimpleFillSymbolLayer,
        QgsShapeburstFillSymbolLayer,
        QgsVectorLayer,
        QgsVectorLayerSimpleLabeling,
    )
    from qgis.PyQt.QtGui import QColor, QFont

    from ..ui.i18n import language

    path, keys, summary = package
    names = {
        "flight_lines": ("Flight lines", "Líneas de vuelo", "Linhas de voo"),
        "tie_lines": ("Tie lines", "Líneas de control", "Linhas de controle"),
        "other_lines": ("Other lines", "Otras líneas", "Outras linhas"),
        "survey_boundary": (
            "Survey boundary",
            "Contorno del levantamiento",
            "Limite do levantamento",
        ),
        "samples": ("Samples", "Muestras", "Amostras"),
    }
    locale = {"en": 0, "es": 1, "pt": 2}.get(language(), 0)
    layers = {}
    for key in keys:
        layer = QgsVectorLayer(f"{path}|layername={key}", names[key][locale], "ogr")
        if not layer.isValid():
            raise ValueError(f"QGIS could not open survey layer {key}.")
        layer.setCustomProperty(SURVEY_PROPERTY, database_id)
        layer.setCustomProperty(WORKSPACE_PROPERTY, str(store.root))
        metadata = layer.metadata()
        metadata.setTitle(layer.name())
        metadata.setAbstract(json.dumps(summary, ensure_ascii=False, indent=2))
        layer.setMetadata(metadata)
        if key in {"flight_lines", "tie_lines", "other_lines"}:
            layer.renderer().setSymbol(_survey_line_symbol(key))
            labels = QgsPalLayerSettings()
            labels.fieldName = "line_number"
            labels.geometryGeneratorEnabled = True
            labels.geometryGenerator = (
                "collect_geometries(start_point($geometry), end_point($geometry))"
            )
            labels.geometryGeneratorType = qt_enum(Qgis, "GeometryType", "Point")
            labels.labelPerPart = True
            labels.scaleVisibility = True
            labels.minimumScale = 125000
            labels.maximumScale = 0
            labels.dist = 1.6
            label_format = QgsTextFormat()
            font = QFont("Arial")
            font.setBold(True)
            label_format.setFont(font)
            label_format.setSize(9)
            label_format.setColor(QColor("#b5440c" if key == "tie_lines" else "#15191d"))
            buffer = QgsTextBufferSettings()
            buffer.setEnabled(True)
            buffer.setSize(0.8)
            buffer.setColor(QColor("white"))
            label_format.setBuffer(buffer)
            labels.setFormat(label_format)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(labels))
            layer.setLabelsEnabled(True)
        elif key == "survey_boundary":
            edge = QColor("#00838f")
            glow = QgsShapeburstFillSymbolLayer()
            edge.setAlphaF(0.25)
            glow.setColor(edge)
            edge.setAlpha(0)
            glow.setColor2(edge)
            glow.setUseWholeShape(False)
            glow.setMaxDistance(3)
            glow.setDistanceUnit(qt_enum(Qgis, "RenderUnit", "Millimeters"))
            glow.setIgnoreRings(True)
            boundary = QgsFillSymbol([glow])
            boundary.appendSymbolLayer(QgsSimpleFillSymbolLayer.create({
                "style": "no", "outline_color": "#ffffff", "outline_width": "1.8",
                "joinstyle": "round",
            }))
            boundary.appendSymbolLayer(QgsSimpleFillSymbolLayer.create({
                "style": "no", "outline_color": "#00838f", "outline_width": "0.95",
                "joinstyle": "round",
            }))
            layer.renderer().setSymbol(boundary)
        else:
            layer.renderer().setSymbol(
                QgsMarkerSymbol.createSimple(
                    {
                        "name": "circle",
                        "color": "54,91,107,135",
                        "outline_style": "no",
                        "size": "0.85",
                    }
                )
            )
            layer.setScaleBasedVisibility(True)
            layer.setMinimumScale(50000)
        layers[key] = layer

    root = project.layerTreeRoot()
    identity = f"{Path(store.root).resolve().as_posix()}:{database_id}"
    group = root.insertGroup(0, name)
    group.setCustomProperty(SURVEY_PROPERTY, identity)
    for key, layer in layers.items():
        project.addMapLayer(layer, False)
        node = group.addLayer(layer)
        node.setExpanded(False)
        node.setItemVisibilityChecked(key != "samples")
    for previous in root.findGroups():
        if previous != group and previous.customProperty(SURVEY_PROPERTY) == identity:
            project.removeMapLayers([node.layerId() for node in previous.findLayers()])
            if previous.parent() is not None:
                previous.parent().removeChildNode(previous)
    return layers
