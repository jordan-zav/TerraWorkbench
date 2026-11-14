"""Standalone Archie adapter for Terra magnetic products; no host SDK required."""
from __future__ import annotations


def compute_magnetic_products(grid_south_to_north, cell_size, *, inclination,
                              declination, continuation_height=500, padding=16,
                              angle_units="degrees", canceled=None,
                              derivative_method="finite_difference", vertical_positive="down",
                              composite_preparation=None, preserve_rtp_mean=True):
    """Compute products from an nT grid; declination is measured from grid north.

    Arrays retain increasing northing by row. Publication alone reverses rows
    for north-up GeoTIFFs. Field angles must be explicitly supplied in degrees.
    """
    import numpy as np
    from terraworkbench_core.magnetic_pipeline import MagneticPipelineOptions, magnetic_grid_products
    if inclination is None or declination is None:
        raise ValueError("Provide explicit inclination and grid-north declination in degrees.")
    if not np.isfinite([inclination, declination, cell_size, continuation_height]).all():
        raise ValueError("Magnetic field, spacing and continuation must be finite.")
    if cell_size <= 0:
        raise ValueError("Cell size must be positive metres.")
    if not -90 <= inclination <= 90:
        raise ValueError("Inclination must lie between -90 and 90 degrees.")
    if not -180 <= declination <= 180:
        raise ValueError("Grid-north declination must lie between -180 and 180 degrees.")
    values = np.ma.asarray(grid_south_to_north, dtype=np.float64).filled(np.nan)
    if composite_preparation is None:
        composite_preparation = "edge_plane_prediction" if derivative_method == "finite_difference" else "reflect"
    options = MagneticPipelineOptions(
        inclination=float(inclination), declination=float(declination),
        declination_frame="grid", derivative_method=derivative_method, vertical_positive=vertical_positive, composite_preparation=composite_preparation, angle_units=angle_units,
        continuation_height=float(continuation_height), padding_rows=padding,
        padding_columns=padding, detrend_order=-1, taper_percent=0.,
        nodata_policy="nearest", max_gain=100., preserve_rtp_mean=preserve_rtp_mean,
    )
    products, recipe = magnetic_grid_products(values, (float(cell_size), float(cell_size)), options, canceled)
    units = {}
    for name in products:
        if name in ("Tilt", "TDX", "Theta"):
            units[name] = angle_units
        elif name == "DZ2_2VD":
            units[name] = "nT/m^2"
        elif name in ("DX", "DY", "DZ_1VD", "THDR", "AS", "45HG"):
            units[name] = "nT/m"
        else:
            units[name] = "nT"
    recipe.update(
        adapter="archie_magnetic", array_orientation="rows south-to-north; columns west-to-east",
        input_units="nT", spacing_metres=[float(cell_size), float(cell_size)],
        product_units=units, field_source="explicit user values; declination from grid north",
        source_product="explicit caller grid", proprietary_equivalence=False,
        method_revision="archie-magnetic-2: positive-down vertical; central horizontal derivatives by default",
        zero_frequency_policy="Only published RTP preserves the input mean by default; derived products use the original zero-DC workspace",
        limitations=["Induced magnetization follows the supplied field; remanence is not modeled.",
                     "RTP gain is capped at 100; low-inclination stabilization may alter amplitudes.",
                     "All derivatives and continuation branch from RTP; not arbitrary sequential filters.",
                     "NoData is filled only within the FFT workspace; original output mask is restored."],
    )
    return products, recipe
