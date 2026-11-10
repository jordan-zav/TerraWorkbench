"""Frozen coordinate/prior/IRLS ablations following the fixed-L2 control."""

import argparse
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.diagnose_mvi import (  # noqa: E402
    cartesian_regularizer,
    fixed_solve,
    simulation,
    write,
    runtime_record,
    source_record,
)


def micro_fixture():
    from discretize import TensorMesh
    from scipy.constants import mu_0
    from scripts.benchmark_voxel_recovery import integrated_fields, direction

    mesh = TensorMesh([[100.0, 100.0]] * 3, origin=[-100.0, -100.0, -200.0])
    active = np.ones(mesh.nC, bool)
    x, y = np.meshgrid(np.linspace(-200.0, 200.0, 7), np.linspace(-200.0, 200.0, 7))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    truth = np.zeros((mesh.nC, 3))
    truth[5] = 0.05 * direction(40.0, -20.0)
    center = mesh.cell_centers[5]
    prism = np.column_stack((center - 50.0, center + 50.0)).ravel()
    magnetization = truth[5][None, :] * 50000e-9 / mu_0
    _, vector = integrated_fields(xyz, [prism], [0.0], magnetization, order=20)
    _, finer = integrated_fields(xyz, [prism], [0.0], magnetization, order=24)
    np.testing.assert_allclose(vector, finer, rtol=1e-7, atol=1e-7)
    return (
        mesh,
        active,
        xyz,
        truth.ravel(order="F"),
        vector @ direction(90.0, 0.0),
        np.full(len(xyz), 0.05),
    )


def physical_prior(mesh, active, mapping):
    from simpeg import maps, regularization

    n = int(active.sum())
    wires = maps.Wires(*[(axis, n) for axis in "xyz"])
    terms = [
        regularization.Sparse(
            mesh,
            active_cells=active,
            mapping=getattr(wires, axis) * mapping,
            reference_model=np.zeros(3 * n),
            reference_model_in_smooth=True,
            norms=[2.0] * 4,
        )
        for axis in "xyz"
    ]
    return sum(terms[1:], terms[0])


def derivative_check(g, sigma, data, mapping, reg, beta, model):
    rng = np.random.default_rng(7219)
    vector = rng.normal(size=len(model))
    vector[: len(model) // 3] *= 0.01

    def objective(m):
        residual = (g @ (mapping * m) - data) / sigma
        return float(residual @ residual + beta * reg(m))

    residual = (g @ (mapping * model) - data) / sigma**2
    gradient = 2 * mapping.deriv(model).T @ (g.T @ residual) + beta * reg.deriv(model)
    analytic = float(gradient @ vector)
    errors = []
    for step in (1e-3, 1e-4, 1e-5):
        difference = (
            objective(model + step * vector) - objective(model - step * vector)
        ) / (2 * step)
        errors.append(float(abs(difference - analytic) / max(abs(analytic), 1.0)))
    if max(errors[-2:]) > 1e-5:
        raise AssertionError(f"Spherical objective gradient failed: {errors}")
    return errors


def bounds_control(matrix, clean, sigma):
    from discretize import TensorMesh
    from scipy.optimize import lsq_linear
    from simpeg import simulation as sdk_simulation, regularization, maps

    class Linear(sdk_simulation.LinearSimulation):
        def getJtJdiag(self, m, W=None, f=None):
            return np.sum((self.G if W is None else W @ self.G) ** 2, axis=0)

    sim = Linear(G=matrix, model_map=maps.IdentityMap(nP=3))
    mesh = TensorMesh([np.ones(3)])
    reg = regularization.WeightedLeastSquares(
        mesh, alpha_s=1.0, alpha_x=0.0, reference_model=np.zeros(3)
    )
    beta = 0.01 * np.linalg.norm(matrix / sigma[:, None]) ** 2 / 3
    a = np.vstack((matrix / sigma[:, None], np.sqrt(beta) * np.eye(3)))
    b = np.r_[clean / sigma, np.zeros(3)]
    cases = []
    for cap in (np.full(3, 0.01), np.array([0.05, 0.01, 0.05])):
        reference = lsq_linear(a, b, bounds=(-cap, cap), method="bvls", tol=1e-13)
        if not reference.success:
            raise AssertionError("Independent bounded reference failed")
        for label, start in (("interior", np.zeros(3)), ("all_at_lower", -cap)):
            for strict in (False, True):
                solved = fixed_solve(
                    sim,
                    clean,
                    sigma,
                    reg,
                    start,
                    beta,
                    lower=-cap,
                    upper=cap,
                    iterations=120,
                    stop_scaled=1e-10,
                    strict=strict,
                )
                delta = float(
                    np.linalg.norm(solved["model"] - reference.x)
                    / np.linalg.norm(reference.x)
                )
                cases.append(
                    dict(
                        start=label,
                        cap=cap,
                        strict_stopping=strict,
                        relative_reference_error=delta,
                        passed=delta <= 1e-5 and solved["scaled_optimality"] <= 1e-8,
                        **solved,
                    )
                )
    return cases


def run(output):
    from simpeg import directives
    from types import SimpleNamespace
    from terraworkbench_core.spherical_mvi import (
        exact_spherical_map,
        spherical_from_cartesian,
        cartesian_from_spherical,
        spherical_regularizer,
    )
    from terraworkbench_core.inversion_diagnostics import (
        fixed_l2_reference,
        linear_error_partition,
    )

    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            seed=7219,
            runtime=runtime_record(),
            provenance=source_record(),
            mesh_cells=8,
            data=49,
            beta_rule="0.01 * Frobenius(WdG)^2 / Frobenius(L)^2",
            stages=[
                "physical_L2",
                "angular_L2",
                "angle_scaling",
                "frozen_sensitivity",
                "updated_sensitivity",
                "beta_cooling",
                "sparse_irls",
            ],
            iterations=30,
            cg_maxiter=1200,
            cg_rtol=1e-10,
            noise_seeds=[7219, 7220, 7221],
            noise_scales=[0.0, 1.0],
            gradient_tolerance=1e-5,
            physical_equivalent_model_tolerance=1e-5,
            note="Only small controls; no threshold chosen from recovery truth",
        ),
    )
    mesh, active, xyz, truth, clean, sigma = micro_fixture()
    cart = simulation(mesh, active, xyz)
    g = np.asarray(cart.G)
    n = mesh.nC
    np.testing.assert_allclose(g @ truth, clean, rtol=1e-7, atol=1e-7)
    np.savez_compressed(
        output / "input.npz",
        G=g,
        clean=clean,
        sigma=sigma,
        truth=truth,
        xyz=xyz,
        centers=mesh.cell_centers,
        volumes=mesh.cell_volumes,
    )
    reg = cartesian_regularizer(mesh, active, np.zeros(3 * n))
    eigen, vectors = np.linalg.eigh(reg.deriv2(np.zeros(3 * n)).toarray() / 2)
    prior_factor = np.sqrt(eigen)[:, None] * vectors.T
    beta = (
        0.01
        * np.linalg.norm(g / sigma[:, None]) ** 2
        / np.linalg.norm(prior_factor) ** 2
    )
    direct = fixed_l2_reference(g, clean, sigma, prior_factor, beta=beta)
    start = spherical_from_cartesian(direct["model"].reshape((n, 3), order="F"))
    # Data-derived fixed-L2 start; not the generating truth.
    start[:n] *= 0.95
    start[n : 2 * n] += 0.02
    mapping = exact_spherical_map(n)
    composed = physical_prior(mesh, active, mapping)
    np.testing.assert_allclose(
        composed(start),
        np.linalg.norm(prior_factor @ (mapping * start)) ** 2,
        rtol=1e-10,
    )
    invariant = float(
        np.max(
            abs(
                g @ (mapping * start)
                - simulation(mesh, active, xyz, spherical=True).dpred(start)
            )
        )
    )
    finite_difference = derivative_check(
        g, sigma, clean, mapping, composed, beta, start
    )
    bounds = bounds_control(
        g.reshape((len(xyz), 3, n))[
            :, :, truth.reshape((n, 3), order="F").any(axis=1)
        ].sum(axis=2),
        clean,
        sigma,
    )
    write(output / "bounds.json", bounds)
    records = []
    for stage in range(7):
        sim = simulation(mesh, active, xyz, spherical=True)
        controls = []
        if stage == 0:
            selected = physical_prior(mesh, active, sim.chiMap)
        else:
            selected, angle_scale = spherical_regularizer(
                mesh,
                active,
                np.zeros(3 * n),
                np.array([0.0, 1.0, 1.0, 1.0]) if stage == 6 else np.full(4, 2.0),
                np.ones(3) if stage == 6 else np.full(3, 2.0),
                None,
                False,
                None,
            )
            if stage >= 2:
                controls.append(angle_scale)
            if stage == 5:
                controls.append(
                    directives.BetaSchedule(coolingFactor=2.0, coolingRate=1)
                )
            if stage == 6:
                controls.append(
                    directives.UpdateIRLS(
                        max_irls_iterations=10,
                        chifact_start=1.0,
                        chifact_target=1.0,
                        cooling_factor=2.0,
                        cooling_rate=1,
                    )
                )
            if stage >= 3:

                class Prior(directives.UpdateSensitivityWeights):
                    @property
                    def simulation(self):
                        return [
                            SimpleNamespace(
                                getJtJdiag=lambda m, W=None, f=None: (
                                    sim.regularization_diagonal(
                                        m, W, "component_approximation"
                                    )
                                )
                            )
                        ]

                controls.append(Prior(every_iteration=stage >= 4))
        lower = np.r_[np.zeros(n), np.full(n, -np.pi / 2), np.full(n, -np.inf)]
        upper = np.r_[np.full(n, 10.0), np.full(n, np.pi / 2), np.full(n, np.inf)]
        solved = fixed_solve(
            sim,
            clean,
            sigma,
            selected,
            start.copy(),
            beta,
            lower=lower,
            upper=upper,
            controls=controls,
            stop_scaled=1e-10 if stage <= 1 else None,
        )
        physical = cartesian_from_spherical(solved["model"])
        delta = float(
            np.linalg.norm(physical - direct["model"]) / np.linalg.norm(direct["model"])
        )
        records.append(
            dict(
                stage=stage,
                physical_model=physical,
                relative_cartesian_optimum_error=delta,
                equivalent_objective_passed=delta <= 1e-5 if stage == 0 else None,
                truth_model_error=float(
                    np.linalg.norm(physical - truth) / np.linalg.norm(truth)
                ),
                weighted_rms=float(
                    np.linalg.norm((g @ physical - clean) / sigma) / np.sqrt(len(clean))
                ),
                **solved,
            )
        )
        write(output / "ablations.partial.json", records)
        print(
            f"ABLATION {stage}: reference_delta={delta:.5g}, WRMS={records[-1]['weighted_rms']:.5g}",
            flush=True,
        )
    noise_cases = []
    for scale in (0.0, 1.0):
        for seed in (7219, 7220, 7221):
            observed = clean + scale * sigma * np.random.default_rng(seed).normal(
                size=len(clean)
            )
            result = fixed_l2_reference(g, observed, sigma, prior_factor, beta=beta)
            unregularized, _, _, _ = np.linalg.lstsq(
                g / sigma[:, None], observed / sigma, rcond=None
            )
            error = result["model"] - truth
            partition = linear_error_partition(
                g, sigma, error, np.tile(mesh.cell_volumes, 3)
            )
            partition.pop("row_error")
            partition.pop("null_error")
            noise_cases.append(
                dict(
                    noise_scale=scale,
                    seed=seed,
                    model_relative_error=float(
                        np.linalg.norm(error) / np.linalg.norm(truth)
                    ),
                    unregularized_model_relative_error=float(
                        np.linalg.norm(unregularized - truth) / np.linalg.norm(truth)
                    ),
                    partition=partition,
                )
            )
    report = dict(
        prediction_invariance_max_nt=invariant,
        gradient_errors=finite_difference,
        bounds=bounds,
        ablations=records,
        resolution=noise_cases,
    )
    write(output / "results.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
