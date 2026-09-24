"""Grid Milligan point data and compare it with a delivered reference grid.

The point CSV is an explicit export of the Geosoft GDB. After that export,
gridding and comparison use TerraWorkbench, QGIS, GDAL and Harmonica only.
The reference grid is read through Harmonica because GDAL does not read native
Oasis Montaj GRD files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from osgeo import osr
from qgis.core import QgsApplication, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QUrl, QUrlQuery

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if os.environ.get("QGIS_PREFIX_PATH"):
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))

from TerraWorkbench.dependencies import import_harmonica
from TerraWorkbench.provider import TerraWorkbenchProvider
from TerraWorkbench.raster_io import read_raster, nodata_mask


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def spatial_reference(code):
    reference = osr.SpatialReference()
    reference.SetFromUserInput(code)
    reference.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points-csv", type=Path, required=True)
    parser.add_argument("--reference-grid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--value", default="f_mtf")
    parser.add_argument("--source-crs", default="EPSG:4326")
    parser.add_argument("--target-crs", default="EPSG:26710")
    parser.add_argument("--cell-size", type=float, default=100.)
    parser.add_argument("--search-radius", type=float, default=1000.)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new output directory; reference data are never overwritten.")
    if not args.points_csv.is_file() or not args.reference_grid.is_file():
        raise FileNotFoundError("Both point CSV and reference GRD are required.")
    started = time.perf_counter()
    args.output.mkdir(parents=True)
    url, query = QUrl.fromLocalFile(str(args.points_csv.resolve())), QUrlQuery()
    for key, value in {"type": "csv", "delimiter": ",", "xField": "p_long",
                       "yField": "p_lat", "crs": args.source_crs,
                       "detectTypes": "yes", "decimalPoint": "."}.items():
        query.addQueryItem(key, value)
    url.setQuery(query)
    points = QgsVectorLayer(url.toString(), "Milligan points", "delimitedtext")
    if not points.isValid():
        raise ValueError("QGIS could not open the exported point CSV.")
    field_index = points.fields().indexOf(args.value)
    if field_index < 0:
        raise ValueError(f"Point channel does not exist: {args.value}")
    import processing
    grid_path = args.output / "milligan_terraworkbench_idw.tif"
    result = processing.run("terraworkbench:grid_survey_points", {
        "INPUT": points, "VALUE_FIELD": args.value, "TARGET_CRS": args.target_crs,
        "METHOD": 0, "CELL_SIZE": args.cell_size, "SEARCH_RADIUS": args.search_radius,
        "NEIGHBORS": 12, "POWER": 2., "OUTPUT": str(grid_path),
    })
    if not Path(result["OUTPUT"]).is_file():
        raise RuntimeError("TerraWorkbench did not publish the point grid.")
    produced = read_raster(QgsRasterLayer(str(grid_path), "Milligan IDW"), 1)
    produced_values = np.where(nodata_mask(produced), np.nan, produced.values)
    hm = import_harmonica()
    reference_data = hm.load_oasis_montaj_grid(args.reference_grid)
    reference = np.asarray(reference_data.values, dtype=float)
    easting = np.asarray(reference_data.easting, dtype=float)
    northing = np.asarray(reference_data.northing, dtype=float)
    out_easting = produced.geotransform[0] + (np.arange(produced_values.shape[1]) + .5) * produced.geotransform[1]
    out_northing = produced.geotransform[3] + (np.arange(produced_values.shape[0]) + .5) * produced.geotransform[5]
    overlap = []
    produced_samples, reference_samples = [], []
    # The point bounding box does not necessarily use the GRD origin. Match
    # each output cell to the nearest 100 m reference cell (within half a cell).
    for output_row, y in enumerate(out_northing):
        ref_row = int(np.rint((y - northing[0]) / args.cell_size))
        if ref_row < 0 or ref_row >= len(northing):
            continue
        if abs(float(northing[ref_row] - y)) > args.cell_size / 2 + 1e-6:
            continue
        for output_col, x in enumerate(out_easting):
            ref_col = int(np.rint((x - easting[0]) / args.cell_size))
            if ref_col < 0 or ref_col >= len(easting):
                continue
            if abs(float(easting[ref_col] - x)) > args.cell_size / 2 + 1e-6:
                continue
            pv, rv = produced_values[output_row, output_col], reference[ref_row, ref_col]
            if np.isfinite(pv) and np.isfinite(rv):
                overlap.append((x, y))
                produced_samples.append(pv)
                reference_samples.append(rv)
    pv, rv = np.asarray(produced_samples), np.asarray(reference_samples)
    if len(pv) < 100:
        raise ValueError(f"Only {len(pv)} finite overlapping cells were found.")
    difference = pv - rv
    correlation = float(np.corrcoef(pv, rv)[0, 1]) if np.std(pv) and np.std(rv) else None
    target = spatial_reference(args.target_crs)
    produced_crs = spatial_reference(produced.projection)
    report = {
        "points_csv": str(args.points_csv.resolve()), "points_sha256": sha256(args.points_csv),
        "reference_grid": str(args.reference_grid.resolve()), "reference_sha256": sha256(args.reference_grid),
        "reference_format": "Oasis Montaj GRD read by Harmonica", "value_channel": args.value,
        "source_crs": args.source_crs, "target_crs": args.target_crs,
        "input_features": points.featureCount(), "output_grid": str(grid_path),
        "output_shape": list(produced_values.shape), "output_finite_cells": int(np.isfinite(produced_values).sum()),
        "reference_shape": list(reference.shape), "reference_finite_cells": int(np.isfinite(reference).sum()),
        "overlap_cells": len(pv), "output_geometry": {"geotransform": list(produced.geotransform),
            "projection_matches_target": bool(produced_crs.IsSame(target))},
        "reference_extent": {"easting": [float(easting.min()), float(easting.max())],
            "northing": [float(northing.min()), float(northing.max())]},
        "comparison": {"correlation": correlation, "bias_output_minus_reference": float(np.mean(difference)),
            "mae": float(np.mean(np.abs(difference))), "rmse": float(np.sqrt(np.mean(difference**2))),
            "max_abs": float(np.max(np.abs(difference))),
            "output_range": [float(np.min(pv)), float(np.max(pv))],
            "reference_range": [float(np.min(rv)), float(np.max(rv))]},
        "interpretation": "This is an IDW reproduction and an overlap comparison. It does not claim byte or cell equality with the unknown Oasis interpolation recipe.",
        "elapsed_seconds": time.perf_counter() - started,
    }
    report["passed"] = bool(report["output_geometry"]["projection_matches_target"] and len(pv) >= 100)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "input_features", "output_shape", "overlap_cells", "comparison", "elapsed_seconds")}, indent=2), flush=True)
    if not report["passed"]:
        raise AssertionError("Milligan validation failed; inspect report.json")


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    from processing.core.Processing import Processing
    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    main()
