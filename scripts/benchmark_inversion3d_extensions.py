"""Independent 3-D fields, public joint artifacts and scalable linear audits.

Only authored geometry and pinned public synthetic SimPEG tutorial inputs.
No plots, private surveys or downloaded executable code. Preserve failed runs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402


def campaign(cache, output, section="all"):
    from scripts.benchmark_public_inversion import inputs, PINS
    from scripts.validate_inversion_campaign import direction, volume_reference, forward
    from terraworkbench_core.inversion import _mesh_from_data, run_inversion_workflow
    from terraworkbench_core.inversion_workflows import run_joint_inversion_workflow
    from terraworkbench_core.inversion_diagnostics import linear_resolution
    from terraworkbench_core.matrix_free_resolution import (
        stochastic_linear_resolution,
        linear_point_spread,
    )

    output.mkdir(parents=True, exist_ok=False)
    report = dict(
        state="running",
        utc=datetime.now(timezone.utc).isoformat(),
        seed=920,
        git_head=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        git_dirty=repository_provenance(ROOT)["dirty"],
        platform=platform.platform(),
        versions={
            name: version(name)
            for name in (
                "numpy",
                "scipy",
                "simpeg",
                "discretize",
                "choclo",
                "harmonica",
            )
        },
        source_sha256={
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "terraworkbench_core").glob("*.py")
        },
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        public_sources={
            name: dict(url=pin[0], sha256=pin[1]) for name, pin in PINS.items()
        },
        cases={},
        limits=[
            "Published dataset is synthetic, not a field survey. Raw inputs are not redistributed.",
            "Voxel data fit and independent prediction do not imply unique property/body/vector recovery.",
            "Linear Gaussian diagnostics condition on fixed noise, forward, beta and regularization; no nonlinear/IRLS/bound posterior claim.",
        ],
    )

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    def record(name, values):
        report["cases"][name] = values
        save()
        print(name, values.get("status"), flush=True)

    save()
    try:
        if section in ("all", "synthetic"):
            axis = np.arange(-300.0, 301.0, 100.0)
            x, y = np.meshgrid(axis, axis)
            xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
            hx, hy = np.meshgrid(
                np.arange(-250.0, 251.0, 100.0), np.arange(-250.0, 251.0, 100.0)
            )
            holdout = np.c_[hx.ravel(), hy.ravel(), np.full(hx.size, 120.0)]
            topo = np.array(
                [
                    [-500.0, -500.0, 0.0],
                    [-500.0, 500.0, 0.0],
                    [500.0, -500.0, 0.0],
                    [500.0, 500.0, 0.0],
                ]
            )
            mesh, active = _mesh_from_data(xyz, 100.0, 100.0, 400.0, 1, topography=topo)
            centers = mesh.cell_centers[active]
            body = (
                (abs(centers[:, 0]) < 100)
                & (abs(centers[:, 1]) < 100)
                & (centers[:, 2] > -300)
                & (centers[:, 2] < -100)
            )
            settings = dict(
                cell_xy=100.0,
                cell_z=100.0,
                depth=400.0,
                mesh=mesh,
                active_cells=active,
                iterations=60,
                cg_maxiter=200,
                cg_rtol=1e-4,
                field_inclination=60.0,
                field_declination=25.0,
            )
            for kind in ("gravity", "susceptibility", "mvi"):
                orientations = (
                    ((25.0, -35.0), (-35.0, 135.0))
                    if kind == "mvi"
                    else ((60.0, 25.0),)
                )
                for inc, dec in orientations:
                    for noise_scale in (1.0, 2.0):
                        name = f"{kind}_{inc}_{dec}_noise{noise_scale}"
                        sigma = (0.002 if kind == "gravity" else 0.3) * noise_scale
                        index = 0 if kind == "gravity" else 1
                        observed = volume_reference(xyz, direction(inc, dec))[index]
                        observed = observed + sigma * np.random.default_rng(920).normal(
                            size=len(observed)
                        )
                        check = volume_reference(holdout, direction(inc, dec))[index]
                        truth = body * (0.4 if kind == "gravity" else 0.025)
                        if kind == "mvi":
                            truth = (truth[:, None] * direction(inc, dec)).reshape(
                                -1, order="F"
                            )
                        result = run_inversion_workflow(
                            kind,
                            xyz,
                            observed,
                            np.full(len(xyz), sigma),
                            output_directory=output / name,
                            **settings,
                        )
                        hold_pred = forward(mesh, active, holdout, result.model, kind)
                        hold_rms = float(
                            np.sqrt(np.mean(((hold_pred - check) / sigma) ** 2))
                        )
                        metrics = dict(
                            status_scope="Data prediction only; not a geological recovery gate",
                            recovery_scope="Use benchmark_voxel_recovery.py for explicit multi-geometry recovery criteria",
                            status="passed"
                            if result.diagnostics["weighted_rms"] < 2.0
                            and hold_rms < 3.0
                            else "failed",
                            kind=kind,
                            magnetization_direction_deg=[inc, dec],
                            noise_std=sigma,
                            diagnostics=result.diagnostics,
                            history=result.history,
                            holdout_rms=hold_rms,
                            cell_model_relative_l2=float(
                                np.linalg.norm(result.model - truth)
                                / np.linalg.norm(truth)
                            ),
                            independent_field="Gauss-Legendre volume quadrature for observations; Geoana analytic prisms for withheld predictions",
                            cell_count=int(active.sum()),
                        )
                        if kind == "mvi":
                            vector = np.asarray(result.model).reshape(
                                (-1, 3), order="F"
                            )
                            total = (vector * mesh.cell_volumes[active, None]).sum(
                                axis=0
                            )
                            metrics["integrated_vector_angular_error_deg"] = float(
                                np.rad2deg(
                                    np.arccos(
                                        np.clip(
                                            total
                                            @ direction(inc, dec)
                                            / np.linalg.norm(total),
                                            -1.0,
                                            1.0,
                                        )
                                    )
                                )
                            )
                        record(name, metrics)
                        # Same objective/inputs with no dense sensitivity storage.
                        # Compare finite 3-step trajectories, not physical uniqueness.
                        if noise_scale == 1.0 and (inc, dec) == orientations[0]:
                            short_opts = dict(settings, iterations=3)
                            stored = run_inversion_workflow(
                                kind,
                                xyz,
                                observed,
                                np.full(len(xyz), sigma),
                                output_directory=output / (name + "_stored_short"),
                                **short_opts,
                            )
                            free = run_inversion_workflow(
                                kind,
                                xyz,
                                observed,
                                np.full(len(xyz), sigma),
                                output_directory=output / (name + "_free_short"),
                                sensitivity_mode="matrix_free",
                                max_sensitivity_bytes=0,
                                **short_opts,
                            )
                            delta = float(
                                np.linalg.norm(free.predicted - stored.predicted)
                                / max(np.linalg.norm(stored.predicted), 1e-30)
                            )
                            record(
                                kind + "_matrix_free",
                                dict(
                                    status="passed" if delta < 1e-5 else "failed",
                                    prediction_relative_difference=delta,
                                    stored_diagnostics=stored.diagnostics,
                                    matrix_free_diagnostics=free.diagnostics,
                                    scope="Three-iteration storage/operator integration equivalence, not a converged inversion",
                                ),
                            )
            from scipy.constants import mu_0
            from terraworkbench_core.prism_inversion import (
                fit_prism_density,
                fit_prism_magnetization,
            )

            prism = [[-100.0, 100.0, -100.0, 100.0, -300.0, -100.0]]
            known_density = fit_prism_density(
                xyz,
                prism,
                volume_reference(xyz, direction(60.0, 25.0))[0],
                np.full(len(xyz), 0.002),
            )
            controls = []
            for inc, dec in ((25.0, -35.0), (-35.0, 135.0), (0.0, 90.0)):
                magnetic_truth = 0.025 * 50000e-9 / mu_0 * direction(inc, dec)
                clean = volume_reference(xyz, direction(inc, dec))[1]
                for scale in (0.0, 0.5, 1.0, 2.0):
                    declared_std = 0.3 * max(scale, 0.5)
                    observed = clean + scale * 0.3 * np.random.default_rng(920).normal(
                        size=len(clean)
                    )
                    fit = fit_prism_magnetization(
                        xyz,
                        prism,
                        observed,
                        np.full(len(xyz), declared_std),
                        inclination=60.0,
                        declination=25.0,
                    )
                    vector = fit["magnetization_a_m"][0]
                    error = float(
                        np.linalg.norm(vector - magnetic_truth)
                        / np.linalg.norm(magnetic_truth)
                    )
                    controls.append(
                        dict(
                            direction_deg=[inc, dec],
                            noise_scale=scale,
                            generated_noise_std_nt=scale * 0.3,
                            declared_data_std_nt=declared_std,
                            magnetization_a_m=vector.tolist(),
                            relative_model_error=error,
                            angular_error_deg=float(
                                np.rad2deg(
                                    np.arccos(
                                        np.clip(
                                            vector
                                            @ magnetic_truth
                                            / (
                                                np.linalg.norm(vector)
                                                * np.linalg.norm(magnetic_truth)
                                            ),
                                            -1.0,
                                            1.0,
                                        )
                                    )
                                )
                            ),
                            parameter_covariance=fit["parameter_covariance"].tolist(),
                            diagnostics=fit["diagnostics"],
                            noiseless_recovery_met=error < 1e-5 if scale == 0 else None,
                        )
                    )
            record(
                "known_geometry_properties",
                dict(
                    status="passed"
                    if abs(known_density["density_kg_m3"][0] - 400.0) < 0.001
                    and all(v["noiseless_recovery_met"] is not False for v in controls)
                    else "failed",
                    density_kg_m3=known_density["density_kg_m3"].tolist(),
                    density_covariance=known_density["parameter_covariance"].tolist(),
                    magnetic_controls=controls,
                    scope="Harmonica-based Core property inversion, independent volume-integral data; exact known cube geometry, not free-voxel recovery",
                ),
            )
        if section in ("all", "public"):
            folder, mesh, active, grav, mag, errors, truth = inputs(cache)
            joint = run_joint_inversion_workflow(
                grav[:, :3],
                grav[:, -1],
                errors[0],
                mag[:, :3],
                mag[:, -1],
                errors[1],
                output_directory=output / "public_joint",
                cell_xy=5.0,
                cell_z=5.0,
                depth=100.0,
                mesh=mesh,
                active_cells=active,
                iterations=3,
                cg_maxiter=40,
                starting_density=1e-6,
                starting_susceptibility=1e-6,
                reference_density=1e-6,
                reference_susceptibility=1e-6,
                density_bounds=(-2.0, 2.0),
                susceptibility_bounds=(-2.0, 2.0),
                field_inclination=90.0,
                coupling_weight=2e12,
                sensitivity_dtype="float64",
                max_sensitivity_bytes=512 * 1024**2,
            )
            manifest = json.loads((output / "public_joint/run.json").read_text())
            record(
                "public_joint_workflow",
                dict(
                    status="passed"
                    if manifest["state"] == "complete"
                    and all(
                        (output / "public_joint" / name).is_file()
                        for name in manifest["artifacts"]
                    )
                    else "failed",
                    numerical_status=manifest["numerical_status"],
                    diagnostics=joint.diagnostics,
                    history=joint.history,
                    input_sha256=manifest["input_sha256"],
                    scope="Exact public mesh/inputs; deliberately three iterations; checks artifact completion and honest nonconvergence, not full recovery",
                    model_errors={
                        name: float(
                            np.linalg.norm(values - truth[name])
                            / np.linalg.norm(truth[name])
                        )
                        for name, values in (
                            ("density", joint.density),
                            ("susceptibility", joint.susceptibility),
                        )
                    },
                ),
            )
            # Diagnose a declared reduced parameterization on the published mesh,
            # instead of claiming a 47,860-cell dense covariance is practical.
            from simpeg import maps
            from simpeg.potential_fields import gravity
            from scipy import sparse

            centers = mesh.cell_centers[active]
            labels = np.zeros(len(centers), int)
            for axis in range(3):
                cut = np.quantile(centers[:, axis], 0.5)
                labels += (centers[:, axis] > cut).astype(int) * (2**axis)
            count = int(labels.max() + 1)
            mapping = sparse.csr_matrix(
                (np.ones(len(labels)), (np.arange(len(labels)), labels)),
                shape=(len(labels), count),
            )
            survey = gravity.survey.Survey(
                gravity.sources.SourceField(
                    receiver_list=[
                        gravity.receivers.Point(grav[:, :3], components="gz")
                    ]
                )
            )
            sim = gravity.simulation.Simulation3DIntegral(
                mesh,
                survey=survey,
                rhoMap=maps.IdentityMap(nP=len(labels)),
                active_cells=active,
                engine="choclo",
                sensitivity_dtype=np.float64,
            )
            g = np.asarray((mapping.T @ sim.getJ(np.zeros(len(labels))).T).T)
            reg = np.eye(count) / 0.4
            exact = linear_resolution(g, errors[0], reg, beta=1.0)
            basis = stochastic_linear_resolution(
                g,
                errors[0],
                reg,
                beta=1.0,
                method="basis",
                probe_count=count,
                cg_rtol=1e-9,
            )
            samples = stochastic_linear_resolution(
                g, errors[0], reg, beta=1.0, probe_count=128, seed=920, cg_rtol=1e-9
            )
            spread = linear_point_spread(
                g, errors[0], reg, [0, count - 1], beta=1.0, cg_rtol=1e-9
            )
            err = float(
                np.max(
                    abs(
                        basis["posterior_variance_estimate"]
                        - np.diag(exact["posterior_covariance"])
                    )
                )
            )
            record(
                "public_linear_resolution",
                dict(
                    status="passed"
                    if np.allclose(
                        basis["posterior_variance_estimate"],
                        np.diag(exact["posterior_covariance"]),
                        rtol=1e-6,
                        atol=1e-9,
                    )
                    and np.allclose(
                        spread["resolution_columns"],
                        exact["resolution"][:, [0, count - 1]],
                        rtol=1e-6,
                        atol=1e-8,
                    )
                    else "failed",
                    parameterization="Eight fixed spatial octants of original active mesh; uniform g/cm3 coefficients, not free voxel covariance",
                    parameters=count,
                    observations=len(grav),
                    beta=1.0,
                    prior_scale_g_cm3=0.4,
                    basis_max_variance_error=err,
                    exact_diagonal=np.diag(exact["posterior_covariance"]).tolist(),
                    stochastic_diagonal=samples["posterior_variance_estimate"].tolist(),
                    probing_standard_error=samples[
                        "probing_standard_error_variance"
                    ].tolist(),
                    negative_estimates=samples["negative_variance_estimates"].tolist(),
                    effective_parameters_exact=exact["effective_parameters"],
                    effective_parameters_estimate=samples[
                        "effective_parameters_estimate"
                    ],
                    cg_history=basis["cg_history"],
                ),
            )
        from scipy import sparse
        from scipy.sparse.linalg import LinearOperator

        n = 100_000
        diagonal = np.linspace(0.5, 2.0, n)
        operator = LinearOperator(
            (n, n),
            matvec=lambda v: diagonal * v,
            rmatvec=lambda v: diagonal * v,
            dtype=float,
        )
        large = stochastic_linear_resolution(
            operator,
            np.ones(n),
            sparse.eye(n),
            beta=3.0,
            probe_count=2,
            precision_diagonal=diagonal**2 + 3.0,
            max_elements=5_000_000,
        )
        error = float(
            np.max(abs(large["posterior_variance_estimate"] - 1 / (diagonal**2 + 3.0)))
        )
        record(
            "large_operator",
            dict(
                status="passed" if error < 1e-12 else "failed",
                parameters=n,
                max_variance_error=error,
                operator_applications=large["operator_applications"],
                hypothetical_dense_covariance_bytes=n * n * 8,
                cg_history=large["cg_history"],
                scope="Analytic diagonal precision stress test; not a geophysical regional sensitivity/runtime benchmark",
            ),
        )
        report["state"] = (
            "complete"
            if all(v["status"] == "passed" for v in report["cases"].values())
            else "failed"
        )
    except Exception as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--section", choices=("all", "synthetic", "public"), default="all"
    )
    args = parser.parse_args()
    report = campaign(args.cache, args.output, args.section)
    if report["state"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
