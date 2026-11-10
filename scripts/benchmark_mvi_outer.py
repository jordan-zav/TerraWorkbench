"""Separate adaptive IRLS continuation from frozen-prior beta sensitivity.

Diagnostic only: no production defaults or recovery criteria are changed.
Run all declared branches; truth is used only after optimization for scoring.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402


def prior_digest(reg):
    """Hash effective frozen weights, multipliers, norms and thresholds."""
    digest = hashlib.sha256()
    for block, multiplier in zip(reg.objfcts, reg.multipliers):
        digest.update(np.asarray([multiplier], dtype=float).tobytes())
        digest.update(np.asarray(block.multipliers, dtype=float).tobytes())
        for term in block.objfcts:
            weight = term.W.tocsr()
            for value in (weight.data, weight.indices, weight.indptr):
                digest.update(np.ascontiguousarray(value).tobytes())
            digest.update(str(term.irls_threshold).encode())
            digest.update(str(term.norm).encode())
    return digest.hexdigest()


def frozen_branch(problem, start, beta, budget, output, inputs, mesh, active):
    from scipy.sparse import diags
    from terraworkbench_core.spherical_mvi import (
        spherical_optimizer,
        cartesian_from_spherical,
    )
    from terraworkbench_core.recovery_metrics import model_recovery_metrics
    from scripts.benchmark_voxel_recovery import CRITERIA

    old = problem.opt
    n = len(start) // 3
    opt = spherical_optimizer(
        n,
        bounded_angles=True,
        maxIter=budget,
        lower=old.lower.copy(),
        upper=old.upper.copy(),
        cg_maxiter=800,
        cg_rtol=1e-4,
        maxIterLS=20,
        tolF=1e-12,
        tolX=1e-12,
        tolG=1e-9,
    )
    problem.opt = opt
    opt.parent = problem
    problem.beta = beta
    reg = problem.reg
    misfit = problem.dmisfit
    sim = misfit.objfcts[0].simulation
    before = prior_digest(reg)
    history = []
    metric = None
    initial_measure = None
    stop_reason = None
    original_stop = opt.stoppingCriteria

    def jacobi(model):
        diagonal = (
            2 * sim.getJtJdiag(model, W=misfit.objfcts[0].W)
            + beta * reg.deriv2(model).diagonal()
        )
        floor = np.finfo(float).eps * max(float(diagonal.max()), 1.0)
        return np.maximum(diagonal, floor)

    opt.approxHinv = diags(1 / jacobi(start))

    def stop(inLS=False):
        nonlocal metric, initial_measure, stop_reason
        if inLS:
            return original_stop(inLS=True)
        diagonal = jacobi(opt.xc)
        opt.approxHinv = diags(1 / diagonal)
        if metric is None:
            metric = diagonal.copy()
        projected = opt.projection(opt.xc - opt.g / metric) - opt.xc
        measure = float(np.linalg.norm(np.sqrt(metric) * projected))
        if initial_measure is None:
            initial_measure = measure
        threshold = max(1e-3 * initial_measure, 1e-12)
        row = dict(
            iteration=int(opt.iter),
            objective=float(opt.f),
            projected_gradient_metric=measure,
            threshold=threshold,
            relative_projected_gradient=measure / max(initial_measure, 1e-300),
            cg_raw=getattr(opt, "cg_true_rel_resid", None),
            cg_scaled=opt.cg_scaled_rel_resid,
            cg_breakdown=getattr(opt, "cg_breakdown", None),
        )
        if history:
            assert row["objective"] <= history[-1]["objective"] + 1e-9 * max(
                abs(history[-1]["objective"]), 1.0
            ), "Frozen objective increased"
        history.append(row)
        if measure <= threshold:
            stop_reason = "projected_gradient_reduction"
            return True
        if opt.iter >= budget:
            stop_reason = "newton_budget"
            return True
        return False

    opt.stoppingCriteria = stop
    recovered = opt.minimize(problem.evalFunction, start.copy())
    if stop_reason is None:
        stop_reason = (
            "line_search_failed" if opt.spherical_search_failed else "optimizer_stop"
        )
    assert prior_digest(reg) == before, "Frozen regularization changed"
    physical = cartesian_from_spherical(recovered)
    predicted = np.asarray(sim.dpred(recovered))
    np.savez_compressed(
        output / "model.npz",
        model=physical,
        spherical=recovered,
        predicted=predicted,
        start=start,
        metric=metric,
    )
    recovery = model_recovery_metrics(
        inputs["centers"],
        inputs["volumes"],
        physical.reshape((n, 3), order="F"),
        inputs["truth"],
        criteria=CRITERIA,
        connectivity_edges=inputs["connectivity_edges"],
        vector=True,
        max_cells=250000,
        max_links=2000000,
    )
    result = dict(
        state="complete",
        beta=float(beta),
        prior_sha256=before,
        stop_reason=stop_reason,
        iterations=int(opt.iter),
        history=history,
        weighted_rms=float(
            np.sqrt(np.mean(((predicted - inputs["observed"]) / inputs["sigma"]) ** 2))
        ),
        recovery=recovery,
        frozen_prior_unchanged=True,
        start_sha256=hashlib.sha256(start.tobytes()).hexdigest(),
        all_audited_cg_met=all(
            row["cg_raw"] is not None
            and row["cg_raw"] <= 1e-4
            and row["cg_scaled"] is not None
            and row["cg_scaled"] <= 1e-4
            for row in history[1:]
        ),
    )
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def run(output, scale):
    from scripts.benchmark_spherical_mvi import run as benchmark
    from terraworkbench_core import spherical_mvi

    output.mkdir(parents=True, exist_ok=False)
    budgets = dict(
        base_irls=40,
        base_outer=80,
        extended_irls=80,
        extended_outer=160,
        fixed_outer=80,
    )
    if scale == "quick":
        budgets = dict(
            base_irls=5,
            base_outer=20,
            extended_irls=10,
            extended_outer=40,
            fixed_outer=8,
        )
    protocol = dict(
        scale=scale,
        budgets=budgets,
        cg_maxiter=800,
        cg_rtol=1e-4,
        fixed_beta_factors=[0.5, 1.0, 2.0],
        fixed_gradient_reduction=1e-3,
        scope="All branches retained; truth only scores outputs; frozen weights are final adaptive weights, not a new L2 problem",
        commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        source_sha256={
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in [
                "scripts/benchmark_mvi_outer.py",
                "scripts/benchmark_spherical_mvi.py",
                "terraworkbench_core/spherical_mvi.py",
                "terraworkbench_core/inversion.py",
            ]
        },
    )
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    captured = []
    factory = spherical_mvi.safeguarded_irls_type

    def capture_factory():
        class Capture(factory()):
            def initialize(self):
                super().initialize()
                captured.append(self)

        return Capture

    with patch.object(spherical_mvi, "safeguarded_irls_type", capture_factory):
        base = benchmark(
            output / "adaptive40",
            scale,
            cg_maxiter=800,
            variants=["core_spherical"],
            spherical_iterations=budgets["base_outer"],
            irls_iterations=budgets["base_irls"],
            budget_reason="Predeclared outer stationarity and frozen-prior separation",
        )
    assert len(captured) == 1
    problem = captured[0].invProb
    start = problem.model.copy()
    beta = float(problem.beta)
    inputs = dict(np.load(output / "adaptive40" / "input.npz"))
    cases = {}
    for factor in protocol["fixed_beta_factors"]:
        label = "fixed_beta_" + str(factor)
        folder = output / label
        folder.mkdir()
        cases[label] = frozen_branch(
            problem,
            start,
            beta * factor,
            budgets["fixed_outer"],
            folder,
            inputs,
            None,
            None,
        )
        print(
            label,
            cases[label]["stop_reason"],
            cases[label]["weighted_rms"],
            cases[label]["recovery"]["model_relative_error"],
            flush=True,
        )
    extended = benchmark(
        output / "adaptive80",
        scale,
        cg_maxiter=800,
        variants=["core_spherical"],
        spherical_iterations=budgets["extended_outer"],
        irls_iterations=budgets["extended_irls"],
        budget_reason="Predeclared doubling of IRLS and outer budgets, not truth-score tuning",
    )
    # Zip containers have timestamps; compare actual input arrays instead.
    other = dict(np.load(output / "adaptive80" / "input.npz"))
    assert inputs.keys() == other.keys()
    assert all(np.array_equal(inputs[k], other[k]) for k in inputs)
    assert base["protocol"]["criteria"] == extended["protocol"]["criteria"]
    models = {name: np.load(output / name / "model.npz")["model"] for name in cases}
    volume = np.tile(inputs["volumes"], 3)
    center = models["fixed_beta_1.0"]
    differences = {
        name: float(
            np.linalg.norm(np.sqrt(volume) * (model - center))
            / max(np.linalg.norm(np.sqrt(volume) * center), 1e-300)
        )
        for name, model in models.items()
    }
    result = dict(
        state="complete",
        protocol=protocol,
        frozen=cases,
        beta_relative_model_differences=differences,
        adaptive40=base["cases"][0],
        adaptive80=extended["cases"][0],
    )
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", choices=["quick", "published"], default="quick")
    args = parser.parse_args()
    run(args.output, args.scale)
