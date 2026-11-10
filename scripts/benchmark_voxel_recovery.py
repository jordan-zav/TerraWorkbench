"""Predeclared recovery gates across shapes, noise and explicit prior strategies.

Independent volume quadrature supplies fields. Truth enters scoring and an
explicitly labelled oracle only. No default is tuned from held-out truth.
Numerical execution and geological recovery have separate report statuses.
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
from numpy.polynomial.legendre import leggauss
from scipy.constants import G, mu_0

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402

CRITERIA = dict(
    location_tolerance_m=100.0,
    volume_relative_tolerance=0.35,
    contrast_relative_tolerance=0.35,
    support_dice_min=0.6,
    direction_tolerance_deg=15.0,
    model_relative_tolerance=0.5,
)
FIXTURES = {
    "shallow_cube": [[-100.0, 100.0, -100.0, 100.0, -300.0, -100.0]],
    "deep_cube": [[-100.0, 100.0, -100.0, 100.0, -500.0, -300.0]],
    "shifted_cube": [[100.0, 300.0, -100.0, 100.0, -300.0, -100.0]],
    "thin_body": [[-200.0, 200.0, -100.0, 100.0, -300.0, -200.0]],
    "two_bodies": [
        [-300.0, -100.0, -100.0, 100.0, -300.0, -100.0],
        [100.0, 300.0, -100.0, 100.0, -400.0, -200.0],
    ],
}
STRATEGIES = {
    "baseline_l2": dict(
        prior="zero reference, default L2/sensitivity weighting", truth_in_fit=False
    ),
    "compact": dict(
        prior="positive scalar properties and [0,1,1,1] norms; signed Cartesian MVI",
        truth_in_fit=False,
    ),
    "soft_roi": dict(
        prior="common partial ROI and positive scalar bounds; outside penalty 10; MVI component smoothness",
        truth_in_fit=False,
    ),
    "hard_roi": dict(
        prior="common partial ROI, fixed outside background zero; MVI component smoothness",
        truth_in_fit=False,
    ),
    "oracle_known_geometry": dict(
        prior="exact true prism geometry, uniform properties per body; GLS control",
        truth_in_fit=True,
    ),
    "wrong_roi_control": dict(
        prior="deliberately incorrect east-side hard support",
        truth_in_fit=False,
        expected_negative=True,
    ),
}


def direction(inc, dec):
    i, d = np.deg2rad([inc, dec])
    return np.array([np.cos(i) * np.sin(d), np.cos(i) * np.cos(d), -np.sin(i)])


def integrated_fields(xyz, prisms, density, magnetization, order=12):
    """Direct Newton/dipole volume integration, separate from analytic kernels."""
    nodes, w = leggauss(order)
    gz = np.zeros(len(xyz))
    b = np.zeros((len(xyz), 3))
    for p, rho, mag in zip(prisms, density, magnetization):
        lengths = (p[1::2] - p[::2]) / 2
        center = (p[1::2] + p[::2]) / 2
        axes = [nodes * lengths[i] + center[i] for i in range(3)]
        x, y, z = np.meshgrid(*axes, indexing="ij")
        wx, wy, wz = np.meshgrid(*(w * length for length in lengths), indexing="ij")
        volume = (wx * wy * wz).ravel()
        delta = xyz[:, None, :] - np.c_[x.ravel(), y.ravel(), z.ravel()][None, :, :]
        radius = np.linalg.norm(delta, axis=2)
        gz -= G * rho * 1e5 * np.sum(delta[:, :, 2] / radius**3 * volume, axis=1)
        dot = delta @ mag
        b += (
            mu_0
            / (4 * np.pi)
            * 1e9
            * np.sum(
                (
                    3 * delta * dot[:, :, None] / radius[:, :, None] ** 5
                    - mag / radius[:, :, None] ** 3
                )
                * volume[None, :, None],
                axis=1,
            )
        )
    return gz, b


def protocol(quick=False):
    return dict(
        schema_version=1,
        seed=6417,
        criteria=CRITERIA,
        data_fit_limits=dict(training_wrms=2.0, holdout_wrms=3.0),
        support_fraction=0.5,
        connectivity_radius_m=101.0,
        mesh=dict(
            shape=[8, 8, 6], cell_width_m=100.0, origin_m=[-400.0, -400.0, -600.0]
        ),
        design_fixtures=["shallow_cube", "deep_cube", "shifted_cube"],
        heldout_morphologies=["thin_body", "two_bodies"],
        fixtures=FIXTURES,
        noise_scales=[0.5, 2.0] if not quick else [0.5],
        strategies=STRATEGIES,
        common_partial_roi=[[-300.0, 300.0, -300.0, 300.0, -500.0, -100.0]],
        wrong_roi=[[100.0, 300.0, -100.0, 100.0, -400.0, -100.0]],
        property_limits=dict(
            gravity=[0.0, 0.8], susceptibility=[0.0, 0.1], mvi=[-0.1, 0.1]
        ),
        solver=dict(iterations=80, cg_maxiter=300, cg_rtol=1e-4, irls_iterations=15),
        field=dict(amplitude_nt=50000.0, inclination_deg=60.0, declination_deg=25.0),
        selection_policy="Fixed strategies and criteria before data generation; no production default selected; oracle and wrong-prior controls excluded from certification",
        quick=quick,
    )


def run(output, quick=False):
    from discretize import TensorMesh
    from simpeg import maps
    from simpeg.potential_fields import gravity, magnetics
    from terraworkbench_core.inversion import run_potential_field_inversion
    from terraworkbench_core._calibration import gaussian_calibration
    from terraworkbench_core.recovery_metrics import model_recovery_metrics
    from terraworkbench_core.spatial_constraints import spatial_property_constraints
    from scripts.validate_inversion_campaign import forward

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    plan = protocol(quick)
    plan_bytes = (json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()
    (output / "protocol.json").write_bytes(plan_bytes)
    report = dict(
        state="running",
        scientific_status="not_assessed",
        utc=datetime.now(timezone.utc).isoformat(),
        protocol=plan,
        protocol_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        git_head=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        git_dirty=repository_provenance(ROOT)["dirty"],
        platform=platform.platform(),
        versions={
            name: version(name)
            for name in ("numpy", "scipy", "simpeg", "discretize", "choclo")
        },
        source_sha256={
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "terraworkbench_core").glob("*.py")
        },
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cases=[],
        scope="Authored independent synthetic fields; explicit partial priors are experimental assumptions, not recovered geology. Truth-based oracle never certifies an unconstrained method.",
    )

    def save():
        staged = output / "report.json.part"
        staged.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        staged.replace(output / "report.json")

    save()
    mesh = TensorMesh(
        [[(100.0, 8)], [(100.0, 8)], [(100.0, 6)]], origin=[-400.0, -400.0, -600.0]
    )
    active = np.ones(mesh.nC, bool)
    n = mesh.nC
    centers = mesh.cell_centers
    x, y = np.meshgrid(np.arange(-400.0, 401.0, 100.0), np.arange(-400.0, 401.0, 100.0))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    hx, hy = np.meshgrid(
        np.arange(-350.0, 351.0, 100.0), np.arange(-350.0, 351.0, 100.0)
    )
    held = np.c_[hx.ravel(), hy.ravel(), np.full(hx.size, 120.0)]
    field = direction(60.0, 25.0)
    h0 = 50000e-9 / mu_0
    fixtures = ["shallow_cube", "thin_body"] if quick else list(FIXTURES)
    try:
        for name in fixtures:
            fi = list(FIXTURES).index(name)
            prisms = np.asarray(FIXTURES[name], float)
            nb = len(prisms)
            masks = [
                np.all((centers > p[::2]) & (centers < p[1::2]), axis=1) for p in prisms
            ]
            if np.any(np.sum(masks, axis=0) > 1) or any(not m.any() for m in masks):
                raise ValueError(
                    "Fixture bodies overlap or do not match cell-center geometry"
                )
            for ki, kind in enumerate(("gravity", "susceptibility", "mvi")):
                dirs = (
                    np.array(
                        [
                            direction(25.0, -35.0)
                            if i == 0
                            else direction(-35.0, 135.0)
                            for i in range(nb)
                        ]
                    )
                    if kind == "mvi"
                    else np.tile(field, (nb, 1))
                )
                mags = 0.025 * h0 * dirs
                clean_g, clean_b = integrated_fields(
                    xyz, prisms, np.full(nb, 400.0), mags
                )
                hold_g, hold_b = integrated_fields(
                    held, prisms, np.full(nb, 400.0), mags
                )
                clean = clean_g if kind == "gravity" else clean_b @ field
                hold_clean = hold_g if kind == "gravity" else hold_b @ field
                truth = np.zeros((n, 3)) if kind == "mvi" else np.zeros(n)
                basis = np.zeros(
                    (n * (3 if kind == "mvi" else 1), nb * (3 if kind == "mvi" else 1))
                )
                for bi, mask in enumerate(masks):
                    truth[mask] = (
                        0.025 * dirs[bi]
                        if kind == "mvi"
                        else (0.4 if kind == "gravity" else 0.025)
                    )
                    if kind == "mvi":
                        for axis in range(3):
                            basis[np.flatnonzero(mask) + axis * n, bi * 3 + axis] = 1.0
                    else:
                        basis[mask, bi] = 1.0
                size = basis.shape[0]
                if kind == "gravity":
                    survey = gravity.survey.Survey(
                        gravity.sources.SourceField(
                            receiver_list=[
                                gravity.receivers.Point(xyz, components="gz")
                            ]
                        )
                    )
                    sim = gravity.simulation.Simulation3DIntegral(
                        mesh,
                        survey=survey,
                        rhoMap=maps.IdentityMap(nP=size),
                        active_cells=active,
                        engine="choclo",
                        sensitivity_dtype=np.float64,
                    )
                else:
                    survey = magnetics.survey.Survey(
                        magnetics.sources.UniformBackgroundField(
                            receiver_list=[
                                magnetics.receivers.Point(xyz, components="tmi")
                            ],
                            amplitude=50000.0,
                            inclination=60.0,
                            declination=25.0,
                        )
                    )
                    sim = magnetics.simulation.Simulation3DIntegral(
                        mesh,
                        survey=survey,
                        chiMap=maps.IdentityMap(nP=size),
                        model_type="vector" if kind == "mvi" else "scalar",
                        active_cells=active,
                        engine="choclo",
                        sensitivity_dtype=np.float64,
                    )
                matrix = np.asarray(sim.getJ(np.zeros(size)))
                exact = truth.ravel(order="F") if kind == "mvi" else truth
                sigma_base = 0.002 if kind == "gravity" else 0.3
                discrepancy = float(np.max(abs(matrix @ exact - clean)) / sigma_base)
                if discrepancy > 1e-5:
                    raise ValueError(
                        f"Independent forward mismatch for fixture {name}/{kind}: {discrepancy}"
                    )
                for noise_scale in plan["noise_scales"]:
                    sigma = sigma_base * noise_scale
                    seed = 6417 + fi * 100 + ki * 10 + int(noise_scale * 10)
                    data = clean + sigma * np.random.default_rng(seed).normal(
                        size=len(clean)
                    )
                    strategies = list(STRATEGIES)
                    if name != "shallow_cube" or noise_scale != plan["noise_scales"][0]:
                        strategies.remove("wrong_roi_control")
                    for strategy in strategies:
                        options = dict(
                            cell_xy=100.0,
                            cell_z=100.0,
                            depth=600.0,
                            mesh=mesh,
                            active_cells=active,
                            iterations=80,
                            cg_maxiter=300,
                            cg_rtol=1e-4,
                            field_inclination=60.0,
                            field_declination=25.0,
                        )
                        if strategy == "oracle_known_geometry":
                            design = (matrix @ basis)[:, None, :]
                            coefficients, cov, diag = gaussian_calibration(
                                design,
                                data[:, None],
                                np.full((len(data), 1, 1), sigma * sigma),
                                maximum_condition=1e8,
                            )
                            model = basis @ coefficients
                            predicted = matrix @ model
                            diagnostics = dict(
                                solver="known-geometry GLS",
                                free_parameter_count=len(coefficients),
                                cg_tolerance_met=None,
                                solver_success=True,
                                calibration=diag,
                                coefficient_covariance=cov.tolist(),
                            )
                        else:
                            if strategy == "compact":
                                options.update(
                                    regularization_norms=[0.0, 1.0, 1.0, 1.0],
                                    irls_iterations=15,
                                )
                                if kind == "gravity":
                                    options["lower"] = 0.0
                            if strategy in (
                                "soft_roi",
                                "hard_roi",
                                "wrong_roi_control",
                            ):
                                lo, hi = plan["property_limits"][kind]
                                prior = spatial_property_constraints(
                                    centers,
                                    lower=lo,
                                    upper=hi,
                                    background_value=0.0,
                                    support_prisms_m=plan["wrong_roi"]
                                    if strategy == "wrong_roi_control"
                                    else plan["common_partial_roi"],
                                    mode="soft" if strategy == "soft_roi" else "hard",
                                    outside_weight=10.0
                                    if strategy == "soft_roi"
                                    else 1.0,
                                )
                                options.update(
                                    {
                                        k: prior[k]
                                        for k in ("lower", "upper", "cell_weights")
                                    }
                                )
                                if kind == "mvi":
                                    options["mvi_regularization"] = "vector_smooth"
                            result = run_potential_field_inversion(
                                kind, xyz, data, np.full(len(data), sigma), **options
                            )
                            model, predicted, diagnostics = (
                                result.model,
                                result.predicted,
                                result.diagnostics,
                            )
                        train = float(
                            np.sqrt(np.mean(((predicted - data) / sigma) ** 2))
                        )
                        hold_pred = forward(mesh, active, held, model, kind)
                        withheld = float(
                            np.sqrt(np.mean(((hold_pred - hold_clean) / sigma) ** 2))
                        )
                        shaped = (
                            model.reshape((n, 3), order="F") if kind == "mvi" else model
                        )
                        recovery = model_recovery_metrics(
                            centers,
                            mesh.cell_volumes,
                            shaped,
                            truth,
                            criteria=CRITERIA,
                            connectivity_radius_m=101.0,
                            vector=kind == "mvi",
                        )
                        fit_pass = train < 2.0 and withheld < 3.0
                        numerical_pass = (
                            diagnostics["solver_success"]
                            if strategy == "oracle_known_geometry"
                            else diagnostics["cg_tolerance_met"] is True
                        )
                        valid = bool(
                            fit_pass and numerical_pass and recovery["recovery_passed"]
                        )
                        item = dict(
                            fixture=name,
                            split="heldout_morphology"
                            if name in plan["heldout_morphologies"]
                            else "design",
                            kind=kind,
                            noise_scale=noise_scale,
                            data_std=sigma,
                            seed=seed,
                            strategy=strategy,
                            oracle_truth_in_fit=strategy == "oracle_known_geometry",
                            expected_negative=strategy == "wrong_roi_control",
                            status="recovery_passed" if valid else "recovery_failed",
                            execution_status="complete",
                            data_fit_passed=bool(fit_pass),
                            numerical_check_passed=bool(numerical_pass),
                            training_wrms=train,
                            holdout_wrms=withheld,
                            recovery=recovery,
                            diagnostics=diagnostics,
                            independent_forward_error_in_base_sigma=discrepancy,
                        )
                        report["cases"].append(item)
                        save()
                        print(
                            "RECOVERY",
                            name,
                            kind,
                            noise_scale,
                            strategy,
                            item["status"],
                            "model",
                            recovery["model_relative_error"],
                            flush=True,
                        )
        summaries = []
        for kind in ("gravity", "susceptibility", "mvi"):
            for strategy in STRATEGIES:
                cases = [
                    c
                    for c in report["cases"]
                    if c["kind"] == kind and c["strategy"] == strategy
                ]
                if not cases:
                    continue
                summaries.append(
                    dict(
                        kind=kind,
                        strategy=strategy,
                        cases=len(cases),
                        recovery_passes=sum(
                            c["status"] == "recovery_passed" for c in cases
                        ),
                        design_passes=sum(
                            c["status"] == "recovery_passed" and c["split"] == "design"
                            for c in cases
                        ),
                        heldout_passes=sum(
                            c["status"] == "recovery_passed"
                            and c["split"] == "heldout_morphology"
                            for c in cases
                        ),
                        median_model_error=float(
                            np.median(
                                [c["recovery"]["model_relative_error"] for c in cases]
                            )
                        ),
                        excluded_from_certification=bool(
                            STRATEGIES[strategy].get("truth_in_fit")
                            or STRATEGIES[strategy].get("expected_negative")
                        ),
                    )
                )
        report["summary"] = summaries
        eligible = [s for s in summaries if not s["excluded_from_certification"]]
        validated = [
            s
            for s in eligible
            if s["cases"] == (2 if quick else 10) and s["recovery_passes"] == s["cases"]
        ]
        report.update(
            state="complete",
            scientific_status="recovery_not_validated",
            fully_passing_nonoracle_configurations=validated,
            negative_control_rejected=all(
                c["status"] == "recovery_failed"
                for c in report["cases"]
                if c["expected_negative"]
            ),
            production_defaults_changed=False,
        )
        if (
            all(
                any(v["kind"] == kind for v in validated)
                for kind in ("gravity", "susceptibility", "mvi")
            )
            and not quick
            and report["negative_control_rejected"]
        ):
            report["scientific_status"] = "validated_for_declared_suite_only"
    except Exception as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--require-recovery",
        action="store_true",
        help="Exit nonzero unless all three kinds have a nonoracle configuration passing the complete declared suite",
    )
    args = parser.parse_args()
    report = run(args.output, args.quick)
    print(
        json.dumps(
            dict(
                state=report["state"],
                scientific_status=report["scientific_status"],
                cases=len(report["cases"]),
            )
        ),
        flush=True,
    )
    if (
        args.require_recovery
        and report["scientific_status"] != "validated_for_declared_suite_only"
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
