"""Reproducible dispersive-IP recovery and explicit-support MVI comparisons."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(output, section):
    output.mkdir(parents=True, exist_ok=False)
    names = ("inversion", "electrical_pde", "dispersive_ip")
    report = {
        "state": "running",
        "seed": 413,
        "source_sha256": {
            n: hashlib.sha256(
                (ROOT / "terraworkbench_core" / (n + ".py")).read_bytes()
            ).hexdigest()
            for n in names
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "versions": {n: version(n) for n in ("numpy", "scipy", "simpeg", "discretize")},
        "cases": [],
    }

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    def record(name, **values):
        report["cases"].append(dict(name=name, **values))
        save()
        print(
            json.dumps(
                dict(
                    name=name,
                    **{
                        k: v
                        for k, v in values.items()
                        if k in ("wrms", "angle_deg", "holdout_wrms", "success")
                    },
                )
            ),
            flush=True,
        )

    def ip_record(name, fit, truth, **inputs):
        model = fit["parameters"].reshape(np.asarray(truth).shape)
        np.savez_compressed(
            output / (name + ".npz"),
            model=model,
            truth=truth,
            predicted=fit["predicted"],
            **inputs,
        )
        record(
            name,
            model=model.tolist(),
            relative_parameter_error=(abs(model - truth) / truth).tolist(),
            wrms=fit["weighted_rms"],
            success=fit["success"],
            data_rank=fit["data_rank"],
            forward_calls=int(fit["forward_evaluations"]),
            active_bounds=fit["active_bounds"].tolist(),
        )
        assert fit["success"] and fit["weighted_rms"] < 2.0, name

    save()
    try:
        if section in ("all", "ip"):
            from terraworkbench_core.dispersive_ip import (
                cole_cole_decay,
                fit_ip_decay,
                fit_cole_cole_spectrum,
                dispersive_ip_forward,
                fit_dispersive_ip,
            )
            from terraworkbench_core.electrical import cole_cole_resistivity
            from terraworkbench_core.electrical_pde import ip_sensitivity
            from discretize import TensorMesh

            f = np.geomspace(0.001, 1e4, 32)
            for c in (0.4, 0.65, 0.9):
                truth = np.array([120.0, 0.15, 0.8, c])
                clean = cole_cole_resistivity(f, *truth)
                for noise in (False, True):
                    z = np.random.default_rng(413).normal(size=(len(f), 2))
                    covariance = np.array([[0.04, 0.01], [0.01, 0.09]])
                    perturbation = z @ np.linalg.cholesky(covariance).T
                    observed = clean + noise * (
                        perturbation[:, 0] + 1j * perturbation[:, 1]
                    )
                    fit = fit_cole_cole_spectrum(
                        f,
                        observed,
                        initial=[90.0, 0.1, 0.4, 0.7],
                        data_covariance=covariance,
                    )
                    ip_record(
                        f"spectral_c{c}_noise{int(noise)}",
                        fit,
                        truth,
                        samples=f,
                        observed=observed,
                        covariance=covariance,
                    )
                    if not noise:
                        np.testing.assert_allclose(fit["parameters"], truth, rtol=1e-4)

                edges = np.geomspace(0.002, 8.0, 19)
                gates = np.c_[edges[:-1], edges[1:]]
                true_decay = truth[1:]
                clean_decay = cole_cole_decay(
                    None,
                    *true_decay,
                    gates_s=gates,
                    pulse_duration_s=1.0,
                    normalization="pulse",
                )
                for noise in (False, True):
                    observed = clean_decay + noise * 1e-4 * np.random.default_rng(
                        413
                    ).normal(size=len(gates))
                    fit = fit_ip_decay(
                        observed,
                        gates_s=gates,
                        pulse_duration_s=1.0,
                        normalization="pulse",
                        initial=[0.1, 0.4, 0.7],
                        standard_deviation=1e-4,
                    )
                    ip_record(
                        f"transient_c{c}_noise{int(noise)}",
                        fit,
                        true_decay,
                        gates=gates,
                        observed=observed,
                        std=np.array(1e-4),
                    )
                    if not noise:
                        np.testing.assert_allclose(
                            fit["parameters"], true_decay, rtol=1e-4
                        )

            h = np.r_[
                2 * 1.5 ** np.arange(6, 0, -1),
                np.repeat(2.0, 30),
                2 * 1.5 ** np.arange(1, 7),
            ]
            z = np.r_[2 * 1.5 ** np.arange(6, 0, -1), np.repeat(2.0, 15)]
            mesh = TensorMesh([h, z], x0=[-h.sum() / 2, -z.sum()])
            x, zz = mesh.cell_centers.T
            labels = ((abs(x) < 10) & (zz > -12) & (zz < -2)).astype(int)
            electrodes = np.array(
                [
                    [center + dx, 0.0, 0.0]
                    for center in (-16.0, -8.0, 0.0, 8.0, 16.0)
                    for dx in (-12.0, -4.0, 4.0, 12.0)
                ]
            )
            operator = ip_sensitivity(
                [h, z],
                mesh.x0,
                electrodes,
                [[4 * i, 4 * i + 3, 4 * i + 1, 4 * i + 2] for i in range(5)],
                conductivity_s_m=[0.01, 0.03],
                parameter_labels=labels,
            )
            sensitivity = operator["sensitivity"]
            truth = np.array([[0.05, 0.4, 0.5], [0.12, 1.2, 0.8]])
            for domain in ("frequency", "time"):
                samples = (
                    np.geomspace(0.01, 100.0, 18)
                    if domain == "frequency"
                    else np.geomspace(0.005, 8.0, 18)
                )
                clean = dispersive_ip_forward(
                    sensitivity, samples, *truth.T, domain=domain
                )
                for noise in (False, True):
                    rng = np.random.default_rng(413)
                    perturbation = 1e-4 * rng.normal(size=clean.shape)
                    if domain == "frequency":
                        perturbation = perturbation + 1j * 1e-4 * rng.normal(
                            size=clean.shape
                        )
                    observed = clean + noise * perturbation
                    fit = fit_dispersive_ip(
                        sensitivity,
                        samples,
                        observed,
                        domain=domain,
                        initial=[[0.04, 0.3, 0.6], [0.1, 0.8, 0.7]],
                        reference=[[0.03, 0.5, 0.6], [0.03, 0.5, 0.6]],
                        beta=1e-6,
                        standard_deviation=1e-4,
                        max_forward_evaluations=4000,
                    )
                    ip_record(
                        f"spatial_{domain}_noise{int(noise)}",
                        fit,
                        truth,
                        sensitivity=sensitivity,
                        samples=samples,
                        observed=observed,
                        std=np.array(1e-4),
                    )
                    if not noise:
                        np.testing.assert_allclose(
                            fit["parameters"].reshape(-1, 3), truth, rtol=1e-3
                        )

        if section in ("all", "mvi"):
            from scripts.validate_inversion_campaign import (
                direction,
                volume_reference,
                forward,
            )
            from terraworkbench_core.inversion import (
                _mesh_from_data,
                run_inversion_workflow,
            )

            x, y = np.meshgrid(
                np.arange(-300.0, 301.0, 100.0), np.arange(-300.0, 301.0, 100.0)
            )
            xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
            hx, hy = np.meshgrid(
                np.arange(-250.0, 251.0, 100.0), np.arange(-250.0, 251.0, 100.0)
            )
            hold = np.c_[hx.ravel(), hy.ravel(), np.full(hx.size, 120.0)]
            topo = np.array(
                [[-500, -500, 0], [-500, 500, 0], [500, -500, 0], [500, 500, 0.0]]
            )
            mesh, base_active = _mesh_from_data(
                xyz, 100.0, 100.0, 400.0, 1, topography=topo
            )
            centers = mesh.cell_centers
            roi = (
                base_active
                & (abs(centers[:, 0]) < 200)
                & (abs(centers[:, 1]) < 200)
                & (centers[:, 2] > -400)
                & (centers[:, 2] < 0)
            )
            for inc, dec in ((25.0, -35.0), (-35.0, 135.0), (0.0, 90.0)):
                target = volume_reference(hold, direction(inc, dec))[1]
                observed = volume_reference(xyz, direction(inc, dec))[
                    1
                ] + 0.3 * np.random.default_rng(413).normal(size=len(xyz))
                for region, active in (("full", base_active), ("roi", roi)):
                    for mode in ("amplitude", "vector_smooth"):
                        name = f"mvi_{inc}_{dec}_{region}_{mode}"
                        options = (
                            {}
                            if mode == "amplitude"
                            else dict(
                                regularization_norms=[0, 2, 2, 2], irls_iterations=12
                            )
                        )
                        result = run_inversion_workflow(
                            "mvi",
                            xyz,
                            observed,
                            np.full(len(xyz), 0.3),
                            output_directory=output / name,
                            cell_xy=100.0,
                            cell_z=100.0,
                            depth=400.0,
                            mesh=mesh,
                            active_cells=active,
                            iterations=80,
                            cg_maxiter=300,
                            cg_rtol=1e-4,
                            field_inclination=60.0,
                            field_declination=25.0,
                            mvi_regularization=mode,
                            **options,
                        )
                        vectors = result.model.reshape(-1, 3, order="F")
                        moment = (mesh.cell_volumes[active, None] * vectors).sum(axis=0)
                        angle = float(
                            np.degrees(
                                np.arccos(
                                    np.clip(
                                        moment
                                        @ direction(inc, dec)
                                        / np.linalg.norm(moment),
                                        -1,
                                        1,
                                    )
                                )
                            )
                        )
                        prediction = forward(mesh, active, hold, result.model, "mvi")
                        wrms = float(
                            np.sqrt(np.mean(((prediction - target) / 0.3) ** 2))
                        )
                        record(
                            name,
                            angle_deg=angle,
                            holdout_wrms=wrms,
                            wrms=result.diagnostics["weighted_rms"],
                            active_cells=int(active.sum()),
                            diagnostics=result.diagnostics,
                            prior="explicit 400m support box"
                            if region == "roi"
                            else "none beyond mesh",
                        )
                        assert wrms < 3.0 and result.diagnostics["weighted_rms"] < 2.0
        report["state"] = "complete"
    except Exception as error:
        report.update(state="failed", error=str(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--section", choices=("all", "ip", "mvi"), default="all")
    args = parser.parse_args()
    run(args.output, args.section)
