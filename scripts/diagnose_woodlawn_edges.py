"""Spatial diagnosis on a fixed common mask; run with QGIS Python.

The existing baseline report supplies source provenance and native-node axes.
No source rasters are modified. All maps use the same signed-error scale.
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm
import numpy as np
from osgeo import gdal, osr
from scipy.ndimage import binary_fill_holes, distance_transform_edt
from scipy.spatial import cKDTree, ConvexHull, Delaunay

gdal.UseExceptions()


def read(path):
    ds = gdal.Open(str(path))
    a = ds.ReadAsArray().astype(float)
    nd = ds.GetRasterBand(1).GetNoDataValue()
    if nd is not None:
        a[a == nd] = np.nan
    return a, ds.GetGeoTransform(), ds.GetProjection()


def stats(error, mask, common):
    use = mask & common
    e = error[use]
    total = np.sum(error[common]**2)
    return dict(cells=int(use.sum()), cell_percent=float(100*use.sum()/common.sum()),
                rmse=float(np.sqrt(np.mean(e**2))) if len(e) else None,
                mae=float(np.mean(abs(e))) if len(e) else None,
                bias=float(np.mean(e)) if len(e) else None,
                squared_error_percent=float(100*np.sum(e**2)/total) if total else 0.)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--old', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    provenance = json.loads((args.baseline/'report.json').read_text(encoding='utf-8'))
    ref, _, _ = read(provenance['reference'])
    baseline, gt, wkt = read(args.baseline/'minimum_curvature.tif')
    old, old_gt, old_wkt = read(args.old/'minimum_curvature.tif')
    assert old.shape == baseline.shape and old_wkt == wkt and np.allclose(old_gt,gt,rtol=0,atol=1e-7)
    variants = {'Anterior: nodos corregidos': old, 'Variacional: 23 septiembre': baseline}
    if args.candidate:
        candidate, cgt, cwkt = read(args.candidate)
        assert candidate.shape == baseline.shape and cwkt == wkt and np.allclose(cgt,gt,rtol=0,atol=1e-7)
        variants['Corrección: 24 septiembre'] = candidate
    common = np.isfinite(ref)
    for a in variants.values():
        common &= np.isfinite(a)
    raw = np.loadtxt(provenance['source'], delimiter='\t', skiprows=1, usecols=(5,6,13))
    src = osr.SpatialReference()
    src.ImportFromEPSG(4326)
    dst = osr.SpatialReference(wkt=wkt)
    for crs in (src,dst):
        crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    points = np.asarray(osr.CoordinateTransformation(src,dst).TransformPoints(raw[:,[1,0]]))[:,:2]
    rows, cols = baseline.shape
    x = gt[0]+(np.arange(cols)+.5)*gt[1]
    y = gt[3]+(np.arange(rows)+.5)*gt[5]
    xx,yy = np.meshgrid(x,y)
    nodes = np.column_stack((xx.ravel(),yy.ravel()))
    nearest = cKDTree(points).query(nodes)[0].reshape(ref.shape)
    hull = ConvexHull(points)
    inside = (Delaunay(points[hull.vertices]).find_simplex(nodes) >= 0).reshape(ref.shape)
    # Explicit padding treats all four array edges symmetrically.
    edge_distance = distance_transform_edt(np.pad(common,1))[1:-1,1:-1]*gt[1]
    exterior = ~binary_fill_holes(common)
    holes = ~common & ~exterior
    rr,cc = np.indices(ref.shape)
    rect_distance = np.minimum.reduce([rr+1,rows-rr,cc+1,cols-cc])*gt[1]
    regions = {'all':common,'outside_data_hull':~inside,'inside_data_hull':inside,
               'outer_rectangle_1m':rect_distance<=1.,
               'coverage_edge_1m_away_from_rectangle':(edge_distance<=1.)&(rect_distance>1.),
               'coverage_edge_0_1m':edge_distance<=1.,
               'coverage_edge_1_3m':(edge_distance>1.)&(edge_distance<=3.),
               'interior_over_3m':edge_distance>3.,
               'nearest_data_over_1m':nearest>1.}
    if holes.any():
        regions['near_internal_holes_1m'] = distance_transform_edt(~holes)*gt[1]<=1.
    quadrants = {'NW':(xx<x.mean())&(yy>=y.mean()),'NE':(xx>=x.mean())&(yy>=y.mean()),
                 'SW':(xx<x.mean())&(yy<y.mean()),'SE':(xx>=x.mean())&(yy<y.mean())}
    reports = {}
    raster_paths = []
    for name, grid in variants.items():
        err = grid-ref
        path = args.output/f'error_{len(raster_paths)+1}.tif'
        ds = gdal.GetDriverByName('GTiff').Create(str(path),cols,rows,1,gdal.GDT_Float64)
        ds.SetGeoTransform(gt)
        ds.SetProjection(wkt)
        ds.SetMetadataItem('ERROR_DEFINITION','Terra minus Oasis, nT; fixed common mask')
        ds.SetMetadataItem('VARIANT',name)
        ds.GetRasterBand(1).SetNoDataValue(float('nan'))
        ds.GetRasterBand(1).WriteArray(np.where(common,err,np.nan))
        ds = None
        raster_paths.append(str(path.resolve()))
        indices = np.flatnonzero(common)
        largest = indices[np.argsort(abs(err.ravel()[indices]))[-10:][::-1]]
        reports[name] = dict(regions={k:stats(err,v,common) for k,v in regions.items()},
                             quadrants={k:stats(err,v,common) for k,v in quadrants.items()},
                             largest_errors=[dict(row=int(i//cols),col=int(i%cols),x=float(xx.ravel()[i]),
                                 y=float(yy.ravel()[i]),error=float(err.ravel()[i]),reference=float(ref.ravel()[i]),
                                 nearest_data_m=float(nearest.ravel()[i])) for i in largest],
                             finite_cells=int(np.isfinite(grid).sum()))
    files = [Path(provenance['reference']), args.old/'minimum_curvature.tif',args.baseline/'minimum_curvature.tif']
    if args.candidate:
        files.append(args.candidate)
    output = dict(source_report=str((args.baseline/'report.json').resolve()),common_cells=int(common.sum()),
                  reference_finite_cells=int(np.isfinite(ref).sum()),error_rasters=raster_paths,
                  inputs=[dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],
                  internal_hole_cells=int(holes.sum()),regions_overlap=True, variants=reports)
    (args.output/'spatial_report.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    np.savez_compressed(args.output/'diagnostic_arrays.npz',points=points,values=raw[:,2],
                        reference=ref,baseline=baseline,old=old,x=x,y=y,gt=gt,wkt=wkt,
                        common=common,nearest=nearest,inside_hull=inside,edge_distance=edge_distance)
    fig, axes = plt.subplots(1,len(variants)+1,figsize=(5*(len(variants)+1),7),layout='constrained')
    extent=(x[0]-gt[1]/2-x[0],x[-1]+gt[1]/2-x[0],y[-1]+gt[5]/2-y[-1],y[0]-gt[5]/2-y[-1])
    norm=SymLogNorm(linthresh=1.,vmin=-400,vmax=400,base=10)
    for ax,(name,grid) in zip(axes,variants.items()):
        im=ax.imshow(np.where(common,grid-ref,np.nan),origin='upper',extent=extent,
                     cmap='RdBu_r',norm=norm,interpolation='nearest')
        ax.contour(xx-x[0],yy-y[-1],inside.astype(float),levels=[.5],colors='#20252b',linewidths=.6)
        ax.set_title(name+'\nTerra − Oasis (nT)',fontsize=11)
        fig.colorbar(im,ax=ax,shrink=.7,label='nT; escala simétrica logarítmica')
    ax=axes[-1]
    im=ax.imshow(np.where(common,nearest,np.nan),origin='upper',extent=extent,cmap='cividis',vmin=0,vmax=3)
    ax.set_title('Distancia al dato más cercano',fontsize=11)
    fig.colorbar(im,ax=ax,shrink=.7,label='m')
    for ax in axes:
        ax.set_xlabel(f'Este desde {x[0]:.3f} m')
        ax.set_ylabel(f'Norte desde {y[-1]:.3f} m')
    fig.suptitle(f'Woodlawn · nodos GRD · {common.sum():,} celdas comunes\nContorno negro: envolvente convexa de datos; blanco: excluido de comparación',fontsize=13)
    fig.savefig(args.output/'spatial_error.png',dpi=170)
    plt.close(fig)
    print(json.dumps(output,indent=2))


if __name__ == '__main__':
    main()
