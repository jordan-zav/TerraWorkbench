"""IGRF on geodetic longitude/latitude and height in km, returning ENU nT.

ppigrf is optional and loaded at execution. Dates outside the packaged SHC
epochs are rejected, not silently extrapolated. No vertical datum is inferred.
"""

from datetime import datetime, timezone
import hashlib
import inspect
from importlib.metadata import version
from pathlib import Path

import numpy as np

from ._array_contract import as_array
from ._calibration import integer_budget
from .preprocessing import magnetic_elements


def igrf_field(
    longitude,
    latitude,
    altitude_km,
    date,
    *,
    chunk_size=2048,
    max_points=10_000_000,
    canceled=None,
):
    """One UTC survey date; finite aligned 1-D positions, east-positive degrees.

    Height is ppigrf's geodetic height convention in km, not orthometric/AGL
    automatically corrected. Longitude must lie in [-180,180], latitude in
    [-90,90]. Cancellation is checked between chunks; outputs are not files.
    Model coefficient hash and epochs describe the actual installed SHC file.
    """
    integer_budget(chunk_size, "Chunk size")
    integer_budget(max_points, "Maximum points")
    lon, lat, height = (
        as_array(value, float) for value in (longitude, latitude, altitude_km)
    )
    if (
        lon.ndim != 1
        or lat.shape != lon.shape
        or height.shape != lon.shape
        or not 0 < lon.size <= max_points
    ):
        raise ValueError(
            "IGRF requires aligned nonempty 1-D longitude, latitude and height within the point budget"
        )
    if (
        not all(np.isfinite(value).all() for value in (lon, lat, height))
        or np.any(abs(lon) > 180)
        or np.any(abs(lat) > 90)
    ):
        raise ValueError(
            "Finite geodetic coordinates in degrees and height in km are required"
        )
    if isinstance(date, str):
        date = datetime.fromisoformat(date.replace("Z", "+00:00"))
    if not isinstance(date, datetime):
        raise ValueError("A single ISO survey date or datetime is required")
    if date.tzinfo is not None:
        date = date.astimezone(timezone.utc).replace(tzinfo=None)
    if canceled is not None and canceled():
        raise RuntimeError("IGRF canceled")
    import ppigrf

    coefficients = Path(inspect.signature(ppigrf.igrf).parameters["coeff_fn"].default)
    with coefficients.open("rb") as stream:
        raw = stream.read(1024**2 + 1)
    if len(raw) > 1024**2:
        raise ValueError("IGRF coefficient file exceeds 1 MiB")
    header = next(
        line
        for line in raw.decode("utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ).split()
    if len(header) < 7:
        raise ValueError("SHC epoch metadata is unavailable")
    start, end = map(float, header[-2:])
    year_start = datetime(date.year, 1, 1)
    year_end = datetime(date.year + 1, 1, 1)
    decimal_year = (
        date.year
        + (date - year_start).total_seconds() / (year_end - year_start).total_seconds()
    )
    if not np.isfinite([start, end]).all() or not start <= decimal_year <= end:
        raise ValueError(
            f"Survey date is outside coefficient epochs {start:g} to {end:g}"
        )
    components = np.empty((3, lon.size))
    for first in range(0, lon.size, chunk_size):
        if canceled is not None and canceled():
            raise RuntimeError("IGRF canceled")
        last = min(first + chunk_size, lon.size)
        response = ppigrf.igrf(
            lon[first:last], lat[first:last], height[first:last], date
        )
        arrays = [as_array(value, float).reshape(-1) for value in response]
        if len(arrays) != 3 or any(
            value.size != last - first or not np.isfinite(value).all()
            for value in arrays
        ):
            raise ValueError("IGRF returned invalid or unsupported component shapes")
        components[:, first:last] = arrays
    if canceled is not None and canceled():
        raise RuntimeError("IGRF canceled")
    total, horizontal, declination, inclination = magnetic_elements(*components)
    return dict(
        engine="ppigrf",
        engine_version=version("ppigrf"),
        east_nt=components[0],
        north_nt=components[1],
        up_nt=components[2],
        total_nt=total,
        horizontal_nt=horizontal,
        declination_degrees=declination,
        inclination_degrees=inclination,
        recipe=dict(
            date_utc=date.isoformat(),
            coordinate_system="geodetic",
            height_units="km",
            field_units="nT",
            axes="east,north,up",
            coefficient_file=coefficients.name,
            coefficient_sha256=hashlib.sha256(raw).hexdigest(),
            epoch_range=[start, end],
            chunk_size=chunk_size,
            scope="No CRS or vertical-datum transformation; no extrapolation",
        ),
    )


def evaluate_igrf(longitude, latitude, altitude_km, date, **options):
    """Compatibility ENU component API for the existing QGIS adapters."""
    result = igrf_field(longitude, latitude, altitude_km, date, **options)
    return [result[key] for key in ("east_nt", "north_nt", "up_nt")]
