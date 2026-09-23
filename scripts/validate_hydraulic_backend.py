"""Read-only Hydraulic reference audit. Run with QGIS Python; no GUI/images.

Writes only a new --output directory. Reference files are SHA256 checked before
and after. This validates a pre-extracted survey, not the original GDB reader.
Historical fill/pad/correction-surface adapters are explicit, not claimed as
native Processing operations. No production algorithm is modified here.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python" / "plugins"))

from qgis.core import (
    QgsApplication, QgsFeature, QgsGeometry, QgsPointXY, QgsProcessingContext,
    QgsProcessingFeedback, QgsRasterLayer, QgsVectorLayer,
)
from osgeo import gdal, osr
import numpy as np

from TerraWorkbench.dependencies import import_harmonica
from TerraWorkbench.provider import TerraWorkbenchProvider
from TerraWorkbench.spectral import frequency_grid, magnetic_field_transform, apply_transfer


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raster(path):
    ds = gdal.Open(str(path), gdal.GA_ReadOnly)
    values = ds.ReadAsArray().astype(float)
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    if nodata is not None:
        values[values == nodata] = np.nan
    transform, projection = ds.GetGeoTransform(), ds.GetProjection()
    ds = None
    return values, transform, projection


def stats(values):
    valid = values[np.isfinite(values)]
    return {"cells": int(values.size), "valid": int(valid.size), "missing": int(values.size - valid.size),
            "min": float(valid.min()), "max": float(valid.max()), "mean": float(valid.mean()),
            "std": float(valid.std()), "p01_p50_p99": np.percentile(valid, [1, 50, 99]).tolist()}


def difference(values, reference):
    both = np.isfinite(values) & np.isfinite(reference)
    delta = values[both] - reference[both]
    return {"common": int(both.sum()), "mask_disagreement": int(np.count_nonzero(np.isfinite(values) != np.isfinite(reference))),
            "bias": float(delta.mean()), "rmse": float(np.sqrt(np.mean(delta**2))),
            "max_abs": float(np.abs(delta).max()), "p50_p95_p99_abs": np.percentile(np.abs(delta), [50, 95, 99]).tolist()}


def write_raster(path, values, transform, projection):
    ds = gdal.GetDriverByName("GTiff").Create(str(path), values.shape[1], values.shape[0], 1,
        gdal.GDT_Float64, options=["COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform(transform)
    ds.SetProjection(projection)
    ds.GetRasterBand(1).SetNoDataValue(float("nan"))
    ds.GetRasterBand(1).WriteArray(values)
    ds = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="NGEA 2027 root")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Output must be a new directory; never overwrite an audit.")
    out.mkdir(parents=True)
    start = time.perf_counter()
    raw = args.root / "Personal/Mag/Raw/line_leveling/results"
    library = args.root / "Shared/Data/Regional Geology, Structural Geology, and Geophysics/Petrofisica_e_Inversion"
    refs = library / "02_Magnetometria/02_Surveys_Corregidos_GDB/Hydraulic"
    consumed = [raw / "extracts/Hydraulic.npz", raw / "extracts/Hydraulic.json",
                raw / "crossover_qc/Hydraulic/crossovers.csv", raw / "crossover_qc/Hydraulic/suggested_line_corrections.csv",
                raw / "crossover_qc/Hydraulic/qc_report.json", refs / "metadata/processing_report.json"]
    consumed += sorted(refs.rglob("*.tif"))
    baseline_meta = read_json(refs / "metadata/processing_report.json")
    original_path = Path(baseline_meta["source_original_grid"])
    consumed.append(original_path)
    print("Hashing reference inputs", flush=True)
    before = {str(p): {"bytes": p.stat().st_size, "sha256": checksum(p)} for p in consumed}
    report = {"survey": "Hydraulic", "scope": "125386 existing extracted valid observations; no raw GDB extraction, GUI, images, inversion or new interpolation benchmark",
              "inputs": before, "stages": {}, "limitations": []}
    (out / "input_manifest.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    import processing
    from processing.core.Processing import Processing
    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    hm = import_harmonica()
    import scipy
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    report["versions"] = {"numpy": np.__version__, "harmonica": hm.__version__, "scipy": scipy.__version__, "gdal": gdal.VersionInfo()}
    context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
    with np.load(raw / "extracts/Hydraulic.npz", allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    print(f"Loaded {len(data['x']):,} observations / {len(data['line_names'])} lines", flush=True)
    source = QgsVectorLayer("Point?crs=EPSG:26910&field=line:string&field=kind:integer&field=order:double&field=mag:double", "Hydraulic", "memory")
    for i, name in enumerate(data["line_names"]):
        first, last = data["offsets"][i:i + 2]
        features = []
        for j in range(int(first), int(last)):
            f = QgsFeature(source.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(data["x"][j]), float(data["y"][j]))))
            f.setAttributes([str(name), int(data["line_types"][i]), float(j), float(data["magnetic"][j])])
            features.append(f)
        source.dataProvider().addFeatures(features)
    source.updateExtents()
    print("Running native crossover_line_leveling on all extracted observations", flush=True)
    result = processing.run("terraworkbench:crossover_line_leveling", {
        "INPUT": source, "VALUE_FIELD": "mag", "LINE_FIELD": "line", "LINE_TYPE_FIELD": "kind",
        "ORDER_FIELD": "order", "TIE_VALUES": "1,nonzero", "OUTLIER_SIGMA": 4.5, "CORRECTION_ORDER": 0,
        "CORRECTED": str(out / "corrected_points.gpkg"), "CROSSOVERS": str(out / "crossovers.gpkg"),
        "CORRECTIONS": str(out / "line_corrections.gpkg")}, context=context, feedback=feedback)
    cross = QgsVectorLayer(result["CROSSOVERS"], "cross", "ogr")
    corr = QgsVectorLayer(result["CORRECTIONS"], "corrections", "ogr")
    constants = {str(f["line"]): float(f["constant"]) for f in corr.getFeatures()}
    rows = list(cross.getFeatures())
    accepted = [f for f in rows if bool(f["accepted"])]
    with (raw / "crossover_qc/Hydraulic/crossovers.csv").open(encoding="utf-8-sig", newline="") as stream:
        ref_cross = list(csv.DictReader(stream))
    with (raw / "crossover_qc/Hydraulic/suggested_line_corrections.csv").open(encoding="utf-8-sig", newline="") as stream:
        ref_constants = {r["line"]: float(r["suggested_correction_nt"]) for r in csv.DictReader(stream)}
    def cross_key(f):
        pt = f.geometry().asPoint()
        return str(f["traverse"]), str(f["tie"]), round(pt.x(), 3), round(pt.y(), 3)
    actual_cross = {cross_key(f): float(f["res_before"]) for f in rows}
    reference_cross = {(r["traverse"], r["tie"], round(float(r["easting"]), 3), round(float(r["northing"]), 3)): float(r["residual_nt"]) for r in ref_cross}
    common = actual_cross.keys() & reference_cross.keys()
    residual_delta = np.array([actual_cross[k] - reference_cross[k] for k in common])
    stage = {"observations": source.featureCount(), "crossovers": len(rows), "accepted": len(accepted),
             "matched_crossovers": len(common), "unmatched_native": len(actual_cross.keys() - reference_cross.keys()),
             "unmatched_reference": len(reference_cross.keys() - actual_cross.keys()),
             "rms_before": float(np.sqrt(np.mean([float(f["res_before"])**2 for f in accepted]))),
             "rms_after": float(np.sqrt(np.mean([float(f["res_after"])**2 for f in accepted]))),
             "crossover_max_abs_delta_nt": float(np.abs(residual_delta).max()) if len(residual_delta) else None,
             "constant_max_abs_delta_nt": max(abs(constants[k] - ref_constants[k]) for k in constants.keys() & ref_constants.keys()),
             "constant_line_names_equal": set(constants) == set(ref_constants),
             "reference_rms_before": baseline_meta["rms_before_nt"], "reference_rms_after": baseline_meta["rms_after_nt"]}
    report["stages"]["native_leveling"] = stage
    print(json.dumps(stage), flush=True)
    (out / "leveling_report.json").write_text(json.dumps(stage, indent=2), encoding="utf-8")

    # Explicit historical workflow adapter: not a new point-grid interpolation.
    print("Reconstructing historical correction-surface adapter using native line constants", flush=True)
    grid = hm.load_oasis_montaj_grid(original_path)
    original = np.asarray(grid.values, dtype=float)
    xg, yg = np.asarray(grid.easting), np.asarray(grid.northing)
    dx, dy = abs(float(np.median(np.diff(xg)))), abs(float(np.median(np.diff(yg))))
    sums, counts = np.zeros_like(original), np.zeros(original.shape, dtype=np.int32)
    for index, name in enumerate(data["line_names"].astype(str)):
        if name not in constants:
            continue
        first, last = data["offsets"][index:index + 2]
        lx, ly = data["x"][first:last], data["y"][first:last]
        distance = np.r_[0., np.cumsum(np.hypot(np.diff(lx), np.diff(ly)))]
        keep = np.r_[True, np.diff(np.floor(distance / (max(dx, dy) * 4))) > 0]
        col = np.rint((lx[keep] - xg[0]) / (xg[1] - xg[0])).astype(int)
        row = np.rint((ly[keep] - yg[0]) / (yg[1] - yg[0])).astype(int)
        valid = (row >= 0) & (row < len(yg)) & (col >= 0) & (col < len(xg))
        np.add.at(sums, (row[valid], col[valid]), constants[name])
        np.add.at(counts, (row[valid], col[valid]), 1)
    known = counts > 0
    sparse = np.divide(sums, counts, out=np.zeros_like(sums), where=known)
    indices = distance_transform_edt(~known, return_distances=False, return_indices=True)
    surface = gaussian_filter(sparse[tuple(indices)], sigma=2., mode="nearest")
    corrected = original + surface
    corrected[~np.isfinite(original)] = np.nan
    reference_rmi, transform, projection = raster(refs / "magnetic/Hydraulic_RMI.tif")
    reconstructed_transform = (float(xg.min() - dx / 2), dx, 0., float(yg.max() + dy / 2), 0., -dy)
    assert corrected.shape == reference_rmi.shape and np.allclose(reconstructed_transform, transform, rtol=0, atol=1e-7)
    crs = osr.SpatialReference(wkt=projection)
    assert crs.GetAuthorityCode(None) == "26910"
    aligned = corrected[::-1]
    report["stages"]["correction_surface_adapter"] = difference(aligned, reference_rmi)
    write_raster(out / "reconstructed_RMI.tif", aligned, transform, projection)

    # Native default wrapper gets a separate verdict on the unmodified real grid.
    input_layer = QgsRasterLayer(str(refs / "magnetic/Hydraulic_RMI.tif"), "RMI")
    try:
        processing.run("terraworkbench:reduction_to_pole_igrf", {"INPUT": input_layer, "BAND": 1,
            "FIELD_MODE": 0, "INCLINATION": baseline_meta["field_inclination_deg"],
            "DECLINATION": baseline_meta["field_declination_deg"], "OUTPUT": str(out / "native_default_RTP.tif")},
            context=context, feedback=feedback)
        report["stages"]["native_default_rtp"] = {"status": "ran"}
    except Exception as error:
        report["stages"]["native_default_rtp"] = {"status": "blocked", "error": str(error)}

    print("Comparing FFT kernels under the historical fill/pad/frame conventions", flush=True)
    # Historical pipeline rounds the corrected input to Float32 before derivatives.
    ascending = corrected.astype(np.float32).astype(float)
    missing = ~np.isfinite(ascending)
    indices = distance_transform_edt(missing, return_distances=False, return_indices=True)
    filled = ascending[tuple(indices)]
    pn, pe = max(16, min(256, len(yg) // 8)), max(16, min(256, len(xg) // 8))
    prepared = np.pad(filled, ((pn, pn), (pe, pe)), mode="reflect")
    ke, kn, radial = frequency_grid(prepared.shape, dy, dx)
    response = magnetic_field_transform(ke, kn, radial, baseline_meta["field_inclination_deg"],
        baseline_meta["field_declination_deg"], 90, 0, max_gain=100)
    rtp = apply_transfer(prepared, response)
    def crop(array):
        result = np.asarray(array[pn:-pn, pe:-pe]).copy()
        result[missing] = np.nan
        return result
    def native_transfer(name, **params):
        algorithm = QgsApplication.processingRegistry().algorithmById("terraworkbench:" + name)
        return algorithm.transfer(ke, kn, radial, params, context)
    dx_grid = crop(apply_transfer(rtp, native_transfer("fft_derivative_easting", ORDER=1)))
    dy_grid = crop(apply_transfer(rtp, native_transfer("fft_derivative_northing", ORDER=1)))
    dz_grid = crop(apply_transfer(rtp, native_transfer("fft_derivative_upward", ORDER=1)))
    thdr = np.hypot(dx_grid, dy_grid)
    analytic = np.sqrt(dx_grid**2 + dy_grid**2 + dz_grid**2)
    # Continuation uses the exact registered Harmonica backend calculate method.
    import xarray as xr
    padded_grid = xr.DataArray(rtp, coords={"northing": yg[0] + np.arange(-pn, len(yg) + pn) * dy,
                                          "easting": xg[0] + np.arange(-pe, len(xg) + pe) * dx}, dims=("northing", "easting"))
    up = QgsApplication.processingRegistry().algorithmById("terraworkbench:upward_continuation")
    uc = crop(up.calculate(hm, padded_grid, {"HEIGHT": 500.}, context).values)
    products = {"RMI": ascending, "RTP": crop(rtp), "DX": dx_grid, "DY": dy_grid, "DZ_1VD": dz_grid,
                "DZ2_2VD": crop(apply_transfer(rtp, native_transfer("fft_derivative_upward", ORDER=2))),
                "THDR": thdr, "AS": analytic, "Tilt": np.arctan2(dz_grid, thdr),
                "45HG": (dx_grid + dy_grid) / np.sqrt(2), "TDX": np.arctan2(thdr, np.abs(dz_grid)),
                "Theta": np.arccos(np.clip(thdr / np.where(analytic == 0, np.nan, analytic), -1, 1)),
                "UC500": uc, "RS": crop(rtp) - uc}
    # Same prepared input, but actual MAG composite defaults (not the audit
    # formulas). This isolates derivative-method and angle-unit differences.
    native_composites = {}
    for name, algorithm_id in (("THDR", "mag_thdr"), ("Tilt", "mag_tilt"),
                               ("TDX", "mag_tdx"), ("Theta", "mag_theta")):
        algorithm = QgsApplication.processingRegistry().algorithmById("terraworkbench:" + algorithm_id)
        calculated = crop(algorithm.calculate(hm, padded_grid, {}, context).values)
        native_units = "field units/metre"
        if name in ("Tilt", "TDX", "Theta"):
            calculated = np.deg2rad(calculated)
            native_units = "degrees (converted to radians for comparison)"
        reference, _, _ = raster(next(refs.rglob(f"Hydraulic_{name}.tif")))
        item = difference(calculated[::-1], reference)
        item["algorithm"] = algorithm_id
        item["native_units"] = native_units
        item["horizontal_method"] = "Harmonica default finite difference, unlike historical FFT derivatives"
        native_composites[name] = item
        write_raster(out / f"native_composite_{name}.tif", calculated[::-1], transform, projection)
    report["stages"]["native_composites_on_common_padded_rtp"] = native_composites
    comparisons = {}
    for name, values in products.items():
        ref = next(refs.rglob(f"Hydraulic_{name}.tif"))
        reference, ref_transform, ref_projection = raster(ref)
        assert ref_transform == transform and osr.SpatialReference(wkt=ref_projection).IsSame(crs)
        north_up = values[::-1]
        comparison = difference(north_up, reference)
        comparison.update(native_stats=stats(north_up), reference_stats=stats(reference),
                          shape=list(values.shape), pixel_size=[dx, dy], crs="EPSG:26910")
        # Accept numerical agreement at 5 Float32 eps * field scale, plus 1e-8.
        tolerance = float(max(1e-8, 5 * np.finfo(np.float32).eps * float(np.nanmax(np.abs(reference)))))
        comparison["absolute_tolerance"] = tolerance
        comparison["within_tolerance"] = comparison["mask_disagreement"] == 0 and comparison["max_abs"] <= tolerance
        comparisons[name] = comparison
        write_raster(out / f"aligned_{name}.tif", north_up, transform, projection)
        print(f"{name}: RMSE={comparison['rmse']:.9g}, max={comparison['max_abs']:.9g}, mask={comparison['mask_disagreement']}", flush=True)
    report["stages"]["aligned_fft_pipeline"] = {"settings": {"padding_rows": pn, "padding_columns": pe,
        "fill": "nearest for FFT workspace only; restored mask", "detrend": "none", "taper": "none",
        "declination": "historical numerical angle; no additional grid-convergence correction",
        "chain": "retain padded RTP through all derivatives; crop only at end",
        "formulas": "THDR/AS/Tilt/45HG/TDX/Theta combined explicitly in this audit adapter"}, "products": comparisons}
    report["limitations"] = [
        "GDB reader not rerun: uses existing complete finite-observation NPZ extraction.",
        "Correction surface, nearest fill, explicit cell padding, compound formulas and mask restoration are audit adapters, not one native end-to-end database recipe.",
        "New interpolation from raw observations, 8-million-record scale, archaeology and inversions are not validated by this pilot.",
        "Historical declination is used as an array-axis angle for reproducibility; this audit does not certify its true/grid-north convention."]
    report["source_hashes_unchanged"] = all(checksum(Path(p)) == entry["sha256"] for p, entry in before.items())
    report["elapsed_seconds"] = time.perf_counter() - start
    report["all_aligned_grids_within_tolerance"] = all(p["within_tolerance"] for p in comparisons.values())
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("Report: " + str(out / "report.json"), flush=True)
    print("Reference hashes unchanged: " + str(report["source_hashes_unchanged"]), flush=True)


if __name__ == "__main__":
    main()
