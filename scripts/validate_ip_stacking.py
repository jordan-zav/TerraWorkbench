"""Finite-history IP stack recovery; authored synthetics, no field data."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terraworkbench_core.ip_stacking import stack_ip_decay, fit_ip_stack  # noqa: E402


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "state": "running",
        "seed": 1047,
        "scope": "authored curve/parameterized sensitivity tests; one noise realization; no PDE or field validation",
        "versions": {p: version(p) for p in ("numpy", "scipy")},
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                ROOT / "terraworkbench_core/ip_stacking.py",
                ROOT / "terraworkbench_core/ip_waveform.py",
                ROOT / "terraworkbench_core/dispersive_ip.py",
            )
        },
        "cases": [],
    }
    events = np.arange(-7.0, 1.0)
    currents = np.array([1.0, 0.0, -2.0, 0.0, 0.8, 0.0, -1.5, 0.0])
    indices = np.array([1, 3, 5, 7])
    times = np.geomspace(0.001, 0.9, 18)
    weights = np.array([1.0, 2.0, 1.0, 3.0])
    common = dict(
        event_times_s=events,
        current_a=currents,
        off_event_indices=indices,
        times_s=times,
        stack_weights=weights,
    )
    S = np.array([[0.7, 0.3], [0.2, 0.8], [0.5, 0.5]])
    sigma = 1e-4

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

    def record(
        name, truth, observed, result, noise, mode, normalization, sensitivity=None
    ):
        recovered = result["parameters"].reshape(truth.shape)
        case = dict(
            name=name,
            success=result["success"],
            weighted_rms=result["weighted_rms"],
            data_rank=result["data_rank"],
            parameters=recovered.tolist(),
            relative_parameter_error=(abs(recovered - truth) / truth).tolist(),
            forward_evaluations=result["forward_evaluations"],
            stack_mode=mode,
            normalization=normalization,
        )
        report["cases"].append(case)
        np.savez_compressed(
            output / (name + ".npz"),
            **common,
            truth=truth,
            observed_v_v=observed,
            recovered=recovered,
            predicted_v_v=result["predicted"],
            standard_deviation=sigma,
            stack_mode=mode,
            normalization=normalization,
            **({} if sensitivity is None else {"sensitivity": sensitivity}),
        )
        save()
        print(json.dumps(case), flush=True)
        assert result["success"] and result["weighted_rms"] < 2.0, name
        if not noise:
            np.testing.assert_allclose(recovered, truth, rtol=1e-4, atol=1e-7)

    save()
    try:
        for mode in ("mean_of_ratios", "ratio_of_sums"):
            for exponent in (0.4, 0.85):
                truth = np.array([0.13, 0.7, exponent])
                clean = stack_ip_decay(
                    **common,
                    stack_mode=mode,
                    chargeability=truth[0],
                    tau_s=truth[1],
                    exponent=truth[2],
                )["decay_v_v"]
                for noise in (False, True):
                    observed = clean + noise * sigma * np.random.default_rng(
                        1047
                    ).normal(size=clean.shape)
                    result = fit_ip_stack(
                        **common,
                        observed_v_v=observed,
                        stack_mode=mode,
                        initial=[0.1, 0.5, 0.7],
                        standard_deviation=sigma,
                    )
                    record(
                        f"curve_{mode}_c{exponent}_noise{int(noise)}",
                        truth,
                        observed,
                        result,
                        noise,
                        mode,
                        "pulse",
                    )
            truth = np.array([[0.12, 0.5, 0.5], [0.08, 1.2, 0.8]])
            start = np.array([[0.1, 0.7, 0.6], [0.1, 1.0, 0.7]])
            for normalization in ("dc", "pulse"):
                clean = stack_ip_decay(
                    **common,
                    stack_mode=mode,
                    sensitivity=S,
                    chargeability=truth[:, 0],
                    tau_s=truth[:, 1],
                    exponent=truth[:, 2],
                    normalization=normalization,
                )["decay_v_v"]
                for noise in (False, True):
                    observed = clean + noise * sigma * np.random.default_rng(
                        1047
                    ).normal(size=clean.shape)
                    result = fit_ip_stack(
                        **common,
                        observed_v_v=observed,
                        stack_mode=mode,
                        sensitivity=S,
                        initial=start,
                        reference=start,
                        beta=0.0,
                        standard_deviation=sigma,
                        normalization=normalization,
                    )
                    record(
                        f"spatial_{mode}_{normalization}_noise{int(noise)}",
                        truth,
                        observed,
                        result,
                        noise,
                        mode,
                        normalization,
                        S,
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
