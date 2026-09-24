"""Connect a tabular ASC survey to native TerraWorkbench raster products.

Run with QGIS Python. Input CRS and channel are explicit; existing output
directories are refused. No ARCHIE, Geosoft runtime or proprietary grid is used.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if os.environ.get("QGIS_PREFIX_PATH"):
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))

import numpy as np
from osgeo import gdal, osr
from qgis.core import QgsApplication, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QUrl, QUrlQuery

from TerraWorkbench.provider import TerraWorkbenchProvider
from TerraWorkbench.raster_io import read_raster, nodata_mask, write_geotiff
from TerraWorkbench.survey_store import SurveyStore
from TerraWorkbench.survey_correction_pipeline import MagneticCorrectionOptions
from TerraWorkbench.text_import import inspect_text


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_values(path):
    grid = read_raster(QgsRasterLayer(str(path), Path(path).stem), 1)
    return grid, np.where(nodata_mask(grid), np.nan, grid.values)


def process(args):
    started = time.perf_counter()
    source, out = args.source.resolve(), args.output.resolve()
    if out.exists():
        raise ValueError("Choose a new output directory; existing results are never overwritten.")
    if not np.isfinite([args.cell_size, args.search_radius, args.median_radius]).all() or min(
        args.cell_size, args.search_radius, args.median_radius
    ) <= 0:
        raise ValueError("Cell size, search radius and median radius must be positive and finite.")
    radius_pixels = args.median_radius / args.cell_size
    if not np.isclose(radius_pixels, round(radius_pixels)) or not 1 <= round(radius_pixels) <= 50:
        raise ValueError("Median radius must be 1–50 whole pixels at the chosen cell size.")
    options, warnings, _ = inspect_text(source)
    with source.open(encoding=options.encoding) as stream:
        source_label = stream.readline().strip()
    raw_track_export = source_label == "Raw track data"
    columns = {c.name: c for c in options.columns}
    for name in (args.x, args.y, args.value, args.line, args.sensor):
        if name not in columns:
            raise ValueError(f"Missing channel: {name}")
    for column in options.columns:
        column.role = ""
    for name, role in ((args.x, "x"), (args.y, "y"), (args.line, "line"), (args.sensor, "sensor")):
        columns[name].role = role
    for name in (args.x, args.y, args.value):
        columns[name].data_type = "float"
    for name in (args.line, args.sensor):
        columns[name].data_type = "text"
    columns[args.value].unit = args.unit
    options.validate()
    source_crs, target_crs = osr.SpatialReference(), osr.SpatialReference()
    source_crs.SetFromUserInput(args.source_crs)
    target_crs.SetFromUserInput(args.target_crs)
    if not target_crs.IsProjected() or not np.isclose(target_crs.GetLinearUnits(), 1.):
        raise ValueError("The target CRS must use projected metre coordinates.")
    for crs in (source_crs, target_crs):
        crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source_crs, target_crs)
    original_hash = checksum(source)
    out.mkdir(parents=True)
    store = SurveyStore(out / "workspace", create=True)
    print("Importing the complete ASC into the versioned survey database", flush=True)
    database = store.import_file(source, text_options=options)
    corrections = None
    grid_channel = args.value
    if getattr(args, "despike_window", 0):
        corrections = store.correct_magnetic(database, args.value, args.time_channel, args.line,
            args.sensor, MagneticCorrectionOptions(max_gap_seconds=args.max_gap_seconds,
                despike_window=args.despike_window, despike_threshold=args.despike_threshold),
            time_scale=args.time_scale, prefix="TW_magnetic")
        grid_channel = corrections["outputs"]["corrected"]

    def project(x, y):
        result = np.asarray(transform.TransformPoints(np.column_stack((x, y))))
        return result[:, 0], result[:, 1]

    store.reproject_coordinates(database, args.x, args.y, args.source_crs, args.target_crs,
        "TW_Easting", "TW_Northing", project, unit="m", details={"engine": "GDAL/PROJ"})
    names = ["TW_Easting", "TW_Northing", grid_channel, args.line, args.sensor]
    collected = {name: [] for name in names}
    for batch in store.batches(database, names):
        for name in names:
            collected[name].append(batch.column(name).to_numpy(zero_copy_only=False))
    data = {name: np.concatenate(parts) for name, parts in collected.items()}
    coordinates = np.column_stack((data[names[0]], data[names[1]]))
    values = data[grid_channel].astype(float)
    valid = np.isfinite(coordinates).all(axis=1) & np.isfinite(values)
    if not np.isfinite(coordinates).all() or (not corrections and not valid.all()):
        raise ValueError("This validation requires finite XY and channel values for every input row.")
    if valid.sum() < 3:
        raise ValueError("Fewer than three valid corrected observations.")
    gridded_rows = int(valid.sum())
    coordinates, values = coordinates[valid], values[valid]
    csv_path = out / "points.csv"
    rows = store.export_csv(database, names, csv_path)
    url, query = QUrl.fromLocalFile(str(csv_path)), QUrlQuery()
    for key, value in {"type": "csv", "delimiter": ",", "xField": names[0], "yField": names[1],
                       "crs": args.target_crs, "detectTypes": "yes", "decimalPoint": "."}.items():
        query.addQueryItem(key, value)
    url.setQuery(query)
    points = QgsVectorLayer(url.toString(), "Survey points", "delimitedtext")
    if not points.isValid() or points.featureCount() != rows:
        raise ValueError("QGIS point bridge lost observations.")
    import processing
    products, operations = {}, []

    def run(name, algorithm, parameters, input_path=None):
        path = out / (name + ".tif")
        recipe = dict(parameters)
        if input_path is not None:
            recipe.update(INPUT=str(input_path), BAND=1)
        operations.append({"product": name, "algorithm": algorithm, "parameters": recipe})
        params = dict(parameters, OUTPUT=str(path))
        params["INPUT"] = points if input_path is None else QgsRasterLayer(str(input_path), name)
        if input_path is not None:
            params["BAND"] = 1
        print("Processing " + name, flush=True)
        processing.run("terraworkbench:" + algorithm, params)
        products[name] = path
        return path

    grid_method_names = {
        "idw": 0,
        "nearest": 1,
        "minimum-curvature": 5,
        "local-tps": 3,
        "sinc": 4,
    }
    grid_method = getattr(args, "grid_method", "idw")
    if grid_method not in grid_method_names:
        raise ValueError("Unknown grid method: " + str(grid_method))
    grid_parameters = {
        "VALUE_FIELD": grid_channel,
        "TARGET_CRS": args.target_crs,
        "METHOD": grid_method_names[grid_method],
        "CELL_SIZE": args.cell_size,
        "SEARCH_RADIUS": args.search_radius,
        "NEIGHBORS": 12,
        "POWER": 2.,
    }
    if grid_method == "minimum-curvature":
        coarse_value = getattr(args, "rangrid_coarse_grid", 16)
        coarse_index = getattr(args, "rangrid_coarse_grid_index", None)
        if coarse_index is None:
            coarse_index = (16, 8, 4, 2, 1).index(int(coarse_value))
        grid_parameters.update({
            "RANGRID_TOLERANCE": getattr(args, "rangrid_tolerance", .01258),
            "RANGRID_PASS_TOLERANCE": getattr(args, "rangrid_pass_tolerance", 99.),
            "RANGRID_MAX_ITERATIONS": getattr(args, "rangrid_max_iterations", 100),
            "RANGRID_TENSION": getattr(args, "rangrid_tension", 0.),
            "RANGRID_COARSE_GRID": coarse_index,
            "RANGRID_SEARCH_RADIUS": getattr(args, "rangrid_search_radius", 8.),
            "RANGRID_BLANKING": getattr(args, "rangrid_blanking", 3.),
            "RANGRID_DESAMPLE": getattr(args, "rangrid_desample", 1),
            "RANGRID_WEIGHT_POWER": getattr(args, "rangrid_weight_power", 2.),
            "RANGRID_WEIGHT_SLOPE": getattr(args, "rangrid_weight_slope", 0.),
        })
    elif grid_method == "sinc":
        grid_parameters.update({
            "SINC_RADIUS": getattr(args, "sinc_radius", 4),
            "SINC_SPACING": getattr(args, "sinc_spacing", 0.),
            "SINC_BLANKING": getattr(args, "sinc_blanking", 3.),
        })
    base = run("field", "grid_survey_points", grid_parameters)
    background = run("median_background", "circular_median", {"RADIUS": round(radius_pixels)}, base)
    grid, field = read_values(base)
    _, median = read_values(background)
    residual = out / "median_residual.tif"
    grid.metadata = dict(grid.metadata, TW_PROCESS="field minus circular median background",
                         TW_UNIT=args.unit, TW_RECIPE="report.json")
    write_geotiff(str(residual), field - median, grid, "Circular median residual", output_nodata=np.nan)
    products["median_residual"] = residual
    operations.append({"product": "median_residual", "expression": "field - median_background"})
    run("residual_smooth", "smooth_nine_point", {"PASSES": 2}, residual)
    for axis in ("easting", "northing", "upward"):
        run("residual_derivative_" + axis, "fft_derivative_" + axis, {
            "ORDER": 1, "FFT_DETREND_ORDER": 1, "FFT_PADDING_PERCENT": 25.,
            "FFT_TAPER_PERCENT": 100., "FFT_RESTORE_TREND": 0}, residual)

    # Independently check output values. IDW has a direct brute-force reference;
    # the other interpolators are checked for finite, supported output without
    # pretending that their kernels reduce to IDW.
    cells = np.argwhere(np.isfinite(field))
    if not len(cells):
        raise AssertionError("Gridding produced no supported cells.")
    sample = cells[np.linspace(0, len(cells) - 1, min(32, len(cells)), dtype=int)]
    gt = grid.geotransform
    errors = []
    median_errors = []
    radius = round(radius_pixels)
    for row, col in sample:
        xy = [gt[0] + (col + .5) * gt[1], gt[3] + (row + .5) * gt[5]]
        distance = np.sqrt(np.sum((coordinates - xy) ** 2, axis=1))
        if grid_method == "idw":
            nearest = np.argsort(distance)[:12]
            nearest = nearest[distance[nearest] < args.search_radius]
            exact = nearest[distance[nearest] <= np.finfo(float).eps]
            expected = values[exact[0]] if len(exact) else np.average(values[nearest], weights=distance[nearest] ** -2)
            errors.append(abs(float(field[row, col]) - float(expected)))
        else:
            errors.append(0.0 if np.isfinite(field[row, col]) else np.inf)
        disk = [field[r, c] for r in range(max(0, row-radius), min(field.shape[0], row+radius+1))
                for c in range(max(0, col-radius), min(field.shape[1], col+radius+1))
                if (r-row)**2 + (c-col)**2 <= radius**2]
        median_errors.append(abs(float(median[row, col]) - float(np.nanmedian(disk))))
    mask = np.isfinite(field)
    checks = {}
    for name, path in products.items():
        unit = args.unit + "/m" if "derivative" in name else args.unit
        ds = gdal.Open(str(path), gdal.GA_Update)
        ds.GetRasterBand(1).SetUnitType(unit)
        ds.SetMetadataItem("TW_RECIPE", "report.json")
        ds = None
        actual, array = read_values(path)
        same_mask = np.array_equal(np.isfinite(array), mask)
        same_geometry = actual.geotransform == grid.geotransform and bool(
            osr.SpatialReference(wkt=actual.projection).IsSame(target_crs))
        checks[name] = {"path": str(path), "sha256": checksum(path), "unit": unit,
                       "mask_preserved": same_mask, "geometry_preserved": same_geometry,
                       "finite_cells": int(np.isfinite(array).sum()),
                       "passed": same_mask and same_geometry and not np.isinf(array).any()}
    _, residual_values = read_values(residual)
    tolerance = float(max(1e-6, np.nanmax(abs(field)) * np.finfo(np.float32).eps * 4))
    reconstruction_error = float(np.nanmax(abs(field - median - residual_values)))
    unchanged = checksum(source) == original_hash
    report = {"source": str(source), "source_sha256": original_hash,
        "source_unchanged": unchanged, "observations": rows,
        "lines": len(set(data[args.line])), "sensors": sorted(set(data[args.sensor])),
        "source_channel": args.value, "source_crs": args.source_crs, "target_crs": args.target_crs,
        "gridded_channel": grid_channel, "gridded_rows": gridded_rows,
        "excluded_null_rows": rows - gridded_rows, "corrections": corrections,
        "source_kind": "raw_track_export" if raw_track_export else "tabular_ASC",
        "text_layout": {"header_row": options.header_row, "data_row": options.data_row,
                        "delimiter": options.delimiter, "encoding": options.encoding},
        "line_channel": args.line,
        "line_sensor_pairs": len(set(zip(data[args.line], data[args.sensor]))),
        "grid_shape": list(field.shape), "supported_cells": int(mask.sum()),
        "missing_cells": int((~mask).sum()), "database_id": database,
        "channel_versions": {c["name"]: c["version_id"] for c in store.channels(database)},
        "operations": operations, "products": checks, "import_warnings": warnings,
        "independent_checks": {"sampled_cells": len(sample), "grid_method": grid_method,
            "idw_max_abs_error": max(errors) if grid_method == "idw" else None,
            "interpolator_accuracy_validated": grid_method == "idw",
            "median_max_abs_error": max(median_errors), "residual_reconstruction_error": reconstruction_error,
            "float32_tolerance": tolerance},
        "limitations": ["Starts from an exported ASC channel, not the native PMXLF binary; upstream export processing is not independently reproduced.",
            "No diurnal, lag, heading, sensor calibration, crossover leveling or height correction is applied by this runner.",
            "A circular-median residual is not a line-leveling correction.",
            "Source CRS is an explicit caller declaration; ASC does not embed a CRS.",
            "One survey, all sensors together at their supplied coordinates; no cross-flight fusion or height normalization.",
            "Grid/filter parameters are a reproducible processing example, not an archaeological interpretation.",
            "No equivalence to ARCHIE/Oasis filters or eight-million-point performance certification.",
            "No RTP: derivatives are of the median residual without an assumed geomagnetic field."],
        "libraries": {"numpy": np.__version__, "gdal": gdal.VersionInfo()},
        "elapsed_seconds": time.perf_counter() - started}
    report["passed"] = bool(unchanged and all(c["passed"] for c in checks.values())
        and max(errors) <= tolerance and max(median_errors) <= tolerance and reconstruction_error <= tolerance)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "observations", "lines", "sensors", "grid_shape", "elapsed_seconds")}), flush=True)
    if not report["passed"]:
        raise AssertionError("Processing validation failed; inspect report.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--x", default="Longitude [°]")
    parser.add_argument("--y", default="Latitude [°]")
    parser.add_argument("--line", default="Line_ID")
    parser.add_argument("--sensor", default="Sensor ID")
    parser.add_argument("--value", required=True)
    parser.add_argument("--unit", default="nT")
    parser.add_argument("--source-crs", required=True)
    parser.add_argument("--target-crs", required=True)
    parser.add_argument("--cell-size", type=float, default=.25)
    parser.add_argument("--search-radius", type=float, default=1.)
    parser.add_argument("--grid-method", choices=("idw", "nearest", "minimum-curvature", "local-tps", "sinc"), default="idw")
    parser.add_argument("--rangrid-tolerance", type=float, default=.01258)
    parser.add_argument("--rangrid-pass-tolerance", type=float, default=99.)
    parser.add_argument("--rangrid-max-iterations", type=int, default=100)
    parser.add_argument("--rangrid-tension", type=float, default=0.)
    parser.add_argument("--rangrid-coarse-grid", type=int, choices=(16, 8, 4, 2, 1), default=16)
    parser.add_argument("--rangrid-search-radius", type=float, default=8.)
    parser.add_argument("--rangrid-blanking", type=float, default=3.)
    parser.add_argument("--rangrid-desample", type=int, default=1)
    parser.add_argument("--rangrid-weight-power", type=float, default=2.)
    parser.add_argument("--rangrid-weight-slope", type=float, default=0.)
    parser.add_argument("--sinc-radius", type=int, default=4)
    parser.add_argument("--sinc-spacing", type=float, default=0.)
    parser.add_argument("--sinc-blanking", type=float, default=3.)
    parser.add_argument("--median-radius", type=float, default=2.5)
    parser.add_argument("--despike-window", type=int, default=0)
    parser.add_argument("--despike-threshold", type=float, default=6.)
    parser.add_argument("--time-channel", default="Timestamp [ms]")
    parser.add_argument("--time-scale", type=float, default=.001)
    parser.add_argument("--max-gap-seconds", type=float, default=.02)
    args = parser.parse_args()
    gdal.UseExceptions()
    app = QgsApplication([], False)
    app.initQgis()
    from processing.core.Processing import Processing
    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    process(args)


if __name__ == "__main__":
    main()
