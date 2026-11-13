"""Construct survey map geometry from row-aligned SurveyStore observations."""

from dataclasses import dataclass, replace
from datetime import date as _Date, datetime
import json
import re

import numpy as np

from .survey_text_import import _role


@dataclass(frozen=True)
class MapChannels:
    """Channel names used to place a survey database on the map.

    Each field holds the channel that supplies easting, northing, CRS, line
    identifier, sample order (fiducial or time), acquisition date and declared
    line type. None means the database does not provide that role.
    """

    x: str | None
    y: str | None
    crs: str | None
    line: str | None
    fiducial: str | None
    time: str | None
    date: str | None
    line_type: str | None


@dataclass(frozen=True)
class FlightSegment:
    """One continuous piece of a survey line, split at distance gaps.

    Holds the line label and number, segment index, kind (traverse, tie or
    other), whether the kind came from metadata or was inferred, mean azimuth,
    length in metres, ordered map coordinates, date range and local line
    spacing when it could be measured.
    """

    line: str
    number: str
    segment: int
    kind: str
    type_source: str
    azimuth: float | None
    length_m: float
    xy: np.ndarray
    date_start: str | None
    date_end: str | None
    spacing_m: float | None = None


@dataclass(frozen=True)
class SurveyMap:
    """Map layers derived from a survey database, independent of QGIS.

    Contains the CRS as WKT, valid sample coordinates and attributes, flight
    line segments, the coverage boundary geometry and a summary with line
    counts, measured spacings, total kilometres and the boundary buffer.
    """

    crs_wkt: str
    sample_xy: np.ndarray
    samples: object
    segments: tuple[FlightSegment, ...]
    boundary: object
    summary: dict


def _key(name):
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def survey_map_channels(store, database_id):
    """Resolve configured channels, import roles and unambiguous header aliases."""
    database = next(row for row in store.databases() if row["id"] == database_id)
    metadata = json.loads(database["metadata"])
    rows = store.channels(database_id)
    names = {row["name"] for row in rows}
    by_id = {row["id"]: row["name"] for row in rows}
    geometry = metadata.get("geometry", {})
    roles = metadata.get("channel_roles", {})

    def find(role, aliases=()):
        configured = by_id.get(geometry.get(f"{role}_channel_id"))
        imported = by_id.get(roles.get(role))
        field = metadata.get(f"{role}_field")
        candidates = [
            name for name in names if _role(name) == role or _key(name) in aliases
        ]
        return (
            configured
            or imported
            or (field if field in names else None)
            or (candidates[0] if len(candidates) == 1 else None)
        )

    channels = MapChannels(
        find("x"),
        find("y"),
        geometry.get("crs") or metadata.get("crs"),
        find("line", ("lineandsegment", "flightline", "flightlineid")),
        find("fiducial", ("fid", "fiducial", "fiducialnumber", "sampleorder")),
        find("time"),
        find("date", ("year", "surveyyear", "surveydate", "acquisitiondate")),
        find("line_type", ("linetype", "flightlinetype", "tracktype")),
    )
    return channels, metadata


def _number(values):
    result = np.full(len(values), np.nan)
    for index, value in enumerate(values):
        try:
            result[index] = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
    return result


def _time_order(values):
    numeric = _number(values)
    if np.isfinite(numeric).all():
        return numeric
    result = []
    for value in values:
        try:
            date = (
                np.datetime64(value, "us")
                if isinstance(value, (str, datetime, _Date))
                else np.datetime64("NaT")
            )
        except ValueError:
            date = np.datetime64("NaT")
        result.append(np.nan if np.isnat(date) else date.astype(np.int64))
    return np.asarray(result)


def _axial(vectors, weights):
    if not len(vectors) or not np.any(weights):
        return None
    angles = np.arctan2(vectors[:, 0], vectors[:, 1])
    mean = np.average(np.exp(2j * angles), weights=weights)
    if abs(mean) < 0.55:
        return None
    return float(np.degrees(np.angle(mean)) / 2 % 180)


def _line_kind(value):
    key = _key(str(value))
    if key in {"traverse", "flight", "flightline", "survey", "normal", "traverseline"}:
        return "traverse"
    if key in {"tie", "tieline", "control", "crossline"}:
        return "tie"
    if key in {"other", "test", "base", "calibration", "special", "random"}:
        return "other"
    return None


def _line_label(value):
    if value is None or isinstance(value, float) and not np.isfinite(value):
        return None
    return str(value).strip() or None


def _classify(lines, line_metadata, declared_direction):
    """Prefer explicit types and avoid assigning ties to isolated orientations."""
    classes = {}
    for name, data in lines.items():
        detail = line_metadata.get(name, {})
        explicit = _line_kind(detail.get("kind")) or _line_kind(detail.get("type"))
        types = {_line_kind(value) for value in data["types"]} - {None}
        if explicit:
            classes[name] = explicit, "metadata"
        elif len(types) == 1:
            classes[name] = types.pop(), "metadata"
        elif len(types) > 1:
            classes[name] = "other", "ambiguous"
        elif re.match(r"^(?:FL(?:[ _-]|\d|$)|L[ _-]?\d)", name, re.I):
            classes[name] = "traverse", "prefix"
        elif re.match(r"^(?:TL(?:[ _-]|\d|$)|T[ _-]?\d)", name, re.I):
            classes[name] = "tie", "prefix"

    bearings = {
        name: data["azimuth"]
        for name, data in lines.items()
        if data["azimuth"] is not None
    }
    primary = declared_direction
    if primary is None:
        known = [
            angle
            for name, angle in bearings.items()
            if classes.get(name, (None,))[0] == "traverse"
        ]
        candidates = np.asarray(
            known or [angle for name, angle in bearings.items() if name not in classes]
        )
        if len(candidates) >= 3:
            anchors = np.arange(180)
            offsets = np.abs((anchors[:, None] - candidates + 90) % 180 - 90)
            members = offsets <= 15
            best = members[np.argmax(members.sum(axis=1))]
            if best.sum() >= 3 and (known or best.mean() > 0.5):
                primary = float(
                    np.degrees(
                        np.angle(np.exp(2j * np.deg2rad(candidates[best])).mean())
                    )
                    / 2
                    % 180
                )
    perpendicular = {}
    for name, angle in bearings.items():
        if primary is None or name in classes:
            continue
        offset = abs((angle - primary + 90) % 180 - 90)
        if offset <= 15:
            classes[name] = "traverse", "direction"
        elif offset >= 75:
            perpendicular[name] = angle
    if len(perpendicular) >= 2:
        classes.update({name: ("tie", "direction") for name in perpendicular})
    return classes


def _line_identity(name):
    # Separate segment suffixes of conventional flight identifiers, not arbitrary
    # numeric line names. Segments from the same flight are not neighbouring tracks.
    match = re.match(r"^([A-Za-z]+[ _-]?\d+)[-.]\d+$", name)
    return match.group(1).casefold() if match else name


def _spacing(lines, classes, kind):
    """Local parallel-track spacing, robust to blocks and fragmented flight IDs.

    Compare chords of continuous pieces in each piece's own reference frame.
    A neighbour must overlap longitudinally without crossing the reference chord.
    Collapse piece estimates to a length-weighted median per line identifier,
    then take the unweighted median over those identifiers.
    """
    records = []
    for name, line in lines.items():
        if classes.get(name, (None,))[0] != kind:
            continue
        for points in line.get("parts", [line["xy"]]):
            if len(points) > 1 and np.linalg.norm(points[-1] - points[0]) > 1:
                records.append((name, points))
    if not records:
        return None, None, {}
    starts = np.asarray([points[0] for _, points in records])
    ends = np.asarray([points[-1] for _, points in records])
    chords = ends - starts
    centers = (starts + ends) / 2
    bearings = np.degrees(np.arctan2(chords[:, 0], chords[:, 1])) % 180
    lengths = np.asarray(
        [np.linalg.norm(np.diff(points, axis=0), axis=1).sum() for _, points in records]
    )
    mean = np.average(np.exp(2j * np.deg2rad(bearings)), weights=lengths)
    azimuth = float(np.degrees(np.angle(mean)) / 2 % 180) if abs(mean) >= 0.65 else None
    identities = np.asarray([_line_identity(name) for name, _ in records])
    estimates = {}
    for index, (name, _) in enumerate(records):
        angle = np.deg2rad(bearings[index])
        axis = np.array([np.sin(angle), np.cos(angle)])
        normal = np.array([np.cos(angle), -np.sin(angle)])
        along = (centers - centers[index]) @ axis
        across = (centers - centers[index]) @ normal
        projected_chords = chords @ axis
        half = np.abs(projected_chords) / 2
        lower = np.maximum(-half[index], along - half)
        upper = np.minimum(half[index], along + half)
        slope = np.divide(
            chords @ normal,
            projected_chords,
            out=np.zeros(len(records)),
            where=np.abs(projected_chords) > 1e-6,
        )
        first = across + (lower - along) * slope
        last = across + (upper - along) * slope
        distances = np.abs((first + last) / 2)
        parallel = np.abs((bearings[index] - bearings + 90) % 180 - 90) <= 15
        eligible = (
            parallel
            & (upper > lower)
            & (first * last > 0)
            & (distances > 1)
            & (identities != identities[index])
        )
        if eligible.any():
            estimates.setdefault(name, []).append(
                (float(distances[eligible].min()), lengths[index])
            )
    local = {}
    for name, pairs in estimates.items():
        values, weights = np.asarray(sorted(pairs)).T
        local[name] = float(
            values[np.searchsorted(np.cumsum(weights), weights.sum() / 2)]
        )
    return (float(np.median(list(local.values()))) if local else None), azimuth, local


def _working_coordinates(source, xy):
    from pyproj import CRS, Transformer

    crs = CRS.from_user_input(source)
    if crs.is_geographic:
        valid = np.isfinite(xy).all(axis=1) & (np.abs(xy) <= [180, 90]).all(axis=1)
        if not valid.any():
            raise ValueError("The survey has no valid longitude/latitude samples.")
        longitude = np.degrees(np.angle(np.exp(1j * np.deg2rad(xy[valid, 0])).mean()))
        latitude = float(np.median(xy[valid, 1]))
        metric = CRS.from_proj4(
            f"+proj=aeqd +lon_0={longitude} +lat_0={latitude} +datum=WGS84 +units=m"
        )
        transform = Transformer.from_crs(crs, metric, always_xy=True)
        output = np.full_like(xy, np.nan)
        output[valid] = np.column_stack(transform.transform(*xy[valid].T.tolist()))
        return output, metric, 1.0
    if not crs.is_projected or len(crs.axis_info) < 2:
        raise ValueError(
            "Survey mapping requires a geographic or projected horizontal CRS."
        )
    factor = crs.axis_info[0].unit_conversion_factor
    if not factor or factor != crs.axis_info[1].unit_conversion_factor:
        raise ValueError("Survey map axes must use consistent linear units.")
    return xy * factor, crs, factor


def _positive_metadata(metadata, key):
    try:
        value = float(metadata.get(key, ""))
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) and value >= 0 else None


def build_survey_map(
    store,
    database_id,
    *,
    channels=None,
    sample_columns=(),
    filters=None,
    max_gap_m=None,
    canceled=None,
    boundary_builder=None,
):
    """Read a store snapshot and construct lines and a buffered coverage estimate.

    Lengths and thresholds are metres. Geographic samples are projected to a local
    azimuthal equidistant CRS. Original channels in the sample table stay unchanged.
    An optional boundary_builder receives metric line arrays, valid metric sample
    coordinates, a BoundaryPlan and output unit factor, and returns an object with
    WKB bytes. The default standalone builder requires the survey-map extra.
    """
    import pyarrow as pa

    detected, metadata = survey_map_channels(store, database_id)
    channels = channels or detected
    if not channels.x or not channels.y or channels.x == channels.y or not channels.crs:
        raise ValueError("Choose distinct X and Y channels and a valid CRS.")
    if max_gap_m is not None and (not np.isfinite(max_gap_m) or max_gap_m <= 0):
        raise ValueError("Maximum line gap must be positive and finite.")
    selected = list(
        dict.fromkeys(
            name
            for name in (
                channels.x,
                channels.y,
                channels.line,
                channels.fiducial,
                channels.time,
                channels.date,
                channels.line_type,
                *sample_columns,
            )
            if name
        )
    )
    batches = list(
        store.batches(database_id, selected, filters=filters, canceled=canceled)
    )
    if not batches:
        raise ValueError("There are no observations in the selected survey.")
    table = pa.Table.from_batches(batches)
    xy, crs, factor = _working_coordinates(
        channels.crs,
        np.column_stack(
            [_number(table[name].to_pylist()) for name in (channels.x, channels.y)]
        ),
    )
    valid = np.isfinite(xy).all(axis=1)
    if not valid.any():
        raise ValueError("The survey has no valid coordinate pairs.")
    labels = table[channels.line].to_pylist() if channels.line else []
    grouping = {}
    for index, value in enumerate(labels):
        name = _line_label(value)
        if name is not None:
            grouping.setdefault(name, []).append(index)
    fiducial = (
        _number(table[channels.fiducial].to_pylist()) if channels.fiducial else None
    )
    time = _time_order(table[channels.time].to_pylist()) if channels.time else None
    dates = (
        table[channels.date or channels.time].to_pylist()
        if channels.date or channels.time
        else None
    )
    types = table[channels.line_type].to_pylist() if channels.line_type else None

    lines, segmented, sample_steps = {}, {}, []
    for name, rows in grouping.items():
        if canceled and canceled():
            raise InterruptedError("Survey map cancelled.")
        indexes = np.asarray(rows)
        order = next(
            (
                key[indexes]
                for key in (fiducial, time)
                if key is not None
                and np.isfinite(key[indexes]).all()
                and np.ptp(key[indexes]) > 0
            ),
            None,
        )
        if order is not None:
            indexes = indexes[np.argsort(order, kind="stable")]
        differences = np.diff(xy[indexes], axis=0)
        distances = np.linalg.norm(differences, axis=1)
        positive = distances[np.isfinite(distances) & (distances > 0)]
        if positive.size:
            sample_steps.append(float(np.median(positive)))
        segmented[name] = indexes, distances, positive

    nominal_sample = float(np.median(sample_steps)) if sample_steps else 100.0
    pieces = {}
    for name, (indexes, distances, positive) in segmented.items():
        typical = float(np.median(positive)) if positive.size >= 3 else nominal_sample
        gap = max_gap_m if max_gap_m is not None else 10 * typical
        parts = np.split(
            indexes, np.flatnonzero(~np.isfinite(distances) | (distances > gap)) + 1
        )
        parts = [
            part
            for part in parts
            if part.size > 1 and valid[part].all() and np.any(np.diff(xy[part], axis=0))
        ]
        points = xy[indexes[valid[indexes]]]
        vectors = (
            np.concatenate([np.diff(xy[part], axis=0) for part in parts])
            if parts
            else np.empty((0, 2))
        )
        if points.size:
            lines[name] = {
                "xy": points,
                "parts": [xy[part] for part in parts],
                "center": np.median(points, axis=0),
                "azimuth": _axial(vectors, np.linalg.norm(vectors, axis=1)),
                "types": [types[i] for i in indexes] if types else [],
            }
            pieces[name] = parts
    direction = _positive_metadata(metadata, "LINE_DIRECTION")
    line_metadata = metadata.get("line_metadata", {})
    classes = _classify(lines, line_metadata, direction)
    segments, geometries = [], []
    for name, parts in pieces.items():
        kind, source = classes.get(name, ("other", "unclassified"))
        detail = line_metadata.get(name, {})
        number = detail.get("number")
        if number is None:
            match = re.match(r"^(?:FL|TL|L|T)?[ _-]?(\d+)(?:[-.]|$)", name, re.I)
            number = match.group(1) if match else name
        for segment_id, part in enumerate(parts, 1):
            points = xy[part]
            vectors = np.diff(points, axis=0)
            distances = np.linalg.norm(vectors, axis=1)
            stamps = sorted(
                str(dates[index])
                for index in part
                if dates and dates[index] is not None and str(dates[index]).strip()
            )
            if not stamps and detail.get("date"):
                stamps = [str(detail["date"])]
            segments.append(
                FlightSegment(
                    name,
                    str(number),
                    segment_id,
                    kind,
                    source,
                    _axial(vectors, distances),
                    float(distances.sum()),
                    points / factor,
                    stamps[0] if stamps else None,
                    stamps[-1] if stamps else None,
                )
            )
            geometries.append(points)

    measured = {kind: _spacing(lines, classes, kind) for kind in ("traverse", "tie")}
    local_spacing = {
        name: value for result in measured.values() for name, value in result[2].items()
    }
    segments = [
        replace(segment, spacing_m=local_spacing.get(segment.line))
        for segment in segments
    ]
    nominal_line = _positive_metadata(metadata, "LINE_SPACING")
    plan = _boundary_plan(segments, measured, nominal_line, nominal_sample)
    if boundary_builder is None:
        boundary_builder = _shapely_boundary
    boundary = boundary_builder(geometries, xy[valid], plan, factor)
    mapped_lines = {segment.line: segment.kind for segment in segments}
    summary = {
        "has_line_channel": bool(channels.line),
        "line_channel": channels.line,
        "samples": int(valid.sum()),
        "invalid_samples": int((~valid).sum()),
        "line_ids": len(grouping),
        "mapped_lines": len(mapped_lines),
        "segments": len(segments),
        "counts": {
            kind: list(mapped_lines.values()).count(kind)
            for kind in ("traverse", "tie", "other")
        },
        "traverse_spacing_m": measured["traverse"][0],
        "tie_spacing_m": measured["tie"][0],
        "traverse_azimuth_deg": measured["traverse"][1],
        "tie_azimuth_deg": measured["tie"][1],
        "declared_traverse_spacing_m": nominal_line,
        "declared_traverse_azimuth_deg": direction,
        "total_km": sum(segment.length_m for segment in segments) / 1000,
        "line_spacing_m": local_spacing,
        "boundary_method": "buffer_close_fill"
        if geometries and plan.spacing_m
        else "concave_hull",
        "boundary_buffer_m": plan.spacing_m / 2
        if geometries and plan.spacing_m
        else None,
        "boundary_closing_m": plan.closing_m,
        "boundary_hole_area_m2": plan.hole_area_m2,
        "boundary_fragment_area_m2": plan.fragment_area_m2,
        "boundary_simplify_m": plan.simplify_m,
        "max_gap_m": max_gap_m,
    }
    return SurveyMap(
        crs.to_wkt(),
        xy[valid] / factor,
        table.filter(pa.array(valid)),
        tuple(segments),
        boundary,
        summary,
    )


@dataclass(frozen=True)
class BoundaryPlan:
    """Metre-based coverage parameters shared by standalone and host GEOS."""

    spacing_m: float | None
    line_buffer_m: tuple[float, ...]
    closing_m: float
    hole_area_m2: float
    fragment_area_m2: float
    simplify_m: float
    degenerate_buffer_m: float
    concavity: float = 0.3


def _boundary_plan(segments, measured, declared, sample_step):
    spacing = (
        (declared or measured["traverse"][0] or measured["tie"][0])
        if segments
        else None
    )
    local = {
        name: value for result in measured.values() for name, value in result[2].items()
    }
    radii = (
        tuple(
            min(declared or local.get(segment.line, spacing), 2 * spacing) / 2
            for segment in segments
        )
        if spacing
        else ()
    )
    return BoundaryPlan(
        spacing,
        radii,
        spacing or 0,
        25 * spacing**2 if spacing else 0,
        25 * spacing**2 if spacing else 0,
        (spacing or sample_step) / 10,
        sample_step / 2,
    )


def _coverage_rings(polygons, plan):
    """Filter polygon parts and holes identically for both geometry backends."""

    def area(ring):
        points = np.asarray(ring, dtype=float)
        # Shift to a local origin to avoid cancellation in large projected grids.
        points = points - points[0]
        return (
            abs(
                float(
                    np.sum(
                        points[:-1, 0] * points[1:, 1] - points[1:, 0] * points[:-1, 1]
                    )
                )
            )
            / 2
        )

    candidates = []
    for rings in polygons:
        holes = [ring for ring in rings[1:] if area(ring) >= plan.hole_area_m2]
        net_area = area(rings[0]) - sum(area(ring) for ring in holes)
        candidates.append(([rings[0], *holes], net_area))
    # A small survey must not disappear merely because it contains fewer than
    # 25 nominal cells. Preserve components comparable to its largest block.
    largest = max((net_area for _, net_area in candidates), default=0)
    minimum = min(plan.fragment_area_m2, largest / 10)
    output = [rings for rings, net_area in candidates if net_area >= minimum]
    return output


def _shapely_boundary(lines, samples, plan, factor):
    """Optional standalone GEOS backend for a consolidated coverage boundary."""
    from shapely import MultiPoint, affinity, concave_hull, union_all
    from shapely.geometry import LineString, MultiPolygon, Polygon

    if lines and plan.spacing_m:
        boundary = union_all(
            [
                LineString(points)
                .simplify(plan.simplify_m, preserve_topology=False)
                .buffer(radius, quad_segs=8)
                for points, radius in zip(lines, plan.line_buffer_m)
            ]
        )
        boundary = boundary.buffer(plan.closing_m, quad_segs=8).buffer(
            -plan.closing_m, quad_segs=8
        )
    else:
        boundary = concave_hull(
            MultiPoint(samples), ratio=plan.concavity, allow_holes=True
        )
        if boundary.geom_type not in {"Polygon", "MultiPolygon"}:
            boundary = boundary.buffer(plan.degenerate_buffer_m, quad_segs=8)
    polygons = [boundary] if boundary.geom_type == "Polygon" else list(boundary.geoms)
    rings = [
        [list(poly.exterior.coords), *[list(ring.coords) for ring in poly.interiors]]
        for poly in polygons
        if poly.geom_type == "Polygon"
    ]
    kept = _coverage_rings(rings, plan)
    if not kept:
        raise ValueError(
            "No survey coverage remains above the fragment area threshold."
        )
    boundary = MultiPolygon([Polygon(rings[0], rings[1:]) for rings in kept])
    boundary = boundary.simplify(plan.simplify_m, preserve_topology=False)
    if not boundary.is_valid:
        boundary = boundary.buffer(0)
    if factor != 1:
        boundary = affinity.scale(boundary, 1 / factor, 1 / factor, origin=(0, 0))
    return boundary
