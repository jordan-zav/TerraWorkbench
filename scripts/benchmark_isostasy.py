"""Private-data Airy sensitivity benchmark; never fit to the published residual.

Requires rasterio and a SRTM30_PLUS w140n90 big-endian int16 tile (6000x4800).
Outputs stay in an explicitly supplied directory. This is a finite Cartesian
experiment, not a claim of reproduction of a proprietary spherical model.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isostasy import airy_prisms, airy_root_effect  # noqa: E402


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--topography-tile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-grid", action="store_true",
                        help="Evaluate every valid station for the fixed 300km/10km/3070 terrain case.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = [args.grids / name for name in
             ("10N-BOU_G.tif", "10N-BOU-IS_G.tif", "10N-TER-BE_G.tif")]
    grids = []
    with rasterio.open(paths[0]) as d:
        transform, crs, bounds = d.transform, d.crs, d.bounds
        shape = d.shape
    for path in paths:
        with rasterio.open(path) as d:
            if d.transform != transform or d.crs != crs or d.shape != shape:
                raise ValueError("Benchmark grids are not aligned.")
            grids.append(d.read(1, masked=True).filled(np.nan).astype(float))
    bouguer, published, terrain = grids
    rr, cc = np.indices(shape)
    valid = np.isfinite(bouguer + published + terrain)
    selected = valid if args.full_grid else valid & (rr % 16 == 0) & (cc % 16 == 0)
    x, y = rasterio.transform.xy(transform, rr[selected], cc[selected])
    x, y, z = np.asarray(x), np.asarray(y), terrain[selected]
    target = (published - bouguer)[selected]
    raw = np.fromfile(args.topography_tile, dtype=">i2").reshape(6000, 4800).astype(float)
    raw[raw <= -32768] = np.nan
    water = np.maximum(-raw, 0)
    src_transform = from_origin(-140, 90, 1/120, 1/120)
    results, comparisons = [], {"x": x, "y": y, "height_terrain": z, "published_correction": target}
    # Fixed, declared sensitivity cases, not a search for best-fitting parameters.
    cases = [(0, 10000, 3070, "terrain"), (167000, 10000, 3070, "terrain"),
             (300000, 10000, 3070, "terrain"), (600000, 10000, 3070, "terrain"),
             (300000, 5000, 3070, "terrain"), (300000, 5000, 3270, "terrain"),
             (300000, 5000, 3070, "sea_level")]
    if args.full_grid:
        cases = [(300000, 10000, 3070, "terrain")]
    for margin, resolution, mantle, height_mode in cases:
        start = time.perf_counter()
        left = np.floor((bounds.left-margin)/resolution)*resolution
        top = np.ceil((bounds.top+margin)/resolution)*resolution
        nx = int(np.ceil((bounds.right+margin-left)/resolution))
        ny = int(np.ceil((top-bounds.bottom+margin)/resolution))
        dst_transform = from_origin(left, top, resolution, resolution)
        model = []
        for source in (raw, water):
            dest = np.full((ny, nx), np.nan)
            reproject(source, dest, src_transform=src_transform, src_crs="EPSG:4326",
                      src_nodata=np.nan, dst_transform=dst_transform, dst_crs=crs,
                      dst_nodata=np.nan, resampling=Resampling.average)
            if not np.isfinite(dest).all():
                raise ValueError("Regional source does not cover the requested model.")
            model.append(dest[::-1])
        east = left + (np.arange(nx)+.5)*resolution
        north = top - (np.arange(ny)[::-1]+.5)*resolution
        prisms, density = airy_prisms(east, north, model[0], water_thickness=model[1],
                                     density_mantle=mantle)
        effect = airy_root_effect((x, y, z if height_mode == "terrain" else np.zeros_like(z)),
                                  prisms, density, max_interactions=2_000_000_000,
                                  progress=(lambda p: print(f"Progress: {p:.1%}", flush=True)) if args.full_grid else None)
        correction = -effect
        error = correction - target
        key = f"margin{margin}_cell{resolution}_mantle{mantle}_{height_mode}"
        comparisons[key] = correction
        record = dict(case=key, prisms=len(prisms), stations=len(x),
                      margin_m=margin, cell_m=resolution, density_mantle=mantle,
                      height=height_mode, correction_range=[float(correction.min()),float(correction.max())],
                      bias_mgal=float(error.mean()), rms_mgal=float(np.sqrt(np.mean(error**2))),
                      demeaned_rms_mgal=float(error.std()),
                      correlation=float(np.corrcoef(correction, target)[0,1]),
                      seconds=time.perf_counter()-start)
        results.append(record)
        print(json.dumps(record), flush=True)
        if args.full_grid:
            for name, values in [("root_correction", correction),
                                 ("isostatic_experimental", bouguer[selected]+correction),
                                 ("difference_from_published", error)]:
                raster = np.full(shape, -99999., dtype="float32")
                raster[selected] = values
                with rasterio.open(args.output / (name + ".tif"), "w", driver="GTiff",
                                   height=shape[0], width=shape[1], count=1,
                                   dtype="float32", crs=crs, transform=transform,
                                   nodata=-99999., compress="deflate") as dst:
                    dst.write(raster, 1)
                    dst.update_tags(status="EXPERIMENTAL_NOT_SURVEY_REPRODUCTION",
                                    model="finite Cartesian Airy; SRTM30_PLUS V11",
                                    reference_depth_m=30000, crust_kg_m3=2670,
                                    mantle_kg_m3=mantle, water_kg_m3=1040,
                                    margin_m=margin, model_cell_m=resolution,
                                    observation_height="published bare earth (assumption)",
                                    units="mGal", fitted_offset="none")
    manifest = dict(status="experimental_not_proprietary_reproduction", results=results,
                    inputs=[dict(path=str(p.resolve()), sha256=digest(p)) for p in paths+[args.topography_tile]],
                    reference_depth_m=30000, density_crust=2670, density_water=1040,
                    source="SRTM30_PLUS V11 (2014); original survey version unspecified",
                    source_url="https://topex.ucsd.edu/pub/srtm30_plus/srtm30/data/w140n90.Bathymetry.srtm",
                    limitations=["Finite Cartesian geometry; no spherical or global far-zone contribution",
                                 "Mantle and water densities are sensitivity assumptions, not documented survey values",
                                 "Terrain or sea-level stations; actual airborne observation surface not reproduced",
                                 "Regional lake bathymetry not supplied; sea water inferred only below zero",
                                 "Grid difference includes published filtering and gridding",
                                 "No offset fitting, calibration or hidden gap filling"],
                    valid_grid_cells=int(valid.sum()), sampled_stations=len(x),
                    published_correction_range=[float(target.min()),float(target.max())])
    (args.output / "benchmark.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    np.savez_compressed(args.output / "comparison.npz", **comparisons)


if __name__ == "__main__":
    main()
