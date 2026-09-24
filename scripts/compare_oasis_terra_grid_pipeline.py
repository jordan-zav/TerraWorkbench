"""Run the same two-pass nine-point grid filter in Oasis and TerraWorkbench."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
from osgeo import gdal, osr
from qgis.core import QgsApplication, QgsRasterLayer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if os.environ.get("QGIS_PREFIX_PATH"):
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))

if __package__:
    from ..dependencies import import_harmonica
else:
    from TerraWorkbench.dependencies import import_harmonica


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_input_geotiff(data_array, destination):
    values = np.asarray(data_array.values, dtype=float)
    easting, northing = np.asarray(data_array.easting), np.asarray(data_array.northing)
    dx, dy = float(np.median(np.diff(easting))), float(np.median(np.diff(northing)))
    if not np.allclose(np.diff(easting), dx) or not np.allclose(np.diff(northing), dy):
        raise ValueError("The reference grid is not regular.")
    source = gdal.GetDriverByName("GTiff").Create(str(destination), len(easting), len(northing), 1, gdal.GDT_Float64)
    # Oasis exports a grid with the first grid coordinate as the upper-left
    # raster origin, so use that same convention for the TerraWorkbench input.
    source.SetGeoTransform((float(easting[0]), dx, 0., float(northing[-1]), 0., -dy))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(26710)
    source.SetProjection(crs.ExportToWkt())
    band = source.GetRasterBand(1)
    band.SetNoDataValue(float("nan"))
    band.WriteArray(values[::-1])
    source.FlushCache()
    source = None


def load_array(path):
    dataset = gdal.Open(str(path), gdal.GA_ReadOnly)
    if dataset is None:
        raise ValueError(f"Could not open raster: {path}")
    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray().astype(float)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        values[np.isclose(values, nodata) if np.isfinite(nodata) else np.isnan(values)] = np.nan
    return values, dataset.GetGeoTransform(), dataset.GetProjection()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-grd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oms", type=Path, default=Path(r"C:/Program Files/Geosoft/Desktop Applications/bin/oms.exe"))
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new output directory; existing results are never overwritten.")
    if not args.input_grd.is_file() or not args.oms.is_file():
        raise FileNotFoundError("Input GRD and oms.exe are required.")
    started = time.perf_counter()
    args.output.mkdir(parents=True)
    workspace = args.output / "oasis_workspace"
    workspace.mkdir()
    for suffix in (".GRD", ".GRD.gi", ".GRD.xml"):
        source = args.input_grd.with_suffix(suffix) if suffix == ".GRD" else Path(str(args.input_grd) + suffix.removeprefix(".GRD"))
        if source.is_file():
            shutil.copy2(source, workspace / source.name)
    local_input = workspace / args.input_grd.name
    oasis_tif = workspace / "oasis_smooth9.tif"
    script = workspace / "same_pipeline.om"
    script.write_text(
        '\n'.join([
            f'SETINI         GRIDFLTN.GRD=".\\{local_input.name}(GRD)"',
            'SETINI         GRIDFLTN.NEW9=".\\oasis_smooth9.grd(GRD)"',
            'SETINI         GRIDFLTN.DEFFILT9="1"',
            'SETINI         GRIDFLTN.FILT9=""',
            'SETINI         GRIDFLTN.FILTSTR9=""',
            'SETINI         GRIDFLTN.PASS9="2"',
            'SETINI         GRIDFLTN.CELLSIZE="1"',
            'GX             gridflt9.gx',
            'SETINI         GRIDCOPY.OVERWRITE="1"',
            'SETINI         GRIDCOPY.IN=".\\oasis_smooth9.grd(GRD)"',
            'SETINI         GRIDCOPY.OUT_FORMAT="TIF;TYPE=DATA"',
            'SETINI         GRIDCOPY.OUT_FOLDER=""',
            'SETINI         GRIDCOPY.OUT_PREFIX=""',
            'SETINI         GRIDCOPY.OUT=".\\oasis_smooth9.tif(TIF;TYPE=DATA)"',
            'SETINI         GRIDCOPY.DISPLAY_OPTION="Do not display"',
            'SETINI         GRIDCOPY.ADDTOPROJECT="0"',
            'GX             geogxnet.dll(Geosoft.GX.GridUtils.CopyConvertMultiGrids;Run)',
            '',
        ]), encoding="utf-8")
    log = args.output / "oasis.log"
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run([str(args.oms), str(script)], cwd=workspace,
                                    stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=600, check=False)
    if completed.returncode != 0 or not oasis_tif.is_file():
        raise RuntimeError(f"Oasis failed with exit code {completed.returncode}; see {log}")
    reference = import_harmonica().load_oasis_montaj_grid(args.input_grd)
    terra_input = args.output / "input_mtf.tif"
    write_input_geotiff(reference, terra_input)
    import processing
    terra_output = args.output / "terra_smooth9.tif"
    processing.run("terraworkbench:smooth_nine_point", {
        "INPUT": QgsRasterLayer(str(terra_input), "MTF"), "BAND": 1,
        "PASSES": 2, "OUTPUT": str(terra_output),
    })
    oasis_values, oasis_gt, oasis_projection = load_array(oasis_tif)
    terra_values, terra_gt, terra_projection = load_array(terra_output)
    if oasis_values.shape != terra_values.shape or oasis_gt != terra_gt:
        raise ValueError("Oasis and TerraWorkbench outputs have different raster geometry.")
    valid = np.isfinite(oasis_values) & np.isfinite(terra_values)
    difference = terra_values[valid] - oasis_values[valid]
    report = {
        "input_grd": str(args.input_grd.resolve()), "input_sha256": digest(args.input_grd),
        "oasis_version": "oms.exe " + str(args.oms.stat().st_size),
        "pipeline": {"filter": "nine-point binomial", "passes": 2, "input": "Milligan South_MTF.GRD",
                     "oasis_macro": str(script), "oasis_log": str(log)},
        "oasis_output": {"path": str(oasis_tif), "sha256": digest(oasis_tif)},
        "terra_output": {"path": str(terra_output), "sha256": digest(terra_output)},
        "shape": list(terra_values.shape), "finite_comparison_cells": int(valid.sum()),
        "geometry": {"geotransform_equal": oasis_gt == terra_gt,
                     "projection_equal": bool(osr.SpatialReference(wkt=oasis_projection).IsSame(osr.SpatialReference(wkt=terra_projection)))},
        "comparison": {"bias_terra_minus_oasis": float(np.mean(difference)),
                       "mae": float(np.mean(np.abs(difference))),
                       "rmse": float(np.sqrt(np.mean(difference ** 2))),
                       "max_abs": float(np.max(np.abs(difference))),
                       "correlation": float(np.corrcoef(terra_values[valid], oasis_values[valid])[0, 1])},
        "elapsed_seconds": time.perf_counter() - started,
    }
    report["passed"] = bool(report["geometry"]["geotransform_equal"] and report["geometry"]["projection_equal"] and valid.any())
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise AssertionError("Same-pipeline comparison failed; inspect report.json")


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    from processing.core.Processing import Processing
    Processing.initialize()
    from TerraWorkbench.provider import TerraWorkbenchProvider
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    main()
