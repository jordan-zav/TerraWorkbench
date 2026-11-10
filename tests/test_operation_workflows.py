import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from terraworkbench_core.operation_jobs import load_core_job
from terraworkbench_core.operation_workflows import run_core_workflow


def recipe():
    options = dict(
        kind="density", top_depth_m=10.0, thickness_m=50.0, spacing=[5.0, 5.0]
    )
    return dict(
        steps=[
            dict(
                id="response",
                operation="potential.layer_response",
                parameters=dict(options, values={"$array": "density"}),
            ),
            dict(
                id="recover",
                operation="potential.apparent_property",
                parameters=dict(
                    options,
                    values={"$result": ["response", "predicted"]},
                    background=0.0,
                    regularization_response=0.0,
                    max_inverse_gain=1e12,
                    minimum_wavelength_m=10.0,
                ),
            ),
        ]
    )


def test_workflow_real_kernel_chain_typed_reload_and_provenance(tmp_path):
    wave = np.broadcast_to(100.0 * np.cos(2 * np.pi * np.arange(9) / 9), (9, 9))
    source = tmp_path / "source.npz"
    np.savez(source, density=wave)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    plan = recipe()
    result = run_core_workflow(json.dumps(plan), tmp_path, input_npz=source)
    root = Path(result["folder"])
    assert not root.name.endswith(".partial")
    summary = json.loads((root / "workflow.json").read_text())
    assert summary["recipe"] == plan
    for step in summary["steps"]:
        folder = root / step["folder"]
        assert (
            step["manifest_sha256"]
            == hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest()
        )
        loaded = load_core_job(folder)
        assert loaded["provenance"]["source_sha256"]
        if step["id"] == "recover":
            np.testing.assert_allclose(loaded["result"]["contrast"], wave, atol=1e-8)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.parametrize(
    "fault", ["forward_reference", "duplicate", "path", "missing", "callback"]
)
def test_invalid_plans_rejected_before_output_creation(tmp_path, fault):
    plan = dict(
        steps=[
            dict(
                id="first",
                operation="potential.layer_response",
                parameters=dict(
                    values=np.ones((3, 3)).tolist(),
                    spacing=[1, 1],
                    kind="density",
                    top_depth_m=0.0,
                    thickness_m=1.0,
                ),
            )
        ]
    )
    if fault == "forward_reference":
        plan["steps"][0]["parameters"]["values"] = {"$result": ["later", "predicted"]}
    elif fault == "duplicate":
        plan["steps"] *= 2
    elif fault == "path":
        plan["steps"][0]["id"] = "../escape"
    elif fault == "missing":
        del plan["steps"][0]["parameters"]["kind"]
    else:
        plan["steps"][0]["parameters"]["canceled"] = None
    with pytest.raises((ValueError, TypeError)):
        run_core_workflow(json.dumps(plan), tmp_path)
    assert not list(tmp_path.iterdir())


def test_failure_and_cancellation_do_not_publish_workflows(tmp_path):
    plan = dict(
        steps=[
            dict(
                id="first",
                operation="potential.layer_response",
                parameters=dict(
                    values=np.ones((3, 3)).tolist(),
                    spacing=[1, 1],
                    kind="density",
                    top_depth_m=-1.0,
                    thickness_m=1.0,
                ),
            )
        ]
    )
    with pytest.raises(RuntimeError, match="unpublished workflow"):
        run_core_workflow(json.dumps(plan), tmp_path)
    assert all(path.name.endswith(".partial") for path in tmp_path.iterdir())
    with pytest.raises(InterruptedError):
        run_core_workflow(json.dumps(plan), tmp_path, cancel=lambda: True)


def test_unresolved_runtime_path_retains_first_step_without_publication(tmp_path):
    plan = recipe()
    plan["steps"][0]["parameters"]["values"] = np.ones((9, 9)).tolist()
    plan["steps"][1]["parameters"]["values"] = {"$result": ["response", "missing"]}
    with pytest.raises(RuntimeError, match="reference does not exist"):
        run_core_workflow(json.dumps(plan), tmp_path)
    partial = next(tmp_path.glob("*.partial"))
    assert (partial / "response" / "manifest.json").is_file()
    assert not (partial / "workflow.json").exists()


def test_result_budget_and_nonconvergence_stop_publication(tmp_path, monkeypatch):
    from terraworkbench_core import operation_workflows as workflow

    plan = recipe()
    plan["steps"][0]["parameters"]["values"] = np.ones((9, 9)).tolist()
    monkeypatch.setattr(workflow, "MAX_RESULT_BYTES", 8)
    with pytest.raises(RuntimeError, match="Cumulative workflow results"):
        workflow.run_core_workflow(json.dumps(plan), tmp_path)
    monkeypatch.setattr(workflow, "MAX_RESULT_BYTES", 128 * 1024**2)
    actual = workflow.run_operation
    calls = []

    def fail_convergence(operation, **parameters):
        result = actual(operation, **parameters)
        calls.append(operation)
        result["provenance"]["status"] = "not_converged"
        return result

    monkeypatch.setattr(workflow, "run_operation", fail_convergence)
    with pytest.raises(RuntimeError, match="nonconverged step response"):
        workflow.run_core_workflow(json.dumps(plan), tmp_path)
    assert calls == ["potential.layer_response"]
    assert all(path.name.endswith(".partial") for path in tmp_path.iterdir())


def test_cancellation_between_steps_preserves_incomplete_results(tmp_path):
    plan = recipe()
    plan["steps"][0]["parameters"]["values"] = np.ones((9, 9)).tolist()
    cancelled = [False]

    def progress(message):
        if "recover" in message:
            cancelled[0] = True

    with pytest.raises(InterruptedError):
        run_core_workflow(
            json.dumps(plan), tmp_path, cancel=lambda: cancelled[0], progress=progress
        )
    partial = next(tmp_path.glob("*.partial"))
    assert (partial / "response" / "manifest.json").is_file()
    assert not (partial / "workflow.json").exists()
