# 14. Structural attributes and source depth

[English](../en/14_estructura_profundidad.md) · [Español](../es/14_estructura_profundidad.md) · [Português](../pt/14_estructura_profundidad.md)

## Mathematical products and interpretation

Gradients, phase, texture and orientations support contrast exploration. A computed edge is not automatically a fault, lithological contact or mineralised body. Recording scale, prior filtering and mask distinguishes an interpretation from the numerical product behind it.

structural_attributes contains multiscale monogenic phase, local texture and orientation entropy. Wavelengths, bandwidth, noise threshold, value range and bin origin affect results. Axial entropy recognises that directions separated by 180° may describe one axis. Sampling or flight texture can also create a dominant orientation.

lineament_geometry converts boolean skeletons into paths. Mask, metric spacing and first-pixel origin are explicit. Branches, cycles and endpoints must not be smoothed or joined without recording another operation. Length depends on pixel representation and connectivity.

## Euler

The homogeneity equation relates field derivatives to source position, background and structural index. A common form is:

    (x − x0) Tx + (y − y0) Ty + (z − z0) Tz = N (B − T)

Index N, window size, derivatives, coordinates and background must agree. A solution cloud can reflect noise, mixed sources or poor conditioning. euler_window, euler_grid and euler_profile do not justify accepting every solution merely because a linear fit completed.

## Werner and SPI

werner_profile and spi_profile rely on source and profile-geometry assumptions. Review source model, window length, sampling, height and edges. A depth from a contact approximation differs in interpretation from one for a cylindrical source. Grid and profile APIs do not automatically share all assumptions.

## Interpretation procedure

1. Define the geological question and a plausible source model.
2. Prepare a field with known corrections and units.
3. Compare scales/windows without selecting only the most attractive result.
4. Reject insufficient support, range or conditioning using predeclared criteria.
5. Compare independent data, terrain, mapping and trajectories.
6. Export solution catalogue and parameters, as well as the chosen figure.

See [source depth](../../reference/methods/source_depth.md), [structural attributes](../../reference/methods/structural_attributes.md) and their method-specific references. Depth catalogues are model solutions, not direct basement observations.

## Related implementation

[source_depth](../../../terraworkbench_core/source_depth.py), [structural_attributes](../../../terraworkbench_core/structural_attributes.py), [lineament_geometry](../../../terraworkbench_core/lineament_geometry.py)

---

[Contents](README.md) · [Previous](13_radiometria.md) · [Next](15_inversion_potencial.md)
