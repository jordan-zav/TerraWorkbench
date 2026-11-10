"""Causal, small-problem MVI diagnostics; no geological recovery tuning."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=serial, allow_nan=False) + "\n")


def cartesian_regularizer(mesh, active, reference):
    from simpeg import maps, regularization

    n = int(active.sum())
    wires = maps.Wires(*[(axis, n) for axis in "xyz"])
    terms = [
        regularization.Sparse(
            mesh,
            active_cells=active,
            mapping=getattr(wires, axis),
            reference_model=reference,
            reference_model_in_smooth=True,
            norms=[2.0] * 4,
        )
        for axis in "xyz"
    ]
    return sum(terms[1:], terms[0])


def simulation(mesh, active, xyz, *, spherical=False):
    from simpeg import maps
    from simpeg.potential_fields import magnetics

    survey = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(
            receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
            amplitude=50000.0,
            inclination=90.0,
            declination=0.0,
        )
    )
    if spherical:
        from terraworkbench_core.spherical_mvi import spherical_simulation

        return spherical_simulation(
            mesh,
            active,
            survey,
            store_sensitivities="ram",
            sensitivity_dtype=np.float64,
        )
    return magnetics.simulation.Simulation3DIntegral(
        mesh,
        active_cells=active,
        survey=survey,
        chiMap=maps.IdentityMap(nP=3 * int(active.sum())),
        model_type="vector",
        engine="choclo",
        sensitivity_dtype=np.float64,
    )


def runtime_record():
    from threadpoolctl import threadpool_info

    libraries = threadpool_info()
    for library in libraries:
        library["filepath"] = Path(library["filepath"]).name
    return dict(
        python=sys.version,
        platform=platform.platform(),
        libraries=libraries,
        threads={
            key: os.environ.get(key)
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMBA_NUM_THREADS",
            )
        },
        versions={
            p: version(p)
            for p in ("numpy", "scipy", "simpeg", "discretize", "choclo", "geoana")
        },
    )


def source_record():
    names = (
        "terraworkbench_core/inversion.py",
        "terraworkbench_core/spherical_mvi.py",
        "terraworkbench_core/inversion_diagnostics.py",
        "scripts/diagnose_mvi.py",
        "scripts/diagnose_mvi_nonlinear.py",
        "scripts/diagnose_mvi_large_subspace.py",
        "scripts/benchmark_mvi_reference.py",
        "scripts/benchmark_voxel_recovery.py",
    )
    return dict(
        commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        repository_dirty=repository_provenance(ROOT)["dirty"],
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names
        },
    )


def fixed_solve(
    sim,
    observed,
    sigma,
    reg,
    start,
    beta,
    *,
    lower=-np.inf,
    upper=np.inf,
    iterations=30,
    strict=True,
    controls=None,
    stop_scaled=None,
    optimizer_factory=None,
    line_search_iterations=30,
):
    from scipy.sparse import diags
    from simpeg import data, data_misfit, inverse_problem, inversion, directives
    from terraworkbench_core.inversion import _jacobi_optimizer, _cg_metrics

    misfit = data_misfit.L2DataMisfit(
        simulation=sim,
        data=data.Data(sim.survey, dobs=observed, standard_deviation=sigma),
    )
    factory = _jacobi_optimizer if optimizer_factory is None else optimizer_factory
    opt = factory(
        maxIter=iterations,
        lower=lower,
        upper=upper,
        cg_maxiter=1200,
        cg_rtol=1e-10,
        maxIterLS=line_search_iterations,
        tolF=1e-13,
        tolX=1e-13,
        tolG=1e-9,
        eps=1e-12 if strict else 1e-5,
    )
    problem = inverse_problem.BaseInvProblem(
        misfit, reg, opt, beta=beta, init_bfgs=False
    )
    history = []
    before = {}
    original = opt.findSearchDirection

    def direction():
        p = original()
        inactive = ~opt.activeSet(opt.xc)
        rhs = (-opt.g) * inactive
        residual = (opt.H @ p + opt.g) * inactive
        opt.true_relative_cg_residual = float(
            np.linalg.norm(residual) / max(np.linalg.norm(rhs), np.finfo(float).tiny)
        )
        return p

    opt.findSearchDirection = direction

    class Jacobi(directives.UpdatePreconditioner):
        def initialize(self):
            diagonal = 2 * sim.getJtJdiag(self.invProb.model, W=misfit.W)
            diagonal += self.invProb.beta * reg.deriv2(self.invProb.model).diagonal()
            floor = np.finfo(float).eps * max(float(diagonal.max()), 1.0)
            opt.approxHinv = diags(1.0 / np.maximum(diagonal, floor), format="csr")

        def endIter(self):
            self.initialize()

    class Trace(directives.InversionDirective):
        def endIter(self):
            value = self.invProb.model
            current_gradient = misfit.deriv(value) + problem.beta * reg.deriv(value)
            residual = kkt_gradient(value, current_gradient, lower, upper)
            relative = float(
                np.linalg.norm(residual)
                / max(
                    np.linalg.norm(misfit.deriv(start) + beta * reg.deriv(start)), 1.0
                )
            )
            history.append(
                dict(
                    iteration=int(opt.iter),
                    phi_d=float(problem.phi_d),
                    phi_m=float(problem.phi_m),
                    beta=float(problem.beta),
                    true_relative_cg_residual=opt.true_relative_cg_residual,
                    before_adaptation=before.copy(),
                    actual_phi_d=float(misfit(value)),
                    actual_phi_m=float(reg(value)),
                    scaled_projected_gradient=relative,
                    **_cg_metrics(opt),
                )
            )
            if stop_scaled is not None and relative <= stop_scaled:
                opt.stopNextIteration = True

    class Before(directives.InversionDirective):
        def endIter(self):
            before.update(
                phi_d=float(misfit(problem.model)),
                phi_m=float(reg(problem.model)),
                beta=float(problem.beta),
            )

    model = inversion.BaseInversion(
        problem, directiveList=[Before(), *(controls or []), Jacobi(), Trace()]
    ).run(start)
    gradient = misfit.deriv(model) + problem.beta * reg.deriv(model)
    projected = kkt_gradient(model, gradient, lower, upper)
    initial_gradient = misfit.deriv(start) + beta * reg.deriv(start)
    scale = max(np.linalg.norm(initial_gradient), np.finfo(float).tiny)
    return dict(
        model=np.asarray(model),
        objective=float(misfit(model) + problem.beta * reg(model)),
        final_beta=float(problem.beta),
        scaled_optimality=float(np.linalg.norm(projected) / scale),
        history=history,
        iterations=int(opt.iter),
        gradient=gradient,
        last_cg_metrics=_cg_metrics(opt),
        last_line_search_backtracks=int(getattr(opt, "iterLS", 0)),
        line_search_retry_events=getattr(opt, "spherical_line_search_retries", []),
        angular_safeguard_events=getattr(opt, "spherical_step_events", []),
    )


def kkt_gradient(model, gradient, lower, upper):
    """Gradient on feasible inward/free coordinates, without box-width clipping."""
    binding = ((model <= lower) & (gradient > 0)) | ((model >= upper) & (gradient < 0))
    return np.where(binding, 0.0, gradient)


def baseline_and_linear(output):
    from scripts.benchmark_mvi_reference import fixture
    from terraworkbench_core.inversion_diagnostics import (
        fixed_l2_reference,
        linear_error_partition,
    )

    mesh, active, xyz, _, noise, truth, support, clean = fixture("quick")
    sim = simulation(mesh, active, xyz)
    g = np.asarray(sim.G)
    n = g.shape[1]
    true = truth.ravel(order="F")
    sigma = np.full(len(xyz), noise)
    np.savez_compressed(
        output / "input.npz",
        G=g,
        clean=clean,
        sigma=sigma,
        truth=true,
        centers=mesh.cell_centers[active],
        volumes=mesh.cell_volumes[active],
    )
    forward_error = float(np.max(abs(g @ true - clean)))
    if forward_error > 1e-5:
        raise AssertionError(f"Independent physical response mismatch {forward_error}")
    uniform = g.reshape((len(xyz), 3, -1))[:, :, support].sum(axis=2)
    oracle = fixed_l2_reference(uniform, clean, sigma, np.zeros((0, 3)), beta=1.0)
    expected = truth[support][0]
    oracle_error = float(
        np.linalg.norm(oracle["model"] - expected) / np.linalg.norm(expected)
    )
    if oracle_error > 1e-5:
        raise AssertionError("Uniform three-component physical control failed")
    reference = np.linspace(-1e-5, 1e-5, n)
    reg = cartesian_regularizer(mesh, active, reference)
    h = reg.deriv2(np.zeros(n)).toarray() / 2
    eigenvalues, vectors = np.linalg.eigh(h)
    if eigenvalues.min() <= 0:
        raise AssertionError("L2 smallness must make prior positive definite")
    prior_factor = np.sqrt(eigenvalues)[:, None] * vectors.T
    probe = np.random.default_rng(7219).normal(size=n) * 0.001
    np.testing.assert_allclose(
        reg(probe), np.linalg.norm(prior_factor @ (probe - reference)) ** 2, rtol=1e-10
    )
    np.testing.assert_allclose(
        reg.deriv(probe), 2 * h @ (probe - reference), rtol=1e-9, atol=1e-8
    )
    records = []
    for ratio in (0.01, 0.1, 1.0):
        beta = float(
            ratio
            * np.linalg.norm(g / sigma[:, None]) ** 2
            / np.linalg.norm(prior_factor) ** 2
        )
        direct = fixed_l2_reference(
            g, clean, sigma, prior_factor, beta=beta, reference_model=reference
        )
        if direct["augmented_condition"] > 1e6:
            raise AssertionError(
                "Reference fixture exceeds preregistered moderate-condition scope"
            )
        for strict in (False, True):
            result = fixed_solve(
                sim, clean, sigma, reg, np.zeros(n), beta, strict=strict
            )
            delta = float(
                np.linalg.norm(result["model"] - direct["model"])
                / np.linalg.norm(direct["model"])
            )
            gradient = (g / sigma[:, None]).T @ ((g @ result["model"] - clean) / sigma)
            gradient += (
                beta * prior_factor.T @ prior_factor @ (result["model"] - reference)
            )
            denom = np.linalg.norm(
                (g / sigma[:, None]).T @ (clean / sigma)
                + beta * prior_factor.T @ prior_factor @ reference
            )
            optimality = float(np.linalg.norm(gradient) / denom)
            partition = linear_error_partition(
                g, sigma, result["model"] - true, np.tile(mesh.cell_volumes[active], 3)
            )
            partition.pop("row_error")
            partition.pop("null_error")
            case = dict(
                ratio=ratio,
                beta=beta,
                strict_stopping=strict,
                relative_reference_error=delta,
                scaled_optimality=optimality,
                augmented_condition=direct["augmented_condition"],
                objective=result["objective"],
                reference_objective=direct["objective"],
                model_error=float(
                    np.linalg.norm(result["model"] - true) / np.linalg.norm(true)
                ),
                partition=partition,
                history=result["history"],
                passed=delta <= 1e-5 and optimality <= 1e-8,
            )
            records.append(case)
            write(output / "linear.partial.json", records)
            print(
                json.dumps(
                    {
                        k: case[k]
                        for k in (
                            "ratio",
                            "strict_stopping",
                            "passed",
                            "relative_reference_error",
                            "scaled_optimality",
                        )
                    }
                ),
                flush=True,
            )
    return dict(
        forward_max_nt=forward_error,
        uniform_relative_error=oracle_error,
        linear_cases=records,
    )


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = dict(
        utc=datetime.now(timezone.utc).isoformat(),
        commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        seed=7219,
        runtime=runtime_record(),
        noise="zero; sigma remains positive at fixture scale",
        ratios=[0.01, 0.1, 1.0],
        tolerances=dict(
            physical_max_nt=1e-5,
            reference_model_relative=1e-5,
            scaled_optimality=1e-8,
            moderate_condition_max=1e6,
        ),
        versions={
            p: version(p)
            for p in ("numpy", "scipy", "simpeg", "discretize", "choclo", "geoana")
        },
        python=sys.version,
        platform=platform.platform(),
        source_sha256={
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in (
                "scripts/diagnose_mvi.py",
                "terraworkbench_core/inversion.py",
                "terraworkbench_core/spherical_mvi.py",
                "terraworkbench_core/inversion_diagnostics.py",
            )
        },
    )
    write(output / "protocol.json", protocol)
    result = baseline_and_linear(output)
    write(output / "results.json", dict(protocol=protocol, **result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
