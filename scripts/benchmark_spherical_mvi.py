"""Frozen staged MVI controls on authored and SimPEG-derived synthetic data.

See doi:10.1190/geo2019-0244.1. Native and Core share a deterministic Cartesian
initialization but use separate spherical solvers. Truth is only for scoring.
"""

import argparse
from datetime import datetime, timezone
import gc
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402


def native_spherical(mesh, active, xyz, observed, sigma, warm, protocol):
    from simpeg import (
        maps,
        utils,
        data,
        data_misfit,
        regularization,
        directives,
        optimization,
        inverse_problem,
        inversion,
    )
    from simpeg.potential_fields import magnetics

    n = int(active.sum())
    mapping = maps.SphericalSystem()
    survey = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(
            receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
            amplitude=50000.0,
            inclination=90.0,
            declination=0.0,
        )
    )
    sim = magnetics.simulation.Simulation3DIntegral(
        mesh,
        active_cells=active,
        survey=survey,
        chiMap=mapping,
        model_type="vector",
        engine="geoana",
        sensitivity_dtype=np.float64,
    )
    wires = maps.Wires(("a", n), ("t", n), ("p", n))
    terms = []
    for i, name in enumerate(("a", "t", "p")):
        term = regularization.Sparse(
            mesh,
            active_cells=active,
            mapping=getattr(wires, name),
            reference_model=np.zeros(3 * n),
            norms=protocol["amplitude_norms"]
            if i == 0
            else [2.0, *protocol["angle_norms"]],
            gradient_type="total",
        )
        if i:
            term.alpha_s = 0.0
            term.units = "radian"
        terms.append(term)
    reg = terms[0] + terms[1] + terms[2]
    misfit = data_misfit.L2DataMisfit(
        simulation=sim,
        data=data.Data(
            survey, dobs=observed, standard_deviation=np.full(len(xyz), sigma)
        ),
    )
    opt = optimization.ProjectedGNCG(
        maxIter=protocol["spherical_iterations"],
        lower=np.r_[np.zeros(n), np.full(n, -np.pi / 2), np.full(n, -np.inf)],
        upper=np.r_[
            np.full(n, protocol["amplitude_max"]),
            np.full(n, np.pi / 2),
            np.full(n, np.inf),
        ],
        maxIterLS=20,
        cg_maxiter=protocol["cg_maxiter"],
        cg_rtol=protocol["cg_rtol"],
        tolF=1e-6,
        tolX=1e-8,
        tolG=1e-6,
    )
    problem = inverse_problem.BaseInvProblem(
        misfit, reg, opt, beta=warm.diagnostics["final_beta"], init_bfgs=False
    )
    history = []

    class Trace(directives.InversionDirective):
        def endIter(self):
            history.append(
                dict(
                    iteration=int(self.opt.iter),
                    phi_d=float(self.invProb.phi_d),
                    phi_m=float(self.invProb.phi_m),
                    beta=float(self.invProb.beta),
                    cg_relative_residual=float(self.opt.cg_rel_resid),
                )
            )

    controls = [
        directives.SphericalUnitsWeights(amplitude=wires.a, angles=terms[1:]),
        directives.ProjectSphericalBounds(),
        directives.UpdateIRLS(
            max_irls_iterations=protocol["irls_iterations"],
            chifact_start=1.0,
            chifact_target=1.0,
            cooling_factor=2.0,
            cooling_rate=1,
        ),
        directives.UpdateSensitivityWeights(every_iteration=True),
        directives.UpdatePreconditioner(),
        Trace(),
    ]
    start = utils.mat_utils.cartesian2spherical(warm.model.reshape((n, 3), order="F"))
    model = inversion.BaseInversion(problem, directiveList=controls).run(start)
    return (
        mapping * model,
        sim.dpred(model),
        dict(
            iterations=int(opt.iter),
            final_beta=float(problem.beta),
            cg_relative_residual=float(opt.cg_rel_resid),
            definition="Native SDK spherical map and mapped-diagonal approximation",
            history=history,
        ),
    )


def run(
    output,
    scale,
    cg_maxiter=200,
    variants=None,
    spherical_iterations=40,
    irls_iterations=20,
    budget_reason=None,
    irls_update="adaptive",
):
    from scripts.benchmark_mvi_reference import fixture, mesh_edges, SOURCE
    from scripts.benchmark_voxel_recovery import CRITERIA
    from terraworkbench_core.inversion import run_potential_field_inversion
    from terraworkbench_core.recovery_metrics import model_recovery_metrics
    from terraworkbench_core._calibration import integer_budget

    integer_budget(cg_maxiter, "cg_maxiter")
    integer_budget(spherical_iterations, "spherical_iterations")
    integer_budget(irls_iterations, "irls_iterations")

    output.mkdir(parents=True, exist_ok=False)
    protocol = dict(
        schema_version=6,
        mvi_irls_update=irls_update,
        cartesian_initialization="componentwise_l2",
        sensitivity_prior="component_approximation",
        directive_order=[
            "angle_scale",
            "canonical_projection",
            "IRLS",
            "sensitivity",
            "preconditioner",
        ],
        source=SOURCE,
        paper="https://doi.org/10.1190/geo2019-0244.1",
        scale=scale,
        seed=7112,
        cartesian_iterations=20,
        spherical_iterations=int(spherical_iterations),
        irls_iterations=int(irls_iterations),
        budget_adjustment_reason=budget_reason,
        cg_maxiter=cg_maxiter,
        cg_rtol=1e-4,
        amplitude_norms=[0.0, 1.0, 1.0, 1.0],
        angle_norms=[1.0, 1.0, 1.0],
        amplitude_max=10.0,
        criteria=CRITERIA,
        data_wrms_max=2.0,
        variants=[
            "cartesian_initialization",
            "native_spherical",
            "core_spherical",
            "core_spherical_support_oracle",
        ],
        truth_in_fit=["core_spherical_support_oracle"],
        scope="Native and Core share Cartesian initialization and the component-approximation sensitivity prior. Core uses an exact zero map and full mapped diagonal for the solver. Fixed choices before generating data; no parameter tuning from truth.",
    )
    if variants is not None:
        if (
            not variants
            or len(set(variants)) != len(variants)
            or not set(variants) <= set(protocol["variants"])
        ):
            raise ValueError("Select unique declared benchmark variants")
        protocol["variants"] = list(variants)
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    mesh, active, xyz, observed, sigma, truth, support, clean = fixture(scale)
    n = int(active.sum())
    edges = mesh_edges(mesh, active)
    np.savez_compressed(
        output / "input.npz",
        xyz=xyz,
        observed=observed,
        sigma=sigma,
        truth=truth,
        centers=mesh.cell_centers[active],
        volumes=mesh.cell_volumes[active],
        connectivity_edges=edges,
        clean=clean,
    )
    common = dict(
        cell_xy=5.0 if scale == "published" else 100.0,
        cell_z=5.0 if scale == "published" else 100.0,
        depth=100.0 if scale == "published" else 400.0,
        mesh=mesh,
        active_cells=active,
        max_cells=250000,
        field_amplitude=50000.0,
        field_inclination=90.0,
        field_declination=0.0,
        beta0_ratio=10.0,
        beta_seed=0,
        cg_maxiter=protocol["cg_maxiter"],
        cg_rtol=protocol["cg_rtol"],
        sensitivity_dtype="float64",
        sensitivity_mode="ram",
        reference_model=np.zeros((n, 3)),
        starting_model=np.full((n, 3), 1e-4),
    )
    warm = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), sigma),
        iterations=protocol["cartesian_iterations"],
        target_chi=2.0,
        lower=-protocol["amplitude_max"],
        upper=protocol["amplitude_max"],
        mvi_regularization="componentwise",
        **common,
    )
    records = []
    for variant in protocol["variants"]:
        if variant == "cartesian_initialization":
            result = warm
            model, predicted, diagnostics = (
                result.model,
                result.predicted,
                result.diagnostics,
            )
            history = result.history
        elif variant == "native_spherical":
            model, predicted, diagnostics = native_spherical(
                mesh, active, xyz, observed, sigma, warm, protocol
            )
            history = diagnostics.pop("history")
        else:
            chosen = dict(common)
            cap = protocol["amplitude_max"]
            if variant.endswith("oracle"):
                cap = np.where(support, cap, 0.0)
                chosen["starting_model"] = np.where(
                    support[:, None], 1e-4, 0.0
                ) * np.ones((n, 3))
            result = run_potential_field_inversion(
                "mvi",
                xyz,
                observed,
                np.full(len(xyz), sigma),
                mvi_parameterization="spherical",
                mvi_irls_update=irls_update,
                mvi_cartesian_iterations=protocol["cartesian_iterations"],
                mvi_amplitude_max=cap,
                mvi_angle_norms=protocol["angle_norms"],
                iterations=protocol["spherical_iterations"],
                irls_iterations=protocol["irls_iterations"],
                regularization_norms=protocol["amplitude_norms"],
                **chosen,
            )
            model, predicted, diagnostics = (
                result.model,
                result.predicted,
                result.diagnostics,
            )
            history = result.history
        np.savez_compressed(
            output / (variant + ".npz"), model=model, predicted=predicted
        )
        recovery = model_recovery_metrics(
            mesh.cell_centers[active],
            mesh.cell_volumes[active],
            model.reshape((n, 3), order="F"),
            truth,
            criteria=CRITERIA,
            connectivity_edges=edges,
            vector=True,
            max_cells=250000,
            max_links=2000000,
        )
        wrms = float(np.sqrt(np.mean(((predicted - observed) / sigma) ** 2)))
        cg_residual = diagnostics.get("cg_relative_residual")
        item = dict(
            variant=variant,
            truth_in_fit=variant.endswith("oracle"),
            weighted_rms=wrms,
            recovery=recovery,
            diagnostics=diagnostics,
            history=history,
            numerical_passed=bool(
                cg_residual is not None
                and np.isfinite(cg_residual)
                and cg_residual <= protocol["cg_rtol"]
            ),
            data_fit_passed=bool(wrms <= protocol["data_wrms_max"]),
        )
        records.append(item)
        (output / "results.partial.json").write_text(
            json.dumps(records, indent=2) + "\n"
        )
        print(
            json.dumps(
                dict(
                    variant=variant,
                    wrms=wrms,
                    model_error=recovery["model_relative_error"],
                    direction_errors=[
                        r["direction_error_deg"] for r in recovery["body_metrics"]
                    ],
                    recovery_passed=recovery["recovery_passed"],
                )
            ),
            flush=True,
        )
        gc.collect()
    result = dict(
        state="complete",
        utc=datetime.now(timezone.utc).isoformat(),
        commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        repository_dirty=repository_provenance(ROOT)["dirty"],
        protocol=protocol,
        versions={
            p: version(p)
            for p in ["numpy", "scipy", "simpeg", "discretize", "choclo", "geoana"]
        },
        mesh_cells=mesh.nC,
        active_cells=n,
        observations=len(xyz),
        cases=records,
        source_sha256={
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in [
                "terraworkbench_core/inversion.py",
                "terraworkbench_core/spherical_mvi.py",
                "terraworkbench_core/recovery_metrics.py",
                "scripts/benchmark_spherical_mvi.py",
                "scripts/benchmark_mvi_reference.py",
                "scripts/benchmark_voxel_recovery.py",
            ]
        },
        input_sha256=hashlib.sha256((output / "input.npz").read_bytes()).hexdigest(),
    )
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", choices=["quick", "published"], default="quick")
    parser.add_argument("--cg-maxiter", type=int, default=200)
    parser.add_argument("--outer-iterations", type=int, default=40)
    parser.add_argument("--irls-iterations", type=int, default=20)
    parser.add_argument("--budget-reason")
    parser.add_argument(
        "--irls-update", choices=["adaptive", "lagged"], default="adaptive"
    )
    parser.add_argument("--variants", nargs="+")
    args = parser.parse_args()
    preexisting = args.output.exists()
    try:
        run(
            args.output,
            args.scale,
            args.cg_maxiter,
            args.variants,
            args.outer_iterations,
            args.irls_iterations,
            args.budget_reason,
            args.irls_update,
        )
    except Exception as error:
        if not preexisting and args.output.is_dir():
            (args.output / "failure.json").write_text(
                json.dumps(dict(state="failed", error=repr(error)), indent=2)
            )
        raise
