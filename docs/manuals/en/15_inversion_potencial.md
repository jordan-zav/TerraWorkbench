# 15. Gravity and susceptibility modelling and inversion

[English](../en/15_inversion_potencial.md) · [Español](../es/15_inversion_potencial.md) · [Português](../pt/15_inversion_potencial.md)

## Preparing the problem

Inversion needs observations, uncertainties, receiver coordinates, mesh, active mask and a physical property–response relationship. Potential-field mesh coordinates are metres with upward-positive elevations. Declare the gravity component: up or down. Susceptibility uses TMI in nT and SI properties; the integral gravity engine uses density in g/cm³.

Do not invert observed gravity or total magnetic field without defining regional and corrections appropriate to the model. regional_prediction is removed in data space; reference_model regularises properties. These are different terms, not substitutes.

## Objective and constraints

A reference formulation combines misfit and regularisation:

    φ(m) = ‖Wd (F(m) − d)‖² + β φm(m, mref)

Wd depends on standard deviations in data units. Choosing arbitrary sigma and then claiming weighted RMS ≈ 1 certifies instrument noise is incorrect. Regularisation, beta, norm and reference supply information or preferences about the model.

run_potential_field_inversion accepts built or supplied meshes, active cells, scalar/per-cell bounds, starting model and reference. spatial_property_constraints and build_cell_difference_prior add explicit hypotheses. Do not derive geological constraints from the same anomaly and subsequently treat them as independent evidence.

## Discretisation and memory

Define cell size, depth, padding and topography before fitting. A receiver inside an active prism may create physical or numerical problems. Air/ground separation must match the representation.

For N data and M parameters, a dense scalar sensitivity needs approximately N × M × bytes_per_element. MVI adds three components. RAM, disk and matrix_free modes trade storage, computation and I/O; matrix_free does not remove evaluation cost or guarantee faster execution.

## Execution and export

run_inversion_workflow publishes NPZ, VTK, data CSV and run.json in a new directory. It retains observations, sigma, regional, predictions, model and history. require_data_target can enforce the data objective, but completed execution does not demonstrate geological recovery.

Scalar gravity output is density contrast. Negative susceptibility, where allowed, is an effective contrast under the adopted reference and regional, not automatically an absolute measured property.

## Known geometry versus free geometry

fit_prism_density and fit_prism_magnetization estimate properties of fixed-geometry prisms. This condition reduces ambiguity and differs from recovering a free voxel body. apparent_layer_property also conditions on layer geometry; stabilisation and background must be declared.

See [standalone controls](../../development/standalone_inversion.md), [regularisation](../../reference/methods/regularization_conventions.md), [apparent properties](../../reference/methods/apparent_properties.md), [recovery](../../validation/reports/voxel_recovery_validation.md) and [SimPEG](https://simpeg.xyz/).

## Related implementation

[inversion](../../../terraworkbench_core/inversion.py), [inversion_workflows](../../../terraworkbench_core/inversion_workflows.py), [spatial_constraints](../../../terraworkbench_core/spatial_constraints.py), [regularization_profiles](../../../terraworkbench_core/regularization_profiles.py), [prism_inversion](../../../terraworkbench_core/prism_inversion.py), [apparent_properties](../../../terraworkbench_core/apparent_properties.py)

---

[Contents](README.md) · [Previous](14_estructura_profundidad.md) · [Next](16_mvi_conjunta.md)
