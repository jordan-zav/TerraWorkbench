# 18. DC resistivity, ABMN geometry and PDE

[English](../en/18_electrica_dc.md) · [Español](../es/18_electrica_dc.md) · [Português](../pt/18_electrica_dc.md)

## Data and geometry

A DC measurement combines current electrodes A/B, potential electrodes M/N, current and voltage difference. Transfer resistance V/I is in ohms. A geometric factor converts it to apparent resistivity under a specified reference geometry/medium; it does not turn an observation into the true resistivity of a cell.

validate_abmn, geometric_factor, apparent_resistivity and reciprocal_errors check geometry, polarity and reciprocity. Retain electrode coordinates/configuration, including remote electrodes as defined by the contract. Large factors may amplify noise. Reciprocity assesses consistency, not the conductivity distribution by itself.

## Layered Earth

dc_layered and fit_dc_resistivity use explicit layer resistivities/thicknesses. There is one fewer thickness than layers when the final layer is a half-space. A good 1D fit needs consistency with the lateral-medium assumption; it does not prove absence of 2D/3D structure.

Compare sensitivity to thickness, separation range and noise. If thicknesses are fixed, report that fitted resistivities condition on that geometry and its bounds.

## 2.5D and 3D simulation

electrical_pde uses tensor meshes and ENU electrode coordinates in metres. A 2.5D section uses X/Z with a Y = 0 survey. Conductivity is S/m, transfer resistance ohms and IP chargeability V/V. There is no automatic snapping/draping: electrodes must be valid relative to mesh and terrain.

active_cells represents supplied Earth; inactive air uses the module's prescribed conductivity. Declare parameter_labels for zonal fitting. Zonal and cell-parameter inversion have different budgets and ambiguities.

## Minimum checks

Check mesh, origin, extent, units, expected half-space resistance and polarity. Examine mesh convergence and 2.5D transverse treatment. Inspect active cells and electrode positions before increasing iteration budgets to address poor fit.

Cell, parameter, work and factorisation limits protect execution; they do not guarantee regional-survey capacity. These APIs do not imply automatic meshing, terrain reconstruction or certified geological model selection.

See [other inversion methods](../../validation/reports/inversion_methods_validation.md), [PDE scope](../../research/core_expansion_implementation.md) and [SimPEG](https://simpeg.xyz/). Use current signatures to distinguish observations, sigma and log-parameterisation.

## Related implementation

[electrical](../../../terraworkbench_core/electrical.py), [layered_electrical](../../../terraworkbench_core/layered_electrical.py), [electrical_pde](../../../terraworkbench_core/electrical_pde.py)

---

[Contents](README.md) · [Previous](17_resolucion_incertidumbre.md) · [Next](19_ip_sip.md)
