"""Database-to-grid backend runner. No Qt or GUI dependencies; GDAL is lazy."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np

if __package__:
    from .magnetic_pipeline import line_correction_surface, magnetic_grid_products
else:
    from magnetic_pipeline import line_correction_surface, magnetic_grid_products


def run_magnetic_grid_pipeline(store, database_id, template_path, x, y, line, correction,
                              options, sample_step_cells=4., sigma_cells=2., input_precision="float64", canceled=None):
    from osgeo import gdal, osr
    import scipy
    options.validate()
    if input_precision not in ("float32", "float64"):
        raise ValueError("Input precision must be explicitly float32 or float64.")
    def check():
        if canceled and canceled():
            raise InterruptedError("Magnetic grid pipeline canceled.")
    check()
    snapshot = store._snapshot(database_id, [x, y, line, correction])
    database = next(d for d in store.databases() if d["id"] == database_id)
    geometry = json.loads(database["metadata"]).get("geometry", {})
    if geometry.get("x_channel_id") != snapshot[0]["id"] or geometry.get("y_channel_id") != snapshot[1]["id"]:
        raise ValueError("Selected XY must be the explicitly configured database coordinate pair.")
    path = Path(template_path).resolve()
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            check()
            digest.update(chunk)
    source = gdal.Open(str(path), gdal.GA_ReadOnly)
    if source is None or source.RasterCount != 1:
        raise ValueError("A single-band georeferenced template is required.")
    transform, projection = source.GetGeoTransform(), source.GetProjection()
    crs = osr.SpatialReference(wkt=projection)
    db_crs = osr.SpatialReference()
    db_crs.SetFromUserInput(geometry.get("crs", ""))
    if not crs.IsProjected() or not crs.IsSame(db_crs) or not np.isclose(crs.GetLinearUnits(), 1.):
        raise ValueError("Template and database must share the same projected metre CRS; reproject explicitly first.")
    if transform[2] != 0 or transform[4] != 0 or transform[1] <= 0 or transform[5] >= 0:
        raise ValueError("Template must be north-up with positive easting pixel spacing.")
    band = source.GetRasterBand(1)
    north_up = band.ReadAsArray().astype(float)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        north_up[north_up == nodata] = np.nan
    band = None
    source = None
    ascending = north_up[::-1]
    height, width = ascending.shape
    xg = transform[0] + (np.arange(width) + .5) * transform[1]
    yg = (transform[3] + (np.arange(height) + .5) * transform[5])[::-1]
    with closing(store._batches(snapshot, canceled=canceled)) as batches:
        surface, surface_recipe = line_correction_surface(batches, x, y, line, correction, xg, yg,
            np.isfinite(ascending), sample_step_cells, sigma_cells, canceled)
    check()
    corrected = (ascending + surface).astype(input_precision).astype(float)
    products, recipe = magnetic_grid_products(corrected, (abs(transform[5]), transform[1]), options, canceled)
    products["line_correction_surface"] = surface
    recipe.update(database_id=database_id, inputs={c["name"]: c["version_id"] for c in snapshot},
        template={"path": str(path), "sha256": digest.hexdigest(), "size": before.st_size},
        correction_surface=surface_recipe, input_precision=input_precision, crs=projection,
        geotransform=list(transform), scipy=scipy.__version__, gdal=gdal.VersionInfo(),
        missing_policy="original template footprint retained", source_unit=snapshot[3]["unit"])
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Template changed while processing.")
    job_id = uuid.uuid4().hex
    staging, destination = store._path("grids/" + job_id + ".partial"), store._path("grids/" + job_id)
    staging.mkdir()
    filenames = []
    published = False
    try:
        for name, values in products.items():
            check()
            filename = name + ".tif"
            filenames.append(filename)
            target = gdal.GetDriverByName("GTiff").Create(str(staging / filename), width, height, 1,
                gdal.GDT_Float64, options=["TILED=YES", "COMPRESS=DEFLATE"])
            if target is None:
                raise OSError("Could not create output raster.")
            try:
                target.SetGeoTransform(transform)
                target.SetProjection(projection)
                target.SetMetadata({"TW_PROCESS": "magnetic_grid_pipeline", "TW_RECIPE": "recipe.json",
                    "TW_DATABASE": database_id, "TW_DERIVATIVES": options.derivative_method,
                    "TW_ANGLE_UNITS": options.angle_units, "TW_NODATA": "Original template support retained"})
                unit = snapshot[3]["unit"] or "unknown"
                if name in ("Tilt", "TDX", "Theta"):
                    unit = options.angle_units
                elif name == "DZ2_2VD":
                    unit += "/m^2"
                elif name in ("DX", "DY", "DZ_1VD", "THDR", "AS", "45HG"):
                    unit += "/m"
                target.GetRasterBand(1).SetUnitType(unit)
                target.GetRasterBand(1).SetNoDataValue(float("nan"))
                target.GetRasterBand(1).WriteArray(values[::-1])
                target.FlushCache()
            finally:
                target = None
        recipe["products"] = {name: name + ".tif" for name in products}
        filenames.append("recipe.json")
        (staging / "recipe.json").write_text(json.dumps(recipe, indent=2, allow_nan=False), encoding="utf-8")
        check()
        staging.rename(destination)
        published = True
        with store._connection() as db:
            store._event(db, database_id, "magnetic_grid_pipeline", {
                "recipe": (destination / "recipe.json").relative_to(store.root).as_posix(),
                "inputs": recipe["inputs"], "products": list(products)})
        return {"directory": str(destination), "recipe": str(destination / "recipe.json"),
                "products": {name: str(destination / (name + ".tif")) for name in products}}
    except BaseException:
        folder = destination if published else staging
        for filename in filenames:
            (folder / filename).unlink(missing_ok=True)
        folder.rmdir()
        raise
