"""Optional LAS 1.2/2.0 text exchange with retained curve/header metadata.

No datum or unknown curve-unit inference. This is not DLIS/LIS/NMR support.
lasio is optional and never imported while discovering Core operations.
"""

import hashlib
from io import StringIO

import numpy as np

from ._array_contract import as_array


def _read(text, max_text_characters):
    if not isinstance(text, str) or not text.strip() or len(text) > max_text_characters:
        raise ValueError("Nonempty bounded decoded LAS text required")
    try:
        import lasio
    except ImportError as error:
        raise ImportError(
            "LAS exchange requires terraworkbench-core[borehole]"
        ) from error
    las = lasio.read(StringIO(text), ignore_header_errors=False, null_policy="strict")
    if float(las.version["VERS"].value) not in (1.2, 2.0):
        raise ValueError("Only LAS 1.2 and 2.0 supported by this adapter")
    if (
        las.data.ndim != 2
        or not min(las.data.shape)
        or len(las.curves) != las.data.shape[1]
    ):
        raise ValueError(
            "LAS must contain a nonempty curve matrix and matching metadata"
        )
    if np.isinf(las.data).any():
        raise ValueError("Infinite LAS sample values are not valid NoData")
    return las, lasio.__version__


def read_las_text(text, *, depth_unit_override=None, max_text_characters=40_000_000):
    """Read decoded LAS; preserve curve units/descriptions and section headers.

    First curve must be DEPT/DEPTH. Only explicit metre/foot depth units are
    converted to depth_m (international foot=0.3048m). An override is recorded,
    not silently substituted in original metadata. Missing codes become NaN.
    Stored curve_values retain ORIGINAL units, including the depth column.
    Depth need not be increasing: retain order and use log_depth_qc explicitly.
    """
    las, version = _read(text, max_text_characters)
    index = las.curves[0]
    mnemonic = getattr(index, "original_mnemonic", index.mnemonic).upper()
    if mnemonic not in ("DEPT", "DEPTH"):
        raise ValueError("First curve is not a declared depth index DEPT/DEPTH")
    original_unit = index.unit.strip()
    unit = (
        (original_unit if depth_unit_override is None else depth_unit_override)
        .strip()
        .lower()
    )
    factors = {"m": 1.0, "ft": 0.3048}
    if unit not in factors:
        raise ValueError(
            "Depth unit must be declared m or ft, or explicitly overridden"
        )
    values = np.array(las.data, dtype=float, copy=True)
    if not np.isfinite(values[:, 0]).all():
        raise ValueError("Depth index cannot contain NoData")

    def scalar(value):
        return value.item() if isinstance(value, np.generic) else value

    sections = {}
    for name in ("Version", "Well", "Parameter"):
        sections[name] = [
            {
                "mnemonic": item.mnemonic,
                "unit": item.unit,
                "value": scalar(item.value),
                "description": item.descr,
            }
            for item in las.sections[name]
        ]
    curves = [
        {
            "mnemonic": item.mnemonic,
            "original_mnemonic": getattr(item, "original_mnemonic", item.mnemonic),
            "unit": item.unit,
            "description": item.descr,
        }
        for item in las.curves
    ]
    return {
        "depth_m": values[:, 0] * factors[unit],
        "curve_values": values,
        "curves": curves,
        "sections": sections,
        "other": str(las.other),
        "original_depth_unit": original_unit,
        "depth_unit_override": depth_unit_override,
        "decoded_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "engine": "lasio",
        "engine_version": version,
        "datum_note": "Source headers preserved; no CRS or vertical datum assigned",
    }


def update_las_curves(text, curve_values, *, max_text_characters=40_000_000):
    """Replace curve samples in original units, keeping source header metadata.

    Shape must match the original matrix and depth column is immutable here.
    Caller must update geometry/header indexing through a separate explicit
    workflow when resampling depth. Writes LAS 2.0 unwrapped decoded text;
    formatting/comments may be normalized, not a byte-identical round trip.
    """
    las, version = _read(text, max_text_characters)
    values = as_array(curve_values, float)
    if (
        values.shape != las.data.shape
        or np.isinf(values).any()
        or not np.array_equal(values[:, 0], las.data[:, 0])
    ):
        raise ValueError(
            "Matching sample matrix, no infinities and unchanged finite depth required"
        )
    null = float(las.well["NULL"].value)
    if np.any(np.isfinite(values) & (values == null)):
        raise ValueError("Finite sample collides with declared LAS NULL sentinel")
    las.set_data(values.copy())
    output = StringIO()
    # lasio's default %.5f loses small physical channels (e.g. susceptibility)
    # and large-coordinate precision. Seventeen significant digits roundtrip
    # IEEE float64, including scientific notation.
    las.write(output, version=2.0, wrap=False, fmt="%.17g")
    return {
        "text": output.getvalue(),
        "engine": "lasio",
        "engine_version": version,
        "format": "LAS 2.0, unwrapped",
        "curve_units": "unchanged from source",
    }
