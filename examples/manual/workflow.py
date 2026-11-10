"""Registered MT half-space and the bundled artificial gravity-layer workflow."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from terraworkbench_core.operations import list_operations, run_operation
from terraworkbench_core.operation_workflows import run_core_workflow
from terraworkbench_core.operation_jobs import load_core_job

ROOT = Path(__file__).resolve().parents[2]


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    response = run_operation(
        "mt.layered_forward",
        frequency_hz=[1.0, 10.0, 100.0],
        resistivity_ohm_m=[100.0],
        thicknesses_m=[],
    )
    # Direct response arrays are checked by their actual keys below; they are
    # not treated as a finished field inversion.
    from terraworkbench_core.magnetotellurics import apparent_resistivity_phase

    impedance = response["result"]["impedance_ohm"]
    apparent = apparent_resistivity_phase([1.0, 10.0, 100.0], impedance)
    np.testing.assert_allclose(apparent["rho_a_ohm_m"], 100.0, rtol=1e-12)
    np.testing.assert_allclose(apparent["phase_deg"], 45.0, atol=1e-12)
    recipe = ROOT / "sample_data/workflows/gravity_layer.json"
    workflow = run_core_workflow(recipe.read_text(), output)
    loaded = load_core_job(Path(workflow["folder"]) / "recover")
    if loaded["provenance"]["status"] == "not_converged":
        raise AssertionError("Artificial workflow did not converge")
    expected = np.asarray(
        json.loads(recipe.read_text())["steps"][0]["parameters"]["values"]
    )
    np.testing.assert_allclose(
        loaded["result"]["contrast"], expected, rtol=1e-8, atol=1e-8
    )
    result = {
        "kind": "synthetic teaching workflow",
        "registry_count": len(list_operations()),
        "mt_max_resistivity_error": float(np.max(abs(apparent["rho_a_ohm_m"] - 100))),
        "layer_max_contrast_error": float(
            np.max(abs(loaded["result"]["contrast"] - expected))
        ),
        "workflow_folder": Path(workflow["folder"]).name,
        "mt_source_sha256": response["provenance"]["source_sha256"],
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
