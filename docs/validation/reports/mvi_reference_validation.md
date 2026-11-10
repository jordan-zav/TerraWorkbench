# MVI references and reproducible recovery checks

Subsequent evidence: the [MVI evidence map](../mvi_evidence_map.md) lists the
later diagnostic, acceptance and solver-comparison reports. This report and its
results are unchanged.

## Scope

MVI recovers Cartesian effective susceptibility vectors in ENU coordinates.
Physical magnetization is that vector multiplied by field amplitude in tesla
divided by vacuum permeability. A good TMI fit alone does not validate the
depth, volume, amplitude or direction of a recovered body.

Individual MVI inversions accept an explicit vector reference_model together
with reference_in_smooth set to true. The reference must contain three Cartesian
components per active cell, using either (n,3) or component-major (3n,) layout.
This preserves reference interfaces for both amplitude and vector_smooth
regularization. An implicit scalar reference is rejected. Defaults are unchanged.

Recovery metrics now accept explicit connectivity_edges instead of a distance
radius. Supply integer cell-index pairs from the mesh topology. A path through
an absent support cell cannot connect two recovered bodies. This avoids false
fragmentation when adaptive cells have very different center spacings; no
connectivity is inferred from the truth. The older radius option is retained.

## Reproduction

Run scripts/benchmark_mvi_reference.py with --output pointing to a new directory
and --scale quick or published. The published setup adapts the pinned SimPEG
0.25 example below. It is a synthetic experiment, not a reproduction of a field
interpretation or of every figure in a paper.

Independent dipole-volume quadrature generates the observations and is checked
for convergence. Native SimPEG uses its Geoana kernel and its own optimizer and
preconditioner. Core uses Choclo and its explicit Jacobi implementation. Both
use the same declared data, reference, bounds, seed and numerical budget.
Native and Core are independent assemblies of the same library family, not two
independent inversion theories. The external quadrature checks their physics.

The protocol fixes the existing six recovery gates before observations are
generated. Native and unconstrained Core are scored separately from an exact
support control. That control uses truth in fitting and cannot certify general
voxel recovery. All successful and failed recovery scores are retained.
Adaptive connectivity comes from two-cell total-face stencils, without changing
the physical recovery thresholds. Outputs include inputs, full models, residual
statistics, library versions, source hashes, partial records and final status.

## Sources reviewed on 2026-10-29

| Reference | Use and reproducibility boundary |
| --- | --- |
| [SimPEG 0.25 VectorAmplitude example](https://github.com/simpeg/simpeg/blob/v0.25.0/examples/03-magnetics/plot_inv_mag_MVI_VectorAmplitude.py) | MIT; pinned synthetic source adapted in the benchmark. Numerical budgets, seed and data generation are explicitly changed. |
| [Fournier, Heagy and Oldenburg, 2020](https://doi.org/10.1190/geo2019-0244.1), [authors' repository](https://github.com/ubcgif/2020-fournier-etal-geophysics) | Spherical sparse MVI and angular scaling. The repository contains the manuscript; this benchmark does not claim implementation of its full workflow. |
| [UBC MVI tutorial](https://giftoolscookbook.readthedocs.io/en/latest/content/AtoZ/magnetic/MVI.html), [coordinate definition](https://mvi.readthedocs.io/en/v3/content/theory.html) | Public TKC archive downloaded and hashed outside the repository. Direct interpretation of its vector model did not reproduce its observations; truth conventions remain unresolved. No recovery certification from this package. |
| [RBF MVI publication, 2026](https://doi.org/10.1093/gji/ggag186), [source snapshot](https://github.com/Lxd-cug/MVI-method/tree/8384805fbeabfbce6035d9491b188f574465b450) | MIT MATLAB repository inspected. The entry script requests deltaT3.dat and cuboid, absent from that snapshot; no complete reproduction claimed. Supplied deltaT1/2 files are not substituted without metadata. |
| [Weis and Heagy, 2026 preprint](https://arxiv.org/html/2610.36368v1) | Relevant vector constraints; not peer-reviewed at the review date. Its availability statement promises code upon publication and describes confidential field data. It is a research reference, not an executed benchmark. |

The TKC probe retains its failed convention hypotheses locally. No sign, axis,
scale or recovery threshold was selected just to force a public example to pass.

## Results recorded on 2026-10-29

The published adaptation has 27,971 active cells, 83,913 Cartesian parameters
and 400 observations. Core and native SimPEG model relative difference is
0.000001624. Both fail the unchanged model-error and 15-degree direction gates:
data prediction agreement does not establish recovery. The exact-support voxel
control still leaves independent magnetizations inside that support; uniform
magnetization is a stronger, explicitly truth-derived assumption.

| Published setup | Weighted data RMS | Model relative error | Angular error | All recovery gates |
| --- | --- | --- | --- | --- |
| Native SimPEG | 1.0327 | 91.02% | 19.53 degrees | Failed |
| Core | 1.0327 | 91.02% | 19.53 degrees | Failed |
| Core with exact support | 1.0411 | 99.64% | 6.40 degrees | Failed |
| Uniform known-prism GLS | 0.9683 | 0.55% | 0.32 degrees | Passed, oracle only |

The small authored setup reproduces the native solution too, while its Core
exact-support control reaches about 0.62% model error and 0.35-degree angular
error. Its success does not override the adaptive example's failure.

The [complete numerical record](../records/mvi_reference_20261029.json) includes
every case, criteria, source hashes and versions. Its execution commit is the
parent revision with an explicit dirty flag and hashes for the tested changes;
it is not presented as a clean checkout of that parent commit. The dedicated
MVI reference workflow independently regenerates and retains all four cases.

These results support numerical equivalence of the Cartesian engine,
not unrestricted MVI recovery. The subsequent [spherical implementation](../../reference/methods/spherical_mvi.md)
has separate validation; independent field validation remains open. No synthetic truth is used
as an unreported production prior and no new default was tuned to this example.
