"""Small independent-volume synthetic inversions and sensitivity experiments.

Requires the inversion extra. Uses only synthetic data and a new output folder.
Volume quadrature supplies data independently of SimPEG/Choclo prism kernels.
Successful data recovery is not proof of unique geological model recovery.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.constants import G, mu_0

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terraworkbench_core.inversion import (  # noqa: E402
    _mesh_from_data,
    joint_full_models,
    run_inversion_workflow,
    run_joint_cross_gradient_inversion,
    write_mesh_vtk,
)


def direction(inclination, declination):
    inc, dec = np.deg2rad([inclination, declination])
    return np.array(
        [np.cos(inc) * np.sin(dec), np.cos(inc) * np.cos(dec), -np.sin(inc)]
    )


def volume_reference(xyz, magnetization_direction, order=12):
    """200 m cube at z=-200 m, density 400 kg/m3, effective chi=.025."""
    nodes, weights = leggauss(order)
    yy, xx, zz = np.meshgrid(nodes * 100, nodes * 100, nodes * 100 - 200, indexing="ij")
    wy, wx, wz = np.meshgrid(weights * 100, weights * 100, weights * 100, indexing="ij")
    source = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    volume = (wx * wy * wz).ravel()
    displacement = np.asarray(xyz)[:, None, :] - source[None, :, :]
    radius = np.linalg.norm(displacement, axis=2)
    gravity_up = (
        -G * 400 * 1e5 * np.sum(displacement[:, :, 2] / radius**3 * volume, axis=1)
    )
    magnetization = 0.025 * 50000e-9 / mu_0 * np.asarray(magnetization_direction)
    dot = displacement @ magnetization
    field = (
        mu_0
        / (4 * np.pi)
        * 1e9
        * np.sum(
            (
                3 * displacement * dot[:, :, None] / radius[:, :, None] ** 5
                - magnetization / radius[:, :, None] ** 3
            )
            * volume[None, :, None],
            axis=1,
        )
    )
    return gravity_up, field @ direction(60.0, 25.0)


def forward(mesh, active, xyz, model, kind):
    """Alternative analytic engine for holdout prediction, not fitted Jacobian."""
    from simpeg import maps
    from simpeg.potential_fields import gravity, magnetics

    common = dict(
        mesh=mesh,
        active_cells=active,
        engine="geoana",
        store_sensitivities="forward_only",
    )
    identity = maps.IdentityMap(nP=len(model))
    if kind == "gravity":
        survey = gravity.survey.Survey(
            gravity.sources.SourceField(
                receiver_list=[gravity.receivers.Point(xyz, components="gz")]
            )
        )
        simulation = gravity.simulation.Simulation3DIntegral(
            survey=survey, rhoMap=identity, **common
        )
    else:
        survey = magnetics.survey.Survey(
            magnetics.sources.UniformBackgroundField(
                receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
                amplitude=50000.0,
                inclination=60.0,
                declination=25.0,
            )
        )
        simulation = magnetics.simulation.Simulation3DIntegral(
            survey=survey,
            chiMap=identity,
            model_type="vector" if kind == "mvi" else "scalar",
            **common,
        )
    return np.asarray(simulation.dpred(model), float)


def run(output, iterations=40, joint_only=False):
    output.mkdir(parents=True, exist_ok=False)
    axis = np.arange(-300.0, 301.0, 100.0)
    x, y = np.meshgrid(axis, axis)
    xyz = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 100.0)))
    hx, hy = np.meshgrid(
        np.arange(-250.0, 251.0, 100.0), np.arange(-250.0, 251.0, 100.0)
    )
    holdout = np.column_stack((hx.ravel(), hy.ravel(), np.full(hx.size, 120.0)))
    topography = np.array(
        [
            [-500.0, -500.0, 0.0],
            [-500.0, 500.0, 0.0],
            [500.0, -500.0, 0.0],
            [500.0, 500.0, 0.0],
        ]
    )
    mesh, active = _mesh_from_data(xyz, 100.0, 100.0, 400.0, 1, topography=topography)
    centers = mesh.cell_centers[active]
    body = (
        (np.abs(centers[:, 0]) < 100)
        & (np.abs(centers[:, 1]) < 100)
        & (centers[:, 2] > -300)
        & (centers[:, 2] < -100)
    )
    truth = {
        "gravity": 0.4 * body,
        "susceptibility": 0.025 * body,
        "mvi": (body[:, None] * 0.025 * direction(25.0, -35.0)).ravel(order="F"),
    }
    reference = volume_reference(xyz, direction(60.0, 25.0))
    remanent = volume_reference(xyz, direction(25.0, -35.0))[1]
    clean = dict(gravity=reference[0], susceptibility=reference[1], mvi=remanent)
    hold_reference = volume_reference(holdout, direction(60.0, 25.0))
    hold_clean = dict(
        gravity=hold_reference[0],
        susceptibility=hold_reference[1],
        mvi=volume_reference(holdout, direction(25.0, -35.0))[1],
    )
    sigma = dict(gravity=0.002, susceptibility=0.3, mvi=0.3)
    rng = np.random.default_rng(82)
    observed = {
        kind: values + rng.normal(0, sigma[kind], values.shape)
        for kind, values in clean.items()
    }
    np.savez_compressed(
        output / "synthetic_inputs.npz",
        xyz=xyz,
        holdout=holdout,
        topography=topography,
        **{kind + "_observed": value for kind, value in observed.items()},
        **{kind + "_truth": value for kind, value in truth.items()},
    )
    report = {
        "status": "running",
        "source_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[1] / "terraworkbench_core/inversion.py"
            ).read_bytes()
        ).hexdigest(),
        "observations": len(xyz),
        "holdout_observations": len(holdout),
        "active_cells": int(active.sum()),
        "cases": [],
        "reference_checks": {},
    }

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    for kind in truth:
        actual = forward(mesh, active, xyz, truth[kind], kind)
        delta = float(np.max(np.abs(actual - clean[kind])))
        report["reference_checks"][kind] = {
            "max_abs_error": delta,
            "units": "mGal" if kind == "gravity" else "nT",
        }
        assert delta < (1e-8 if kind == "gravity" else 1e-5), (kind, delta)
    converged_reference = volume_reference(xyz, direction(60.0, 25.0), order=16)
    assert (
        max(np.max(abs(reference[i] - converged_reference[i])) for i in range(2)) < 1e-6
    )
    save()
    settings = dict(
        cell_xy=100.0,
        cell_z=100.0,
        depth=400.0,
        padding=1,
        iterations=iterations,
        field_inclination=60.0,
        field_declination=25.0,
        mesh=mesh,
        active_cells=active,
        cg_maxiter=60,
        max_sensitivity_bytes=10_000_000,
    )
    cases = [dict(name=kind, kind=kind) for kind in truth]
    cases += [dict(name="gravity_down", kind="gravity", gravity_component="down")]
    cases += [
        dict(
            name="susceptibility_beta_" + str(beta),
            kind="susceptibility",
            beta0_ratio=beta,
        )
        for beta in (0.3, 3.0)
    ]
    cases += [
        dict(
            name="susceptibility_sigma_" + str(scale),
            kind="susceptibility",
            sigma_scale=scale,
        )
        for scale in (0.5, 2.0)
    ]
    cases += [
        dict(
            name="susceptibility_float32_disk",
            kind="susceptibility",
            sensitivity_dtype="float32",
            sensitivity_path=str(output / "disk_sensitivities"),
        )
    ]
    models = {}
    if joint_only:
        cases = []
    try:
        for case in cases:
            options = dict(case)
            name, kind = options.pop("name"), options.pop("kind")
            scale = options.pop("sigma_scale", 1.0)
            sign = -1 if options.get("gravity_component") == "down" else 1
            if kind == "gravity":
                options.setdefault("lower", 0.0)
            item = {"name": name, "kind": kind, "status": "running"}
            report["cases"].append(item)
            save()
            started = time.perf_counter()
            result = run_inversion_workflow(
                kind,
                xyz,
                sign * observed[kind],
                np.full(len(xyz), sigma[kind] * scale),
                output_directory=output / name,
                **settings,
                **options,
            )
            predicted = forward(mesh, active, holdout, result.model, kind)
            item.update(
                seconds=time.perf_counter() - started,
                diagnostics=result.diagnostics,
                holdout_wrms=float(
                    np.sqrt(
                        np.mean(((predicted - hold_clean[kind]) / sigma[kind]) ** 2)
                    )
                ),
                noise_free_training_wrms=float(
                    np.sqrt(
                        np.mean(
                            ((sign * result.predicted - clean[kind]) / sigma[kind]) ** 2
                        )
                    )
                ),
                model_relative_error=float(
                    np.linalg.norm(result.model - truth[kind])
                    / np.linalg.norm(truth[kind])
                ),
            )
            manifest = json.loads(
                (output / name / "run.json").read_text(encoding="utf-8")
            )
            assert manifest["state"] == "complete"
            with np.load(output / name / "model.npz") as saved:
                np.testing.assert_array_equal(saved["model"], result.model)
                np.testing.assert_array_equal(
                    saved["predicted_total"], result.predicted
                )
            residual = np.loadtxt(output / name / "data.csv", delimiter=",", skiprows=1)
            np.testing.assert_allclose(
                residual[:, -1], sign * observed[kind] - result.predicted
            )
            assert result.diagnostics["weighted_rms"] < 2.0, item
            assert item["holdout_wrms"] < 3.0, item
            assert np.isfinite(result.model).all()
            if kind != "mvi":
                assert result.model.min() >= 0 and result.model.max() <= (
                    1.5 if kind == "gravity" else 1.0
                )
            if name == "gravity_down":
                np.testing.assert_allclose(
                    result.model, models["gravity"], atol=1e-10, rtol=1e-9
                )
            models[name] = result.model
            item["status"] = "passed"
            save()
            print(json.dumps(item), flush=True)
        joint_up = None
        for weight, component in ((0.0, "up"), (2e12, "up"), (2e12, "down")):
            name = "joint_" + str(weight) + "_" + component
            item = {
                "name": name,
                "kind": "joint",
                "status": "running",
                "coupling_weight": weight,
            }
            report["cases"].append(item)
            save()
            started = time.perf_counter()
            sign = -1 if component == "down" else 1
            result = run_joint_cross_gradient_inversion(
                xyz,
                sign * observed["gravity"],
                np.full(len(xyz), sigma["gravity"]),
                xyz,
                observed["susceptibility"],
                np.full(len(xyz), sigma["susceptibility"]),
                cell_xy=100.0,
                cell_z=100.0,
                depth=400.0,
                padding=1,
                topography=topography,
                iterations=iterations,
                coupling_weight=weight,
                density_bounds=(0.0, 1.0),
                susceptibility_bounds=(0.0, 0.1),
                field_inclination=60.0,
                field_declination=25.0,
                gravity_component=component,
            )
            item.update(
                seconds=time.perf_counter() - started,
                gravity_wrms=float(
                    np.sqrt(
                        np.mean(
                            (
                                (sign * result.predicted_gravity - observed["gravity"])
                                / sigma["gravity"]
                            )
                            ** 2
                        )
                    )
                ),
                magnetic_wrms=float(
                    np.sqrt(
                        np.mean(
                            (
                                (
                                    result.predicted_magnetics
                                    - observed["susceptibility"]
                                )
                                / sigma["susceptibility"]
                            )
                            ** 2
                        )
                    )
                ),
                gravity_holdout_wrms=float(
                    np.sqrt(
                        np.mean(
                            (
                                (
                                    forward(
                                        result.mesh,
                                        result.active,
                                        holdout,
                                        result.density,
                                        "gravity",
                                    )
                                    - hold_clean["gravity"]
                                )
                                / sigma["gravity"]
                            )
                            ** 2
                        )
                    )
                ),
                magnetic_holdout_wrms=float(
                    np.sqrt(
                        np.mean(
                            (
                                (
                                    forward(
                                        result.mesh,
                                        result.active,
                                        holdout,
                                        result.susceptibility,
                                        "susceptibility",
                                    )
                                    - hold_clean["susceptibility"]
                                )
                                / sigma["susceptibility"]
                            )
                            ** 2
                        )
                    )
                ),
                iterations=len(result.history),
            )
            folder = output / name
            folder.mkdir()
            write_mesh_vtk(
                folder / "models.vtk", result.mesh, joint_full_models(result)
            )
            np.savez_compressed(
                folder / "models.npz",
                density=result.density,
                susceptibility=result.susceptibility,
                predicted_gravity=result.predicted_gravity,
                predicted_magnetics=result.predicted_magnetics,
            )
            (folder / "diagnostics.json").write_text(
                json.dumps(item, indent=2) + "\n", encoding="utf-8"
            )
            assert item["gravity_wrms"] < 2 and item["magnetic_wrms"] < 2, item
            assert (
                item["gravity_holdout_wrms"] < 3 and item["magnetic_holdout_wrms"] < 3
            ), item
            if component == "down":
                np.testing.assert_allclose(
                    result.density, joint_up.density, rtol=1e-8, atol=1e-10
                )
                np.testing.assert_allclose(
                    result.susceptibility,
                    joint_up.susceptibility,
                    rtol=1e-8,
                    atol=1e-10,
                )
            if weight == 2e12 and component == "up":
                joint_up = result
            item["status"] = "passed"
            save()
            print(json.dumps(item), flush=True)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--joint-only", action="store_true")
    args = parser.parse_args()
    run(args.output, args.iterations, args.joint_only)


if __name__ == "__main__":
    main()
