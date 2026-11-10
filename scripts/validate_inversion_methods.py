"""Synthetic MVI and fixed-geometry electrical/EM/SP sensitivity campaign.

No private data, QGIS or image inspection. Output directories must be new.
Parameterized self-consistency is explicitly separated from independent fields.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values) ** 2)))


class Campaign:
    def __init__(self, output):
        self.output = output
        output.mkdir(parents=True, exist_ok=False)
        modules = (
            "inversion",
            "electrical_pde",
            "layered_electrical",
            "fdem_3d",
            "self_potential_pde",
        )
        self.report = {
            "state": "running",
            "seed": 413,
            "versions": {
                name: version(name)
                for name in ("numpy", "scipy", "simpeg", "discretize")
            },
            "source_sha256": {
                name: hashlib.sha256(
                    (ROOT / "terraworkbench_core" / (name + ".py")).read_bytes()
                ).hexdigest()
                for name in modules
            },
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "acceptance": {
                "training_wrms_max": 2.0,
                "holdout_wrms_max": 3.0,
                "note": "Numerical diagnostic thresholds, not proof of unique recovery or outer convergence.",
            },
            "cases": [],
        }
        self.save()

    def save(self):
        (self.output / "report.json").write_text(
            json.dumps(self.report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    def record(self, name, **metrics):
        self.report["cases"].append(dict(name=name, **metrics))
        self.save()
        print(
            json.dumps(
                dict(
                    name=name,
                    **{
                        k: v
                        for k, v in metrics.items()
                        if k
                        in (
                            "wrms",
                            "holdout_wrms",
                            "success",
                            "model_error",
                            "angular_error_deg",
                        )
                    },
                )
            ),
            flush=True,
        )


def potential(campaign):
    from scripts.validate_inversion_campaign import direction, forward, volume_reference
    from terraworkbench_core.inversion import _mesh_from_data, run_inversion_workflow

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
    cases = [
        (f"mvi_{inc}_{dec}_noise{scale}", "mvi", inc, dec, scale, {})
        for inc, dec in ((25.0, -35.0), (-35.0, 135.0), (0.0, 90.0))
        for scale in (0.5, 1.0, 2.0)
    ]
    cases += [
        ("mvi_beta_low", "mvi", 25.0, -35.0, 1.0, {"beta0_ratio": 0.3}),
        ("mvi_beta_high", "mvi", 25.0, -35.0, 1.0, {"beta0_ratio": 3.0}),
        (
            "mvi_float32_disk",
            "mvi",
            25.0,
            -35.0,
            1.0,
            {
                "sensitivity_dtype": "float32",
                "sensitivity_path": str(campaign.output / "mvi_disk"),
            },
        ),
        ("mvi_short", "mvi", 25.0, -35.0, 1.0, {"iterations": 1}),
        ("gravity", "gravity", 60.0, 25.0, 1.0, {"lower": 0.0}),
        ("susceptibility", "susceptibility", 60.0, 25.0, 1.0, {}),
    ]
    for name, kind, inc, dec, scale, options in cases:
        index = 0 if kind == "gravity" else 1
        sigma = (0.002 if kind == "gravity" else 0.3) * scale
        clean = volume_reference(xyz, direction(inc, dec))[index]
        hold_clean = volume_reference(holdout, direction(inc, dec))[index]
        observed = clean + sigma * np.random.default_rng(413).normal(size=len(clean))
        truth = (
            (body[:, None] * 0.025 * direction(inc, dec)).ravel(order="F")
            if kind == "mvi"
            else body * (0.4 if kind == "gravity" else 0.025)
        )
        started = time.perf_counter()
        result = run_inversion_workflow(
            kind,
            xyz,
            observed,
            np.full(len(clean), sigma),
            output_directory=campaign.output / name,
            **(settings | options),
        )
        predicted = forward(mesh, active, holdout, result.model, kind)
        hold_wrms = rms((predicted - hold_clean) / sigma)
        item = dict(
            kind=kind,
            observations=len(xyz),
            active_cells=int(active.sum()),
            noise_std=sigma,
            seconds=time.perf_counter() - started,
            wrms=result.diagnostics["weighted_rms"],
            holdout_wrms=hold_wrms,
            model_error=float(
                np.linalg.norm(result.model - truth) / np.linalg.norm(truth)
            ),
            diagnostics=result.diagnostics,
            evidence="independent volume quadrature; holdout via alternative analytic kernel",
        )
        if kind == "mvi":
            vectors = result.model.reshape((-1, 3), order="F")
            moment = (mesh.cell_volumes[active, None] * vectors).sum(axis=0)
            item["angular_error_deg"] = float(
                np.rad2deg(
                    np.arccos(
                        np.clip(
                            moment @ direction(inc, dec) / np.linalg.norm(moment), -1, 1
                        )
                    )
                )
            )
            expected_moment = (mesh.cell_volumes[active] * body).sum() * 0.025
            item["integrated_moment_amplitude_ratio"] = float(
                np.linalg.norm(moment) / expected_moment
            )
            item["vector_units"] = (
                "effective susceptibility SI; magnetization A/m = vector * H0"
            )
        campaign.record(name, **item)
        assert np.isfinite(result.model).all() and np.isfinite(predicted).all()
        with np.load(campaign.output / name / "model.npz") as saved:
            np.testing.assert_array_equal(saved["model"], result.model)
        if name != "mvi_short":
            assert item["wrms"] < 2.0 and hold_wrms < 3.0, name
        else:
            assert (
                result.diagnostics["iteration_limit_reached"]
                and not result.diagnostics["target_reached"]
            )


def direction_control(campaign):
    """Known geometry isolates component/unit correctness from voxel ambiguity."""
    from scripts.validate_inversion_campaign import direction, forward, volume_reference
    from terraworkbench_core.inversion import _mesh_from_data

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
    basis = [(body[:, None] * unit).ravel(order="F") for unit in np.eye(3)]
    kernel = np.column_stack(
        [forward(mesh, active, xyz, vector, "mvi") for vector in basis]
    )
    hold_kernel = np.column_stack(
        [forward(mesh, active, holdout, vector, "mvi") for vector in basis]
    )
    independent = np.column_stack(
        [volume_reference(xyz, unit)[1] / 0.025 for unit in np.eye(3)]
    )
    np.testing.assert_allclose(kernel, independent, atol=1e-5, rtol=1e-10)
    for inc, dec in ((25.0, -35.0), (-35.0, 135.0), (0.0, 90.0)):
        truth = 0.025 * direction(inc, dec)
        clean = volume_reference(xyz, direction(inc, dec))[1]
        hold = volume_reference(holdout, direction(inc, dec))[1]
        for scale in (0.0, 0.5, 1.0, 2.0):
            std = 0.3 * max(scale, 0.5)
            observed = clean + (scale > 0) * std * np.random.default_rng(413).normal(
                size=len(clean)
            )
            model, _, rank, singular = np.linalg.lstsq(
                kernel / std, observed / std, rcond=None
            )
            wrms = rms((kernel @ model - observed) / std)
            hold_wrms = rms((hold_kernel @ model - hold) / std)
            angle = float(
                np.rad2deg(
                    np.arccos(
                        np.clip(
                            model
                            @ truth
                            / (np.linalg.norm(model) * np.linalg.norm(truth)),
                            -1.0,
                            1.0,
                        )
                    )
                )
            )
            campaign.record(
                f"known_body_{inc}_{dec}_noise{scale}",
                wrms=wrms,
                holdout_wrms=hold_wrms,
                model=model.tolist(),
                angular_error_deg=angle,
                model_error=float(
                    np.linalg.norm(model - truth) / np.linalg.norm(truth)
                ),
                rank=int(rank),
                singular_values=singular.tolist(),
                evidence="independent volume data; fixed known body; three-coefficient least-squares control, not voxel MVI",
            )
            assert rank == 3 and wrms < 2.0 and hold_wrms < 3.0
            if scale == 0:
                np.testing.assert_allclose(model, truth, atol=1e-10)


def electrical(campaign):
    from discretize import TensorMesh
    from terraworkbench_core.electrical import geometric_factor
    from terraworkbench_core.layered_electrical import dc_layered, fit_dc_resistivity
    from terraworkbench_core.electrical_pde import electrical_forward, invert_electrical

    def sounding(spacings):
        electrodes = np.array(
            [[offset, 0.0, 0.0] for a in spacings for offset in (-3 * a, -a, a, 3 * a)]
        )
        return electrodes, np.array(
            [[4 * i, 4 * i + 3, 4 * i + 1, 4 * i + 2] for i in range(len(spacings))]
        )

    xyz, abmn = sounding(np.geomspace(1.0, 80.0, 14))
    hx, hq = sounding(np.geomspace(1.2, 75.0, 11))
    truth = np.array([100.0, 500.0])
    clean = dc_layered(xyz, abmn, truth, [12.0])["resistance_ohm"]
    hold = dc_layered(hx, hq, truth, [12.0])["resistance_ohm"]
    half = dc_layered(xyz, abmn, [100.0], [])["resistance_ohm"]
    analytic = 100.0 / geometric_factor(xyz, abmn)
    np.testing.assert_allclose(half, analytic, rtol=1e-4)
    for scale in (0.0, 1.0, 2.0):
        std = abs(clean) * 0.01
        observed = clean + scale * std * np.random.default_rng(413).normal(
            size=len(clean)
        )
        for initial in ([80.0, 300.0], [200.0, 50.0]):
            fit = fit_dc_resistivity(
                xyz,
                abmn,
                observed,
                resistance_std_ohm=std * max(scale, 1.0),
                initial_resistivity_ohm_m=initial,
                thicknesses_m=[12.0],
            )
            model = fit["resistivity_ohm_m"]
            prediction = dc_layered(hx, hq, model, [12.0])["resistance_ohm"]
            wrms = float(np.sqrt(fit["chi_squared"] / len(clean)))
            campaign.record(
                f"dc_layers_noise{scale}_start{initial[0]}",
                wrms=wrms,
                holdout_wrms=rms(
                    (prediction - hold) / (abs(hold) * 0.01 * max(scale, 1.0))
                ),
                model=model.tolist(),
                model_error=float(
                    np.linalg.norm(model - truth) / np.linalg.norm(truth)
                ),
                success=fit["success"],
                evaluations=int(fit["evaluations"]),
                evidence="same forward kernel; fixed two-layer thickness; analytic half-space check",
            )
            assert fit["success"] and wrms < 2.0
            if scale == 0:
                np.testing.assert_allclose(model, truth, rtol=1e-4)

    widths = [
        np.r_[
            2 * 1.5 ** np.arange(8, 0, -1),
            np.repeat(2.0, 40),
            2 * 1.5 ** np.arange(1, 9),
        ],
        np.r_[2 * 1.5 ** np.arange(8, 0, -1), np.repeat(2.0, 20)],
    ]
    mesh = TensorMesh(widths, x0=[-widths[0].sum() / 2, -widths[1].sum()])
    x, z = mesh.cell_centers.T
    labels = ((abs(x) < 10) & (z > -12) & (z < -2)).astype(int)
    electrodes = np.array(
        [
            [center + dx, 0.0, 0.0]
            for center in (-16.0, -8.0, 0.0, 8.0, 16.0)
            for dx in (-12.0, -4.0, 4.0, 12.0)
        ]
    )
    args = dict(
        mesh_widths=widths,
        mesh_origin=mesh.x0,
        electrodes=electrodes,
        abmn=np.array([[4 * i, 4 * i + 3, 4 * i + 1, 4 * i + 2] for i in range(5)]),
        parameter_labels=labels,
    )
    sigma = [0.01, 0.03]
    for kind, truth, initial in (
        ("dc", np.array(sigma), [0.012, 0.02]),
        ("ip", np.array([0.015, 0.04]), [0.01, 0.03]),
    ):
        clean = electrical_forward(
            **args,
            conductivity_s_m=sigma,
            **({"chargeability_v_v": truth} if kind == "ip" else {}),
        )["predicted"]
        for scale in (0.0, 1.0, 2.0):
            std = np.maximum(abs(clean) * 0.01, 1e-6) * max(scale, 1.0)
            observed = clean + (scale > 0) * std * np.random.default_rng(413).normal(
                size=len(clean)
            )
            fit = invert_electrical(
                **args,
                kind=kind,
                observed=observed,
                data_std=std,
                initial=initial,
                reference=[0.01, 0.01],
                beta=1e-6,
                max_evaluations=40,
                max_forward_evaluations=150,
                **({"conductivity_s_m": sigma} if kind == "ip" else {}),
            )
            model = fit["model"]
            wrms = float(np.sqrt(fit["chi_squared"] / len(clean)))
            campaign.record(
                f"{kind}_pde_noise{scale}",
                model=model.tolist(),
                wrms=wrms,
                success=fit["success"],
                model_error=float(
                    np.linalg.norm(model - truth) / np.linalg.norm(truth)
                ),
                forward_calls=int(fit["forward_evaluations"]),
                evidence="same 2.5D PDE kernel; two prescribed zones; fixed IP conductivity",
            )
            assert fit["success"] and wrms < 2.0
            if scale == 0:
                np.testing.assert_allclose(model, truth, rtol=0.005)


def fdem(campaign):
    from discretize import TensorMesh
    from terraworkbench_core.fdem_3d import fdem_3d_forward, fit_fdem_3d_zones

    h = np.r_[8.0, 4.0, np.repeat(2.0, 4), 4.0, 8.0]
    mesh = TensorMesh([h] * 3, x0=[-h.sum() / 2] * 3)
    x, y, z = mesh.cell_centers.T
    labels = ((abs(x) < 4) & (abs(y) < 4) & (z < 0) & (z > -4)).astype(int)
    args = dict(
        mesh_widths=[h] * 3,
        mesh_origin=mesh.x0,
        source_m=[0.0, 0.0, 0.0],
        receiver_m=[3.0, 0.0, 0.0],
        parameter_labels=labels,
    )
    frequencies = [500.0, 1500.0, 5000.0, 15000.0]
    hold_frequency = [800.0, 3000.0, 9000.0]
    truth = np.array([0.1, 0.3])
    clean = fdem_3d_forward(**args, frequency_hz=frequencies, conductivity_s_m=truth)[
        "secondary_b_t"
    ]
    hold = fdem_3d_forward(**args, frequency_hz=hold_frequency, conductivity_s_m=truth)[
        "secondary_b_t"
    ]
    for scale in (0.0, 1.0, 2.0):
        std = (abs(clean) * 0.01 + 1e-14) * max(scale, 1.0)
        correlation = np.array([[1.0, 0.4], [0.4, 1.0]])
        factor = std[:, None, None] * np.linalg.cholesky(correlation)
        noise = np.einsum(
            "nij,nj->ni",
            factor,
            np.random.default_rng(413).normal(size=(len(clean), 2)),
        )
        observed = clean + (scale > 0) * (noise[:, 0] + 1j * noise[:, 1])
        for initial in ([0.08, 0.25], [0.2, 0.05]):
            fit = fit_fdem_3d_zones(
                **args,
                frequency_hz=frequencies,
                observed_secondary_b_t=observed,
                data_covariance_t2=factor @ factor.transpose(0, 2, 1),
                initial_conductivity_s_m=initial,
                reference_conductivity_s_m=[0.1, 0.1],
                beta=1e-6,
                max_evaluations=40,
                max_forward_evaluations=200,
            )
            model = fit["conductivity_s_m"]
            prediction = fdem_3d_forward(
                **args, frequency_hz=hold_frequency, conductivity_s_m=model
            )["secondary_b_t"]
            hold_std = (abs(hold) * 0.01 + 1e-14) * max(scale, 1.0)
            hold_wrms = rms(
                np.r_[
                    (prediction - hold).real / hold_std,
                    (prediction - hold).imag / hold_std,
                ]
            )
            jac = fit["weighted_log_parameter_jacobian"][: 2 * len(clean)]
            singular = np.linalg.svd(jac, compute_uv=False)
            wrms = float(np.sqrt(fit["data_chi_squared"] / (2 * len(clean))))
            campaign.record(
                f"fdem_noise{scale}_start{initial[0]}",
                model=model.tolist(),
                wrms=wrms,
                holdout_wrms=hold_wrms,
                success=fit["success"],
                model_error=float(
                    np.linalg.norm(model - truth) / np.linalg.norm(truth)
                ),
                data_jacobian_singular_values=singular.tolist(),
                active_bounds=fit["active_bounds"].tolist(),
                forward_calls=int(fit["forward_evaluations"]),
                evidence="same 3D PDE kernel; prescribed two zones; correlated real/imaginary noise; held-out frequencies",
            )
            assert fit["success"] and wrms < 2.0 and hold_wrms < 3.0
            if scale == 0:
                np.testing.assert_allclose(model, truth, rtol=0.005)


def sp(campaign):
    from discretize import TensorMesh
    from terraworkbench_core.self_potential_pde import (
        sp_pde_forward,
        fit_sp_pde_sources,
    )

    widths = [np.ones(8), np.ones(6), np.ones(4)]
    mesh = TensorMesh(widths, x0=[0.0, 0.0, 0.0])
    xyz = mesh.cell_centers
    sigma = np.where(xyz[:, 0] < 4.0, 0.1, 0.3)
    templates = (
        0.01 * np.c_[np.cos(np.pi * xyz[:, 0] / 8), np.cos(np.pi * xyz[:, 1] / 6)]
    )
    truth = np.array([1.5, -0.5])
    receivers, reference = xyz[1::3], xyz[0]
    clean = sp_pde_forward(
        widths, mesh.x0, sigma, templates @ truth, receivers, reference
    )["potential_difference_v"]
    hold = sp_pde_forward(
        widths, mesh.x0, sigma, templates @ truth, xyz[2::3], reference
    )["potential_difference_v"]
    for scale in (0.0, 1.0, 2.0):
        std = np.full(len(clean), 1e-4 * max(scale, 1.0))
        observed = clean + (scale > 0) * std * np.random.default_rng(413).normal(
            size=len(clean)
        )
        fit = fit_sp_pde_sources(
            widths,
            mesh.x0,
            sigma,
            templates,
            receivers,
            reference,
            observed,
            std,
            reference_coefficients=[0.0, 0.0],
            beta=1e-6,
        )
        model = fit["source_coefficients"]
        prediction = sp_pde_forward(
            widths, mesh.x0, sigma, templates @ model, xyz[2::3], reference
        )["potential_difference_v"]
        wrms = float(np.sqrt(fit["data_chi_squared"] / len(clean)))
        campaign.record(
            f"sp_noise{scale}",
            model=model.tolist(),
            wrms=wrms,
            holdout_wrms=rms((prediction - hold) / (1e-4 * max(scale, 1.0))),
            model_error=float(np.linalg.norm(model - truth) / np.linalg.norm(truth)),
            posterior_std=np.sqrt(np.diag(fit["posterior_covariance"])).tolist(),
            effective_coefficients=float(np.trace(fit["resolution"])),
            evidence="same 3D PDE kernel; fixed neutral templates/conductivity; noiseless reference",
        )
        assert wrms < 2.0
        if scale == 0:
            np.testing.assert_allclose(model, truth, atol=1e-7)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--section",
        choices=("all", "potential", "direction", "electrical", "fdem", "sp"),
        default="all",
    )
    args = parser.parse_args()
    campaign = Campaign(args.output)
    try:
        for name, operation in (
            ("potential", potential),
            ("direction", direction_control),
            ("electrical", electrical),
            ("fdem", fdem),
            ("sp", sp),
        ):
            if args.section in ("all", name):
                operation(campaign)
        campaign.report["state"] = "complete"
    except Exception as error:
        campaign.report.update(state="failed", error=str(error))
        raise
    finally:
        campaign.save()


if __name__ == "__main__":
    main()
