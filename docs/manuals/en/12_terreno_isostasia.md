# 12. Terrain, isostasy, flexure and tensors

[English](../en/12_terreno_isostasia.md) · [Español](../es/12_terreno_isostasia.md) · [Português](../pt/12_terreno_isostasia.md)

## A defensible terrain model

Terrain modelling requires a DEM, resolution, extent, mask, vertical datum and density or density contrast. A finite DEM omits masses outside its domain. More detail does not necessarily improve a correction when receiver position is wrong or heights are inconsistent.

terrain_correction_prisms computes its defined slab-minus-finite-DEM-attraction term with explicit units and limits. terrain_gravity_adaptive computes DEM-contrast attraction at stations using nearby prisms and far-field approximations. Do not exchange their outputs because names look similar: determine whether an output is attraction, correction or a component of complete reduction.

## Cost and tolerance

The historical finite method may require quadratic work in cell count. Receiver blocks reduce temporaries but not physical interactions. The adaptive method permits controlled approximation; assess tolerance, near radius, mask and boundary effects at test stations.

A flat case and a known prism help verify signs and units. For large regions also assess whether planar geometry remains adequate. A prism API does not imply a regional spherical, multiresolution terrain solution for arbitrary scale.

## Airy isostasy

airy_root_thickness and airy_moho_depth predict root geometry under local compensation, density and reference-thickness assumptions. isostasy computes its effect with prisms or FFT. Isostatic residual depends on the chosen model; it is not an observationally unique removal of deep field.

FFT formulations have periodicity and boundary treatment; finite prisms have spatial truncation. Comparisons require identical support, reference, densities and signs. Marginal differences alone do not establish an implementation error.

## Flexure

thin_plate_flexure computes plate response under explicit loads and rheological models; scan_elastic_thickness explores parameters. The conceptual relationship D ∝ E Te³/(1 − ν²) shows sensitivity to elastic thickness. A Te scan with fixed loads and densities does not simultaneously estimate the entire lithosphere.

## Tensors

prism_gravity_tensor, rotate_tensor and tensor_invariants provide gradients and changes of basis. Record component order, ENU coordinates, rotation matrix and Eötvös units. Incorrect rotation can preserve some invariants while misplacing components. Avoid receivers at model singularities.

Sources: [Harmonica prisms](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.prism_gravity.html), [adaptive terrain](../../reference/methods/adaptive_terrain.md), [isostasy](../../reference/methods/isostasy.md) and [GMT flexure reference](https://docs.generic-mapping-tools.org/6.5/supplements/potential/grdflexure.html).

## Related implementation

[terrain_gravity](../../../terraworkbench_core/terrain_gravity.py), [adaptive_terrain](../../../terraworkbench_core/adaptive_terrain.py), [terrain_tree_walk](../../../terraworkbench_core/terrain_tree_walk.py), [isostasy](../../../terraworkbench_core/isostasy.py), [flexure](../../../terraworkbench_core/flexure.py), [potential_tensors](../../../terraworkbench_core/potential_tensors.py)

---

[Contents](README.md) · [Previous](11_gravimetria.md) · [Next](13_radiometria.md)
