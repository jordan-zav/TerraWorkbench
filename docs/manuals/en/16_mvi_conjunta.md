# 16. MVI, joint inversion and structural assumptions

[English](../en/16_mvi_conjunta.md) · [Español](../es/16_mvi_conjunta.md) · [Português](../pt/16_mvi_conjunta.md)

## Differences from scalar susceptibility

MVI allows effective magnetisation components instead of fixing direction to the inducing field. It increases parameter count and ambiguity. Improved fit may reflect flexibility, not a geologically correct recovered direction.

Cartesian representation uses axis components. Spherical representation separates amplitude and angles and introduces difficulties at zero amplitude and poles. When comparing/exporting, determine whether a field is effective SI susceptibility or A/m magnetisation; historical unsuffixed names retain documented compatibility conventions.

## Solver controls

Vector, amplitude and component regularisation impose different priors. The spherical scheme has a Cartesian stage and chart rules for zero amplitude/poles. An undefined polar azimuth is not a determined direction.

Scaling SI amplitudes against radian angles affects the inner solve. Diagnostics distinguish raw and scaled CG residuals; satisfying one does not imply satisfying the other. Adaptive IRLS is the Core reference; frozen-weight strategies remain experimental diagnostics and may exhaust budgets.

## Joint inversion

run_joint_cross_gradient_inversion combines gravity and magnetics with a cross-gradient penalty. It favours structural relations under the chosen weight but does not enforce a unique petrophysical relationship. Regions without gradients also affect interpretation of coupling.

Each dataset needs its own sigma, regional, component and units. Examine misfits separately: a low sum can conceal a poorly explained dataset. Distinguish data objective, CG tolerance and outer model-change criterion. Gauss–Newton cross-gradient Hessian and the historical stabilised mode retain recipe differences.

## Communicating current status

Repository reports include synthetic tests, comparisons and failed recovery cases. Do not summarise them as solved MVI or closed 3D inversion. Known-geometry and free-voxel experiments answer different questions.

Before interpretation, compare starting models, references, structural weights, bounds and resolution under a predeclared design. Reserve observations/geometries for final evaluation. Residual, direction and amplitude maps should be accompanied by convergence states and physical limits.

See [spherical MVI](../../reference/methods/spherical_mvi.md), [stability](../../validation/reports/mvi_stability.md), [IRLS](../../validation/reports/lagged_irls.md), [outer sensitivity](../../validation/reports/mvi_outer_sensitivity.md), [acceptance](../../validation/reports/mvi_acceptance.md) and [causal diagnosis](../../validation/reports/mvi_causal_diagnosis.md).

## Related implementation

[spherical_mvi](../../../terraworkbench_core/spherical_mvi.py)

---

[Contents](README.md) · [Previous](15_inversion_potencial.md) · [Next](17_resolucion_incertidumbre.md)
