"""Compare the experimental solver to an existing Oasis GeoTIFF in its CRS.

Run using QGIS Python. Reads sources only; requires a new output directory.
The reference is a historical RANGRID output, not a fresh Oasis execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import struct
import numpy as np
from osgeo import gdal, osr
from scipy.ndimage import binary_erosion

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridding_methods import MinimumCurvatureGridder, SincGridder

gdal.UseExceptions()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-grd', type=Path)
    parser.add_argument('--iterations', type=int, default=100)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [args.source,args.reference]+([args.native_grd] if args.native_grd else [])
    hashes = [digest(path) for path in sources]
    raw = np.loadtxt(args.source, delimiter='\t', skiprows=1, usecols=(5,6,13))
    ds = gdal.Open(str(args.reference))
    ref = ds.ReadAsArray().astype(float)
    nd = ds.GetRasterBand(1).GetNoDataValue()
    if nd is not None:
        ref[ref == nd] = np.nan
    gt, wkt = ds.GetGeoTransform(), ds.GetProjection()
    ds = None
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    target = osr.SpatialReference(wkt=wkt)
    for crs in (source, target):
        crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    coords = np.asarray(osr.CoordinateTransformation(source,target).TransformPoints(raw[:,[1,0]]))[:,:2]
    rows, cols = ref.shape
    geometry_note = 'Existing Oasis raster cell centres; native node coordinates unverified.'
    if args.native_grd:
        with args.native_grd.open('rb') as stream:
            header = stream.read(512)
        _, _, nc, nr, order = struct.unpack_from('<5i', header)
        dx, dy, x0, y0, rotation = struct.unpack_from('<5d', header, 20)
        if (nr,nc) != (rows,cols) or order != 1 or rotation != 0 or dx <= 0 or dy <= 0:
            raise ValueError('Unsupported native GRD geometry')
        expected_export = (x0, dx, 0., y0+(nr-1)*dy, 0., -dy)
        if not np.allclose(gt, expected_export, rtol=0, atol=1e-7):
            raise ValueError('Reference GeoTIFF does not match native GRD export geometry')
        gt = (x0-dx/2,dx,0.,y0+(nr-.5)*dy,0.,-dy)
        geometry_note = 'Native GRD sample coordinates verified against export. Output GeoTIFF corners adjusted by half cell to represent those same sample centres.' 
    x = gt[0]+(np.arange(cols)+.5)*gt[1]
    y = (gt[3]+(np.arange(rows)+.5)*gt[5])[::-1]
    model = MinimumCurvatureGridder(coords, raw[:,2], gt[1],
                                   blanking_distance=3, search_radius=8, max_iterations=args.iterations)
    start = time.perf_counter()
    grid = model.grid(x,y)[::-1]
    seconds = time.perf_counter()-start

    def write(name, values, transform):
        out = gdal.GetDriverByName('GTiff').Create(str(args.output/name), values.shape[1], values.shape[0], 1, gdal.GDT_Float64)
        out.SetGeoTransform(transform)
        out.SetProjection(wkt)
        out.GetRasterBand(1).SetNoDataValue(float('nan'))
        out.GetRasterBand(1).WriteArray(values)
        out = None

    write('minimum_curvature.tif', grid, gt)
    common = np.isfinite(grid)&np.isfinite(ref)
    delta = grid[common]-ref[common]
    xx,yy = np.meshgrid(x,y[::-1])
    finite = np.isfinite(grid)
    sinc = SincGridder(np.column_stack((xx[finite],yy[finite])),grid[finite],(gt[1],-gt[5]))
    sx = x[0]+np.arange((cols-1)*2+1)*gt[1]/2
    sy = y[-1]+np.arange((rows-1)*2+1)*gt[5]/2
    start = time.perf_counter()
    expanded = sinc.grid(sx,sy)
    sinc_seconds = time.perf_counter()-start
    write('sinc_expansion.tif',expanded,(sx[0]-gt[1]/4,gt[1]/2,0,sy[0]-gt[5]/4,0,gt[5]/2))
    np.testing.assert_allclose(expanded[::2,::2],grid,atol=1e-8,equal_nan=True)
    assert hashes == [digest(path) for path in sources]
    regions = {}
    for cells in (0,4,12):
        region = common if cells == 0 else binary_erosion(common,iterations=cells)
        errors = grid[region]-ref[region]
        regions[str(cells)] = dict(cells=int(region.sum()),rmse=float(np.sqrt(np.mean(errors**2))),mae=float(np.mean(abs(errors))))
    report = dict(source=str(args.source),reference=str(args.reference),sha256=hashes,
                  points=len(raw),channel='anomaly_mm_bw',shape=list(grid.shape),
                  comparison_basis=geometry_note, native_grd=str(args.native_grd), iterations=args.iterations,
                  minimum_curvature_seconds=seconds,solver=model.metadata,
                  interior_metrics_by_erosion_cells=regions,
                  common_cells=int(common.sum()),mask_equal=bool(np.array_equal(np.isfinite(grid),np.isfinite(ref))),
                  rmse=float(np.sqrt(np.mean(delta**2))),mae=float(np.mean(np.abs(delta))),
                  correlation=float(np.corrcoef(grid[common],ref[common])[0,1]),
                  sinc_seconds=sinc_seconds,sinc=sinc.metadata,
                  sinc_shape=list(expanded.shape),sinc_original_samples_preserved=True,
                  source_unchanged=True,parity_certified=False)
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
