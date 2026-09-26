"""Reproduce a declared periodic Airy hypothesis on private reference grids.

This does not identify a proprietary recipe. The reference anomaly is used only
for diagnostics, never to estimate an offset or modify the model input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from scipy.interpolate import RegularGridInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isostasy import airy_root_effect_fft  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--topography-tile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = [args.grids/name for name in ("10N-BOU_G.tif", "10N-BOU-IS_G.tif")]
    with rasterio.open(paths[0]) as ds:
        bouguer = ds.read(1, masked=True).filled(np.nan).astype(float)
        transform, crs, bounds, profile = ds.transform, ds.crs, ds.bounds, ds.profile
    with rasterio.open(paths[1]) as ds:
        if ds.transform != transform or ds.crs != crs or ds.shape != bouguer.shape:
            raise ValueError("Reference grids must align.")
        published = ds.read(1, masked=True).filled(np.nan).astype(float)
    valid = np.isfinite(bouguer) & np.isfinite(published)
    rr, cc = np.indices(bouguer.shape)
    xs, ys = rasterio.transform.xy(transform, rr[valid], cc[valid])
    xy = np.column_stack((ys, xs))
    target = published[valid]-bouguer[valid]
    raw = np.fromfile(args.topography_tile, dtype=">i2").reshape(6000, 4800).astype(float)
    if np.any(raw <= -32768):
        raise ValueError("Source tile contains missing load.")
    raw_water = np.maximum(-raw, 0)
    cases = [(167000, 5000, 3270, 0), (167000, 2500, 3270, 0),
             (167000, 5000, 3070, 0), (167000, 5000, 3270, 1500),
             (0, 5000, 3270, 0), (300000, 5000, 3270, 0), (600000, 5000, 3270, 0)]
    records, predictions, written = [], {}, []
    for margin, dx, mantle, height in cases:
        start = time.perf_counter()
        left = np.floor((bounds.left-margin)/dx)*dx
        top = np.ceil((bounds.top+margin)/dx)*dx
        nx = int(np.ceil((bounds.right+margin-left)/dx))
        ny = int(np.ceil((top-bounds.bottom+margin)/dx))
        model_transform = from_origin(left, top, dx, dx)
        projected = []
        for source in (raw, raw_water):
            dest = np.full((ny, nx), np.nan)
            reproject(source, dest, src_transform=from_origin(-140,90,1/120,1/120),
                      src_crs="EPSG:4326", src_nodata=np.nan, dst_transform=model_transform,
                      dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average)
            projected.append(dest[::-1])
        effect, recipe = airy_root_effect_fft(projected[0], (dx, dx), boundary="periodic",
                                              density_mantle=mantle, water_thickness=projected[1],
                                              observation_height=height, tolerance_mgal=1e-7)
        x = left+(np.arange(nx)+.5)*dx
        y = top-(np.arange(ny)[::-1]+.5)*dx
        prediction = -RegularGridInterpolator((y,x), effect, bounds_error=True)(xy)
        error = prediction-target
        key = f"margin{margin}_cell{dx}_mantle{mantle}_height{height}"
        predictions[key] = prediction
        record = dict(case=key, margin_m=margin, cell_m=dx, stations=int(valid.sum()),
                      rms_mgal=float(np.sqrt(np.mean(error**2))), bias_mgal=float(error.mean()),
                      error_std_mgal=float(error.std()), max_abs_error_mgal=float(np.max(np.abs(error))),
                      correlation=float(np.corrcoef(prediction,target)[0,1]),
                      seconds=time.perf_counter()-start, recipe=recipe)
        records.append(record)
        print(json.dumps(record), flush=True)
        # Fixed fine-grid diagnostic case, not a fitted minimum over the cases.
        if (margin, dx, mantle, height) == (167000, 2500, 3270, 0):
            recipe.update(model_shape=[ny,nx], geotransform=list(model_transform.to_gdal()),
                          regional_margin_m=margin, source="SRTM30_PLUS V11 (2014)",
                          mantle_status="hypothesis; not documented survey density",
                          station_height_status="sea-level hypothesis; not verified survey surface",
                          proprietary_equivalence="not established")
            def write(name, values, raster_transform):
                path = args.output/(name+".tif")
                options = profile.copy()
                options.update(driver="GTiff", count=1, dtype="float64", nodata=-99999.,
                               width=values.shape[1], height=values.shape[0],
                               transform=raster_transform, compress="deflate")
                with rasterio.open(path,"w",**options) as ds:
                    ds.write(np.where(np.isfinite(values),values,-99999.),1)
                    ds.update_tags(TW_ISOSTASY=json.dumps(recipe), status="PERIODIC_AIRY_HYPOTHESIS",
                                   units="m" if name in ("regional_basement", "regional_water_thickness") else "mGal")
                written.append(path)
            for name, values in [("root_correction_fft", prediction),
                                 ("isostatic_fft", bouguer[valid]+prediction),
                                 ("difference_from_published_fft",error)]:
                raster = np.full(bouguer.shape,np.nan)
                raster[valid] = values
                write(name,raster,transform)
            write("regional_basement",projected[0][::-1],model_transform)
            write("regional_water_thickness",projected[1][::-1],model_transform)
            write("regional_root_effect_fft",effect[::-1],model_transform)
    coarse = predictions[cases_key(167000,5000,3270,0)]
    fine = predictions[cases_key(167000,2500,3270,0)]
    manifest = dict(status="periodic_model_hypothesis_not_certified_proprietary_reproduction", cases=records,
                    input_files=[dict(path=str(p.resolve()),sha256=sha256(p)) for p in paths+[args.topography_tile]],
                    output_files=[dict(path=p.name,sha256=sha256(p)) for p in written],
                    resolution_rms_mgal=float(np.sqrt(np.mean((coarse-fine)**2))),
                    resolution_max_abs_mgal=float(np.max(np.abs(coarse-fine))),
                    caveats=["Parameters tested after examining the reference; this is not blind validation",
                             "Density 3270 and sea-level plane are hypotheses, not recovered SGL metadata",
                             "Periodic repetition is explicit, not a global spherical solution",
                             "No fitted offset; DC term comes from the independent load model",
                             "Source V11 is newer than the survey and omits its local lake bathymetry",
                             "167 km is documented for terrain coverage, not confirmed for SGL isostasy"])
    (args.output/"benchmark_fft.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    np.savez_compressed(args.output/"comparison_fft.npz", published_correction=target, **predictions)


def cases_key(margin, dx, mantle, height):
    return f"margin{margin}_cell{dx}_mantle{mantle}_height{height}"


if __name__ == "__main__":
    main()
