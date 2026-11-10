"""Explicit multi-operation Core recipes with bounded, typed result references.

No QGIS, REST, eval, arbitrary imports or inferred scientific parameters.
Publication is atomic for the workflow folder; failures retain a partial folder.
"""

import hashlib
import copy
import importlib
import inspect
import json
from pathlib import Path
import re
import uuid

import numpy as np

from .operations import operation_info, run_operation
from .operation_jobs import (
    MAX_RESULT_BYTES,
    _read_arrays,
    _cancel,
    parse_job_parameters,
    encode_result,
)


def _reference(value, previous, *, validate_only=False):
    if isinstance(value, dict):
        if "$result" in value:
            path = value["$result"]
            if (
                set(value) != {"$result"}
                or not isinstance(path, list)
                or not 2 <= len(path) <= 9
                or not isinstance(path[0], str)
                or path[0] not in previous
                or any(
                    isinstance(k, bool) or not isinstance(k, (str, int))
                    for k in path[1:]
                )
            ):
                raise ValueError(
                    "Result reference must identify an earlier step and explicit mapping keys/indices"
                )
            if validate_only:
                return value
            node = previous[path[0]]
            for key in path[1:]:
                if not isinstance(node, (dict, list, tuple, np.ndarray)):
                    raise ValueError("Result reference cannot traverse this value")
                if not isinstance(node, dict) and (not isinstance(key, int) or key < 0):
                    raise ValueError(
                        "Sequence result references require nonnegative integer indices"
                    )
                try:
                    node = node[key]
                except (KeyError, IndexError, TypeError) as error:
                    raise ValueError("Result reference does not exist") from error
            return copy.deepcopy(node)
        return {
            key: _reference(item, previous, validate_only=validate_only)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _reference(item, previous, validate_only=validate_only) for item in value
        ]
    return (
        value.copy() if isinstance(value, np.ndarray) and not validate_only else value
    )


def _function(info):
    module = importlib.import_module(
        "." + info["module"].rsplit(".", 1)[1], __package__
    )
    return getattr(module, info["function"])


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024**2):
            digest.update(chunk)
    return digest.hexdigest()


def validate_core_workflow(plan):
    """Validate structure, operation contracts and backward references; no solve."""
    if (
        not isinstance(plan, dict)
        or set(plan) != {"steps"}
        or not isinstance(plan["steps"], list)
        or not 1 <= len(plan["steps"]) <= 16
    ):
        raise ValueError("Workflow requires one to sixteen explicit steps")
    previous = set()
    for step in plan["steps"]:
        if (
            not isinstance(step, dict)
            or set(step) != {"id", "operation", "parameters"}
            or not isinstance(step["id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", step["id"])
            or step["id"] in previous
            or not isinstance(step["operation"], str)
            or not isinstance(step["parameters"], dict)
        ):
            raise ValueError("Invalid or duplicate workflow step")
        info = operation_info(step["operation"])
        function = _function(info)
        if {"canceled", "cancelled", "cancel"} & step["parameters"].keys():
            raise ValueError("Workflow owns cancellation callbacks")
        inspect.signature(function).bind(**step["parameters"])
        _reference(step["parameters"], previous, validate_only=True)
        previous.add(step["id"])


def run_core_workflow(
    recipe_json, output_root, *, input_npz=None, cancel=None, progress=None
):
    """Run 1..16 registered steps; $result paths start at an earlier result.

    Recipe: {"steps":[{"id":"source","operation":"potential.layer_response",
    "parameters":{...}}, {"id":"inverse","operation":...,"parameters":{
    "values":{"$result":["source","predicted"]}, ...}}]}.
    External arrays use the job API's {"$array":"name"} syntax. Up to 128 MiB
    of cumulative result arrays are retained; input/recipe limits match jobs.
    These are data budgets, not bounds on solver RAM or runtime. Every step
    has a verified job manifest compatible with load_core_job. All steps must
    complete, including solver convergence, before the workflow is published.
    No source data or existing output is overwritten. No GUI is required.
    """
    root = Path(output_root).resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing output folder")
    _cancel(cancel)
    arrays, input_hash = _read_arrays(input_npz, cancel)
    original, plan = parse_job_parameters(recipe_json, arrays)
    validate_core_workflow(plan)
    identity = "workflow_" + uuid.uuid4().hex
    staging, target = root / (identity + ".partial"), root / identity
    staging.mkdir()
    history, records = {}, []
    retained = 0
    try:
        for index, step in enumerate(plan["steps"]):
            _cancel(cancel)
            if progress:
                progress("Executing " + step["id"] + " (" + step["operation"] + ")")
            params = _reference(step["parameters"], history)
            info = operation_info(step["operation"])
            function = _function(info)
            runtime = next(
                (
                    name
                    for name in ("canceled", "cancelled", "cancel")
                    if name in inspect.signature(function).parameters
                ),
                None,
            )
            if runtime:
                params[runtime] = lambda: bool(cancel and cancel())
            result = run_operation(step["operation"], **params)
            _cancel(cancel)
            tree, outputs, descriptions = encode_result(result["result"])
            retained += sum(array.nbytes for array in outputs.values())
            if retained > MAX_RESULT_BYTES:
                raise ValueError("Cumulative workflow results exceed 128 MiB")
            folder = staging / step["id"]
            folder.mkdir()
            np.savez_compressed(folder / "arrays.npz", **outputs)
            _cancel(cancel)
            manifest = dict(
                schema_version=1,
                provenance=result["provenance"],
                parameters=original["steps"][index]["parameters"],
                input_archive_sha256=input_hash,
                result=tree,
                arrays=descriptions,
                array_file="arrays.npz",
                arrays_sha256=_file_hash(folder / "arrays.npz"),
            )
            (folder / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2),
                encoding="utf-8",
            )
            records.append(
                dict(
                    id=step["id"],
                    operation=step["operation"],
                    folder=step["id"],
                    status=result["provenance"]["status"],
                    manifest_sha256=_file_hash(folder / "manifest.json"),
                )
            )
            if result["provenance"]["status"] != "completed":
                raise ValueError("Workflow stopped at nonconverged step " + step["id"])
            history[step["id"]] = result["result"]
        summary = dict(
            schema_version=1,
            kind="core_workflow",
            status="completed",
            steps=records,
            recipe=original,
            input_archive_sha256=input_hash,
            cumulative_result_array_bytes=retained,
        )
        (staging / "workflow.json").write_text(
            json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2),
            encoding="utf-8",
        )
        _cancel(cancel)
        staging.rename(target)
    except Exception as error:
        if isinstance(error, InterruptedError) or cancel and cancel():
            raise InterruptedError(
                f"Workflow cancelled; unpublished workflow retained at {staging}"
            ) from error
        raise RuntimeError(
            f"{error}; unpublished workflow retained at {staging}"
        ) from error
    return dict(
        folder=str(target),
        manifest=str(target / "workflow.json"),
        status="completed",
        steps=records,
    )
