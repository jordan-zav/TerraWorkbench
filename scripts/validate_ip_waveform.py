"""Reproducible synthetic finite-current-history IP campaign, without QGIS."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terraworkbench_core.ip_waveform import (  # noqa: E402
    fit_ip_waveform,
    fit_spatial_ip_waveform,
    ip_waveform_decay,
    spatial_ip_waveform,
)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "state": "running",
        "seed": 927,
        "scope": "authored synthetic finite histories; one noise realization, not field validation",
        "versions": {p: version(p) for p in ("numpy", "scipy", "simpeg", "discretize")},
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                ROOT / "scripts/validate_ip_waveform.py",
                ROOT / "terraworkbench_core/ip_waveform.py",
                ROOT / "terraworkbench_core/dispersive_ip.py",
                ROOT / "terraworkbench_core/electrical_pde.py",
            )
        },
        "cases": [],
    }

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

    def record(name, truth, observed, fit, noise, **inputs):
        model = fit["parameters"].reshape(truth.shape)
        case = {
            "name": name,
            "success": fit["success"],
            "weighted_rms": fit["weighted_rms"],
            "data_rank": fit["data_rank"],
            "relative_parameter_error": (abs(model - truth) / truth).tolist(),
            "parameters": model.tolist(),
            "forward_calls": fit["forward_evaluations"],
        }
        report["cases"].append(case)
        np.savez_compressed(
            output / (name + ".npz"),
            truth=truth,
            observed_v_v=observed,
            recovered=model,
            predicted_v_v=fit["predicted"],
            normalization=np.array(fit["normalization"]),
            **inputs,
        )
        save()
        print(json.dumps(case), flush=True)
        assert fit["success"] and fit["weighted_rms"] < 2, name
        if not noise:
            np.testing.assert_allclose(model, truth, rtol=1e-4, atol=1e-7)

    histories = {
        "unipolar": ([-7, -5, -3, 0], [2, 0, 2, 0]),
        "bipolar": ([-7, -5, -3, -1, 0], [2, 0, -2, 2, 0]),
    }
    edges = np.geomspace(0.002, 12.0, 21)
    gates = np.c_[edges[:-1], edges[1:]]
    save()
    try:
        for label, (events, currents) in histories.items():
            for exponent in (0.4, 0.65, 0.9):
                truth = np.array([0.15, 1.2, exponent])
                clean = ip_waveform_decay(
                    events,
                    currents,
                    gates_s=gates,
                    chargeability=truth[0],
                    tau_s=truth[1],
                    exponent=truth[2],
                )["decay_v_v"]
                for noise in (False, True):
                    observed = clean + noise * 1e-4 * np.random.default_rng(927).normal(
                        size=len(clean)
                    )
                    fit = fit_ip_waveform(
                        events,
                        currents,
                        observed,
                        gates_s=gates,
                        initial=[0.1, 0.7, 0.7],
                        standard_deviation=1e-4,
                    )
                    record(
                        f"{label}_c{exponent}_noise{int(noise)}",
                        truth,
                        observed,
                        fit,
                        noise,
                        gates_s=gates,
                        event_times_s=events,
                        current_a=currents,
                        standard_deviation=np.array(1e-4),
                    )

        from discretize import TensorMesh
        from terraworkbench_core.electrical_pde import ip_sensitivity

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
        S = operator["sensitivity"]
        np.savez_compressed(
            output / "spatial_geometry.npz",
            hx=h,
            hz=z,
            origin=mesh.x0,
            electrodes=electrodes,
            parameter_labels=labels,
            sensitivity=S,
            abmn=[[4 * i, 4 * i + 3, 4 * i + 1, 4 * i + 2] for i in range(5)],
            conductivity_s_m=[0.01, 0.03],
        )
        events, currents = histories["bipolar"]
        truth = np.array([[0.05, 0.4, 0.5], [0.12, 1.2, 0.8]])
        start = np.array([[0.08, 0.7, 0.6], [0.1, 0.8, 0.7]])
        for normalization in ("dc", "pulse"):
            clean = spatial_ip_waveform(
                S,
                events,
                currents,
                *truth.T,
                gates_s=gates,
                normalization=normalization,
            )["decay_v_v"]
            for noise in (False, True):
                observed = clean + noise * 1e-4 * np.random.default_rng(927).normal(
                    size=clean.shape
                )
                fit = fit_spatial_ip_waveform(
                    S,
                    events,
                    currents,
                    observed,
                    gates_s=gates,
                    initial=start,
                    reference=start,
                    beta=0.0,
                    standard_deviation=1e-4,
                    normalization=normalization,
                )
                record(
                    f"spatial_{normalization}_noise{int(noise)}",
                    truth,
                    observed,
                    fit,
                    noise,
                    gates_s=gates,
                    event_times_s=events,
                    current_a=currents,
                    sensitivity=S,
                    standard_deviation=np.array(1e-4),
                )
        report["state"] = "complete"
    except Exception as error:
        report.update(state="failed", error=str(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
