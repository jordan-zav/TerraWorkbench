"""Capture a failed MVI solve and compare frozen objectives without truth tuning."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def linear_reference(opt, production, budgets=(800, 3200)):
    """Use independent SciPy recurrences on the identical inactive quadratic."""
    from scipy.sparse.linalg import LinearOperator, cg, minres

    free = np.flatnonzero(~opt.activeSet(opt.xc))
    inverse = np.asarray(opt.approxHinv.diagonal())
    root = np.sqrt(inverse[free])
    rhs = -opt.g[free]
    hessian = opt.H

    def full(v):
        value = np.zeros_like(opt.g)
        value[free] = v
        return value

    def product(v):
        return np.asarray(hessian @ full(v))[free]

    def scaled(v):
        return root * product(root * v)

    operator = LinearOperator((len(free), len(free)), matvec=scaled, dtype=float)
    b = root * rhs
    raw0, scaled0 = np.linalg.norm(rhs), np.linalg.norm(b)
    if not raw0 or not scaled0:
        raise ValueError("Reference capture needs a nonzero inactive gradient")

    def metrics(step):
        hp = product(step)
        residual = hp - rhs
        raw = float(np.linalg.norm(residual) / raw0)
        energy = float(np.linalg.norm(root * residual) / scaled0)
        return dict(
            raw_relative_residual=raw,
            scaled_relative_residual=energy,
            both_tolerances_met=bool(raw <= opt.cg_rtol and energy <= opt.cg_rtol),
            quadratic_objective=float(0.5 * step @ hp - rhs @ step),
        )

    rng = np.random.default_rng(9607)
    probes = []
    for _ in range(3):
        u, v = rng.normal(size=(2, len(free)))
        hu, hv = scaled(u), scaled(v)
        denominator = max(abs(u @ hv), abs(v @ hu), np.finfo(float).tiny)
        probes.append(
            dict(
                relative_symmetry_error=float(abs(u @ hv - v @ hu) / denominator),
                scaled_rayleigh_quotient=float(u @ hu / (u @ u)),
            )
        )
    rows = [
        dict(
            solver="core_pcg", iterations=int(opt.cg_count), **metrics(production[free])
        )
    ]
    for method, solver in [("scipy_cg", cg), ("scipy_minres", minres)]:
        for budget in budgets:
            count = 0

            def callback(_):
                nonlocal count
                count += 1
                if count % 400 == 0:
                    print(method, budget, count, flush=True)

            kwargs = dict(rtol=1e-10, maxiter=budget, callback=callback)
            if method == "scipy_cg":
                kwargs["atol"] = 0.0
            solution, info = solver(operator, b, **kwargs)
            step = root * solution
            row = dict(
                solver=method,
                budget=int(budget),
                iterations=count,
                scipy_info=int(info),
                **metrics(step),
            )
            rows.append(row)
            print(json.dumps(row), flush=True)
    return dict(
        free_parameters=len(free),
        production_rtol=float(opt.cg_rtol),
        scipy_internal_rtol=1e-10,
        symmetry_probes=probes,
        cases=rows,
    )


def nonlinear_reference(problem, start, metric, lower, upper, budget=1000):
    """Minimize the same frozen objective in fixed Jacobi-scaled coordinates."""
    from scipy.optimize import minimize

    root = np.sqrt(metric)
    lo, hi = (lower - start) * root, (upper - start) * root
    history = []
    cached = None

    def evaluate(y):
        nonlocal cached
        if cached is None or not np.array_equal(cached[0], y):
            value, gradient = problem.evalFunction(
                start + y / root, return_g=True, return_H=False
            )
            cached = (y.copy(), float(value), np.asarray(gradient) / root)
        return cached[1], cached[2]

    def measure(y):
        value, gradient = evaluate(y)
        projected = np.clip(y - gradient, lo, hi) - y
        return dict(
            iteration=len(history),
            objective=value,
            projected_gradient_metric=float(np.linalg.norm(projected)),
        )

    y0 = np.zeros_like(start)
    initial = measure(y0)
    threshold = max(1e-3 * initial["projected_gradient_metric"], 1e-12)
    history.append(initial)
    # Independent directional differences audit the shared analytic gradient.
    _, g0 = evaluate(y0)
    direction = np.clip(-g0, lo, hi)
    direction /= max(np.linalg.norm(direction), 1.0)
    checks = []
    for epsilon in (1e-3, 1e-4, 1e-5):
        yp = np.clip(epsilon * direction, lo, hi)
        actual = evaluate(yp)[0] - initial["objective"]
        expected = float(g0 @ yp)
        checks.append(
            dict(
                epsilon=epsilon,
                relative_directional_error=float(
                    abs(actual - expected) / max(abs(expected), 1e-300)
                ),
            )
        )
    final_y = y0.copy()

    class Stationary(Exception):
        pass

    def callback(y):
        nonlocal final_y
        final_y = y.copy()
        row = measure(y)
        history.append(row)
        if row["iteration"] % 50 == 0:
            print("L-BFGS-B", json.dumps(row), flush=True)
        if row["projected_gradient_metric"] <= threshold:
            raise Stationary

    try:
        answer = minimize(
            evaluate,
            y0,
            jac=True,
            method="L-BFGS-B",
            bounds=list(zip(lo, hi)),
            callback=callback,
            options=dict(
                maxiter=budget,
                maxfun=4 * budget,
                maxls=40,
                maxcor=20,
                ftol=0.0,
                gtol=0.0,
            ),
        )
        final_y = answer.x
        reason = str(answer.message)
        scipy_success = bool(answer.success)
    except Stationary:
        reason, scipy_success = "declared_projected_gradient_reduction", None
    final = measure(final_y)
    final["iteration"] = history[-1]["iteration"]
    return start + final_y / root, dict(
        solver="scipy_lbfgsb",
        budget=budget,
        scipy_success=scipy_success,
        stop_reason=reason,
        threshold=threshold,
        stationarity_passed=bool(final["projected_gradient_metric"] <= threshold),
        relative_projected_gradient=final["projected_gradient_metric"]
        / max(initial["projected_gradient_metric"], 1e-300),
        final=final,
        history=history,
        directional_checks=checks,
    )


def run(output, scale="published", capture="first-failure"):
    from scripts.benchmark_spherical_mvi import run as benchmark
    from scripts.benchmark_mvi_outer import frozen_branch, prior_digest
    from terraworkbench_core import spherical_mvi

    output.mkdir(parents=True, exist_ok=False)
    paths = list((ROOT / "terraworkbench_core").glob("*.py")) + [
        ROOT / "scripts/benchmark_mvi_solver_reference.py",
        ROOT / "scripts/benchmark_spherical_mvi.py",
        ROOT / "scripts/benchmark_mvi_outer.py",
    ]
    protocol = dict(
        id="TW-MVI-SOLVER-REFERENCE-1",
        scale=scale,
        capture=capture,
        created_utc=datetime.now(timezone.utc).isoformat(),
        base_commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        provenance_scope="Standalone solver comparison; study freeze retained in development archive",
        source_sha256_lf={p.relative_to(ROOT).as_posix(): digest(p) for p in paths},
        adaptive=dict(cg_maxiter=800, irls_iterations=80, outer_iterations=160),
        linear_budgets=[800, 3200],
        scipy_linear_rtol=1e-10,
        frozen_core_outer=80,
        frozen_scipy_outer=1000,
        projected_gradient_reduction=1e-3,
        scope="Numerical comparison, no geological recovery acceptance or parameter tuning from truth",
    )
    dump(output / "protocol.json", protocol)
    original = spherical_mvi.spherical_pcg
    captured = False

    class CaptureComplete(Exception):
        pass

    def inspect(opt, cancel_callback=None):
        nonlocal captured
        step = original(opt, cancel_callback)
        failed = (
            opt.cg_true_rel_resid > opt.cg_rtol or opt.cg_scaled_rel_resid > opt.cg_rtol
        )
        print(
            "core_cg",
            int(opt.iter),
            opt.cg_count,
            opt.cg_true_rel_resid,
            opt.cg_scaled_rel_resid,
            flush=True,
        )
        if captured or (capture == "first-failure" and not failed):
            return step
        captured = True
        problem = opt.parent
        start = opt.xc.copy()
        before = prior_digest(problem.reg)
        beta = float(problem.beta)
        inputs = dict(np.load(output / "adaptive" / "input.npz"))
        linear = linear_reference(opt, step, protocol["linear_budgets"])
        dump(output / "linear.json", linear)
        folder = output / "frozen_core"
        folder.mkdir()
        # Remove the capture hook while continuing the frozen Core problem.
        with patch.object(spherical_mvi, "spherical_pcg", original):
            core = frozen_branch(
                problem,
                start,
                beta,
                protocol["frozen_core_outer"],
                folder,
                inputs,
                None,
                None,
            )
        metric = np.load(folder / "model.npz")["metric"]
        assert prior_digest(problem.reg) == before
        model, reference = nonlinear_reference(
            problem,
            start,
            metric,
            opt.lower.copy(),
            opt.upper.copy(),
            protocol["frozen_scipy_outer"],
        )
        assert prior_digest(problem.reg) == before and float(problem.beta) == beta
        np.testing.assert_allclose(
            reference["history"][0]["objective"],
            core["history"][0]["objective"],
            rtol=1e-12,
            atol=1e-12,
        )
        assert all(
            digest(ROOT / name) == expected
            for name, expected in protocol["source_sha256_lf"].items()
        )
        np.savez_compressed(
            output / "reference.npz",
            start=start,
            model=model,
            metric=metric,
            lower=opt.lower,
            upper=opt.upper,
        )
        dump(output / "nonlinear.json", reference)
        record = dict(
            state="complete",
            protocol=protocol,
            benchmark_intentionally_stopped_after_capture=True,
            capture=dict(
                outer_iteration=int(opt.iter),
                inner_budget=int(opt.cg_maxiter),
                failed=bool(failed),
                prior_sha256=before,
                beta=beta,
                start_sha256=hashlib.sha256(start.tobytes()).hexdigest(),
            ),
            versions={
                name: version(name)
                for name in ["numpy", "scipy", "simpeg", "discretize"]
            },
            environment=dict(system=platform.system(), release=platform.release(),
                             python=platform.python_version()),
            linear=linear,
            frozen_core=core,
            frozen_scipy=reference,
        )
        dump(output / "results.json", record)
        raise CaptureComplete

    try:
        with patch.object(spherical_mvi, "spherical_pcg", inspect):
            benchmark(
                output / "adaptive",
                scale,
                cg_maxiter=800,
                variants=["core_spherical"],
                spherical_iterations=160,
                irls_iterations=80,
                budget_reason="Capture first failed linear solve, compare independent frozen numerical objectives",
            )
    except CaptureComplete:
        return
    raise RuntimeError(
        "No matching solve captured; do not claim the failed case was tested"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", choices=["quick", "published"], default="published")
    parser.add_argument(
        "--capture", choices=["first", "first-failure"], default="first-failure"
    )
    args = parser.parse_args()
    preexisting = args.output.exists()
    try:
        run(args.output, args.scale, args.capture)
    except Exception as error:
        if not preexisting and args.output.is_dir():
            dump(args.output / "failure.json", dict(state="failed", error=repr(error)))
        raise
