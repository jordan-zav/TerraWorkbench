# 3. Coordinates, units, heights and conventions

[English](../en/03_coordenadas.md) · [Español](../es/03_coordenadas.md) · [Português](../pt/03_coordenadas.md)

## Spatial contract

Distance and Fourier operations require known horizontal units. A number such as 500000 does not identify a UTM zone or datum. Assigning a CRS describes existing coordinates; reprojection computes new coordinates. Relabelling the CRS does not repair an incorrect transformation.

reproject_xy accepts horizontal 2D CRSs, explicit XY order and rejection of unauthorised approximate transformations. It does not transform elevations. If the best operation needs missing datum grids, investigate rather than silently accepting another operation. The QGIS adapter retains its own transformation context.

## Heights that must remain distinct

| Quantity | Typical use | Precaution |
| --- | --- | --- |
| Ellipsoidal elevation | GNSS position | Not orthometric height |
| Orthometric elevation | Terrain relative to the geoid | Record the geoid model |
| Height above terrain | Sensor–ground clearance | Needs compatible sensor position and DEM |
| Sensor elevation | Receiver Z coordinate | May differ from antenna or platform elevation |
| Sensor separation | Gradients or paired data | Does not replace absolute elevation |

A towed sensor may have vertical and horizontal offsets. A nominal height documents an approximation, not a measured sensor trajectory. Keep DEM, topography and receiver in compatible vertical frames.

## Physical conventions

The Core often uses East, North and Up. Component signs nevertheless depend on the API: gravity inversion allows up or down, the gravity polygon returns a downward component, and MT tensors use North/East horizontal axes. Consult the module contract rather than inferring signs from a plot.

For magnetics, downward-positive inclination and declination from true north are not necessarily the angles of a projected mesh. Where appropriate, use D_grid = D_true − meridian convergence and verify its sign by projecting a known heading.

| Conversion | Relationship |
| --- | --- |
| Gravity | 1 mGal = 10⁻⁵ m/s² |
| Gravity gradient | 1 Eötvös = 10⁻⁹ s⁻² |
| Magnetic field | 1 nT = 10⁻⁹ T |
| Density | 1 g/cm³ = 1,000 kg/m³ |
| Susceptibility | SI, dimensionless |
| Chargeability | V/V; distinguish from mV/V |

## Raster, masks and pixels

Check dimensions, affine transform, row orientation, pixel centres and NoData. A north-up raster often has negative geographic Y step although inter-row sampling distance is positive. FFT functions receive sampling distances; physical axis orientation must be resolved beforehand.

Retain zero as a valid measurement where appropriate. NaN and masks do not mean zero amplitude. Also inspect band scale and offset to avoid filtering stored integers instead of physical quantities.

Sources: [GDAL raster model](https://gdal.org/en/stable/user/raster_data_model.html), [PROJ transformations](https://proj.org/en/stable/usage/transformation.html) and the [standalone coordinate contract](../../development/standalone_acquisition.md).

## Related implementation

[coordinates](../../../terraworkbench_core/coordinates.py)

---

[Contents](README.md) · [Previous](02_instalacion.md) · [Next](04_importacion.md)
