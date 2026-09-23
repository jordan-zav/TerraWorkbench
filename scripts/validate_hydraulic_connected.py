"""Validate the production SurveyStore/grid connection against Hydraulic.

Run with QGIS Python. Consumes a prior native crossover audit, reads references
only, and writes exclusively to a new output directory. No images or GUI.
"""
import argparse
import json
from pathlib import Path
import time

from validate_hydraulic_backend import checksum, raster, difference, stats, read_json, write_raster
from qgis.core import QgsApplication, QgsVectorLayer, QgsRasterLayer
from osgeo import osr
import numpy as np
from TerraWorkbench.dependencies import import_harmonica
from TerraWorkbench.provider import TerraWorkbenchProvider
from TerraWorkbench.survey_store import SurveyStore
from TerraWorkbench.magnetic_pipeline import MagneticPipelineOptions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--crossovers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError("Choose a new output directory; audits are never overwritten.")
    out.mkdir(parents=True)
    started = time.perf_counter()
    app = QgsApplication([], False)
    app.initQgis()
    import processing
    from processing.core.Processing import Processing
    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    hm = import_harmonica()
    import pyarrow as pa
    import pyarrow.parquet as pq
    refs = args.root / "Shared/Data/Regional Geology, Structural Geology, and Geophysics/Petrofisica_e_Inversion/02_Magnetometria/02_Surveys_Corregidos_GDB/Hydraulic"
    archive_path = args.root / "Personal/Mag/Raw/line_leveling/results/extracts/Hydraulic.npz"
    metadata_path = refs / "metadata/processing_report.json"
    meta = read_json(metadata_path)
    original_path = Path(meta["source_original_grid"])
    consumed = [archive_path, metadata_path, original_path, args.crossovers] + sorted(refs.rglob("*.tif"))
    hashes = {str(p): checksum(p) for p in consumed}
    with np.load(archive_path, allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    lines = np.repeat(data["line_names"].astype(str), np.diff(data["offsets"]))
    pq.write_table(pa.table({"Easting": data["x"], "Northing": data["y"], "Line": lines,
                            "MAGRES": data["magnetic"]}), out / "observations.parquet")
    store = SurveyStore(out / "workspace", create=True)
    database = store.import_file(out / "observations.parquet", name="Hydraulic")
    store.configure_geometry(database, "Easting", "Northing", "EPSG:26910")
    store.rename_channel(database, "MAGRES", "MAGRES", unit="nT")
    cross = QgsVectorLayer(str(args.crossovers), "native_crossovers", "ogr")
    assert cross.isValid()
    rows = [(str(f["traverse"]), str(f["tie"]), float(f["res_before"])) for f in cross.getFeatures()]
    print("Publishing correction and leveled channels from native crossovers", flush=True)
    leveling = store.level_lines(database, "MAGRES", "Line", rows, "MAGRES__line_correction", "MAGRES__leveled")
    original = hm.load_oasis_montaj_grid(original_path)
    # The published reference supplies the already-audited EPSG:26910 grid
    # georeferencing. Check the GRD coordinates before attaching that CRS.
    _, transform, projection = raster(refs / "magnetic/Hydraulic_RMI.tif")
    xx, yy = np.asarray(original.easting), np.asarray(original.northing)
    assert np.allclose(xx, transform[0] + (np.arange(len(xx)) + .5) * transform[1])
    assert np.allclose(yy, (transform[3] + (np.arange(len(yy)) + .5) * transform[5])[::-1])
    template = out / "original_template.tif"
    write_raster(template, np.asarray(original.values)[::-1], transform, projection)
    options = MagneticPipelineOptions(meta["field_inclination_deg"], meta["field_declination_deg"],
        declination_frame="grid", padding_rows=16, padding_columns=37)
    result = store.magnetic_grid_pipeline(database, template, "Easting", "Northing", "Line",
        "MAGRES__line_correction", options, input_precision="float32")
    comparisons = {}
    for name, path in result["products"].items():
        if name == "line_correction_surface":
            continue
        values, actual_transform, actual_projection = raster(path)
        reference, ref_transform, ref_projection = raster(next(refs.rglob(f"Hydraulic_{name}.tif")))
        item = difference(values, reference)
        item["statistics"] = stats(values)
        item["tolerance"] = float(max(1e-8, 5 * np.finfo(np.float32).eps * np.nanmax(np.abs(reference))))
        item["geometry_equal"] = actual_transform == ref_transform and bool(osr.SpatialReference(wkt=actual_projection).IsSame(osr.SpatialReference(wkt=ref_projection)))
        item["passed"] = item["geometry_equal"] and item["mask_disagreement"] == 0 and item["max_abs"] <= item["tolerance"]
        comparisons[name] = item
        print(f"{name}: RMSE={item['rmse']:.9g}; passed={item['passed']}", flush=True)
    # Exercise the public Processing wrapper directly on a real masked grid.
    wrapper = out / "native_wrapper_RTP.tif"
    processing.run("terraworkbench:reduction_to_pole_igrf", {
        "INPUT": QgsRasterLayer(str(refs / "magnetic/Hydraulic_RMI.tif"), "RMI"), "BAND": 1,
        "FIELD_MODE": 0, "INCLINATION": options.inclination, "DECLINATION": options.declination,
        "OUTPUT": str(wrapper)})
    mask_equal = np.array_equal(np.isfinite(raster(wrapper)[0]), np.isfinite(raster(template)[0]))
    recipe = read_json(Path(result["recipe"]))
    report = {"observations": len(lines), "lines": len(data["line_names"]), "crossovers": len(rows),
        "leveling": leveling, "products": comparisons, "recipe": result["recipe"],
        "recipe_inputs": recipe["inputs"], "wrapper_mask_preserved": mask_equal,
        "source_hashes": hashes, "source_hashes_unchanged": all(checksum(Path(p)) == h for p, h in hashes.items()),
        "limitations": ["Existing finite-observation NPZ extraction; GDB reader not tested.",
            "Crossovers reused from the native backend audit; channel solving and all grid products run through production APIs.",
            "Historical declination reproduced as a grid angle; true/grid convention is not independently certified.",
            "No raw-point regridding, inversion, archaeology or eight-million-observation benchmark."],
        "elapsed_seconds": time.perf_counter() - started}
    report["passed"] = all(item["passed"] for item in comparisons.values()) and mask_equal and report["source_hashes_unchanged"]
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("Report: " + str(out / "report.json"), flush=True)
    if not report["passed"]:
        raise AssertionError("Connected pipeline comparison failed; inspect report.json")


if __name__ == "__main__":
    main()
