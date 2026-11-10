# 21. Self-potential and reference networks

[English](../en/21_potencial_espontaneo.md) · [Español](../es/21_potencial_espontaneo.md) · [Português](../pt/21_potencial_espontaneo.md)

## Quantity and references

Self-potential is measured as an electrode difference. Its level depends on the reference; combining profiles without resolving offsets can create artificial structures. Core APIs use volts, metres, S/m and amperes as appropriate. Convert acquisition mV to V before calculation and preserve original units in provenance.

adjust_reference_network handles reference differences. Check connectivity, anchors and loop closure. A network without a defined datum is not absolute potential. Electrode electrochemical changes and instrument drift require additional information; small network residuals do not remove them.

## Prescribed sources in a uniform medium

prescribed_source_potential and invert_source_currents model electrical sources with known conductivity in full space or under an insulating horizontal surface. Source position, strength and geometry belong to the problem. They do not directly infer water flow, permeability or electrokinetic coefficients from an SP map.

Fixed source geometry reduces the inverse problem. Compare sensitivity to geometry, conductivity and reference before attributing amplitudes to a physical process. Different source models can produce the same potential field.

## Finite heterogeneous conductor

self_potential_pde solves an equation of the form:

    −div(σ grad φ) = q

σ is prescribed positive isotropic cell conductivity; q is current source per volume in A/m³. Exterior faces are insulating. This finite domain is not an open infinite medium and requires consistent source balance and reference. The module does not automatically add air/topography through an active-cell mask.

Check sp_pde_forward and fit_sp_pde_sources against domain size, mesh and boundaries. If moving boundaries substantially changes predictions near observations, the first solution is not stable evidence.

## Practical review

Retain measured differences, references, times and drift controls. Verify a known case, current balance and units. Compare spatial residuals and weak-sensitivity regions. Report the result as source fitting under prescribed conductivity and boundaries.

See [other-method contracts](../../validation/reports/inversion_methods_validation.md), [implementation limits](../../research/core_expansion_implementation.md) and the [API reference](../../reference/api/en.md).

## Related implementation

[self_potential](../../../terraworkbench_core/self_potential.py), [self_potential_pde](../../../terraworkbench_core/self_potential_pde.py)

---

[Contents](README.md) · [Previous](20_em_mt.md) · [Next](22_ondas_sondeos.md)
