"""Explicit advanced jobs: bounded safe NPZ input, typed results, atomic publication.

Budgets constrain input/result arrays, NOT solver working memory or runtime.
No eval, arbitrary imports, pickle, dependency installation or source edits.
"""

import hashlib
import importlib
import inspect
import json
import math
from pathlib import Path
import uuid
from zipfile import ZipFile

import numpy as np

from . import operations

MAX_INPUT_BYTES = 256 * 1024**2
MAX_RESULT_BYTES = 128 * 1024**2


def _cancel(cancel):
    if cancel and cancel():
        raise InterruptedError("Core job cancelled; no completed result published")


def _read_arrays(path, cancel):
    if not path:
        return {}, None
    arrays = {}
    with Path(path).open("rb") as handle:
        from os import fstat

        before = fstat(handle.fileno())
        handle.seek(0, 2)
        if handle.tell() > MAX_INPUT_BYTES + 2 * 1024**2:
            raise ValueError("NPZ file exceeds input archive budget")
        handle.seek(0)
        with ZipFile(handle) as bundle:
            members = bundle.infolist()
            if (
                len(members) > 256
                or len({m.filename for m in members}) != len(members)
                or sum(m.file_size for m in members) > MAX_INPUT_BYTES
            ):
                raise ValueError(
                    "NPZ archive exceeds member/size budgets or has duplicate names"
                )
            total = 0
            for member in members:
                _cancel(cancel)
                if not member.filename.endswith(".npy"):
                    raise ValueError("NPZ must contain only NumPy arrays")
                with bundle.open(member) as item:
                    version = np.lib.format.read_magic(item)
                    if version == (1, 0):
                        shape, _, dtype = np.lib.format.read_array_header_1_0(item)
                    elif version == (2, 0):
                        shape, _, dtype = np.lib.format.read_array_header_2_0(item)
                    else:
                        raise ValueError(
                            "Only NPY 1.0/2.0 numeric/string arrays are supported"
                        )
                    if (
                        dtype.hasobject
                        or dtype.kind not in "biufcSU"
                        or dtype.itemsize <= 0
                        or len(shape) > 8
                        or any(size < 0 for size in shape)
                    ):
                        raise ValueError("Unsafe or unsupported array dtype/shape")
                    total += math.prod(shape) * dtype.itemsize
                    if total > MAX_INPUT_BYTES:
                        raise ValueError(
                            "NPZ declared array sizes exceed the input budget"
                        )
        handle.seek(0)
        digest = hashlib.sha256()
        while chunk := handle.read(1024**2):
            _cancel(cancel)
            digest.update(chunk)
        handle.seek(0)
        with np.load(handle, allow_pickle=False) as archive:
            for name in archive.files:
                _cancel(cancel)
                arrays[name] = archive[name]
        after = fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Input archive changed while being read")
    return arrays, digest.hexdigest()


def parse_job_parameters(text, arrays):
    if len(text.encode("utf-8")) > 1024**2:
        raise ValueError("Parameter JSON exceeds 1 MiB")

    def reject(value):
        raise ValueError("Nonfinite JSON numbers are not supported: " + value)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON parameter: " + key)
            result[key] = value
        return result

    original = json.loads(text, parse_constant=reject, object_pairs_hook=pairs)
    if not isinstance(original, dict):
        raise ValueError("Parameters must be a JSON object")

    def resolve(value, depth=0):
        if depth > 32:
            raise ValueError("Parameter nesting is too deep")
        if isinstance(value, dict):
            if set(value) == {"$array"}:
                name = value["$array"]
                if not isinstance(name, str) or name not in arrays:
                    raise ValueError("Unknown NPZ array reference: " + str(name))
                return arrays[name]
            return {key: resolve(item, depth + 1) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item, depth + 1) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nonfinite JSON number")
        return value

    return original, resolve(original)


def encode_result(result):
    """Preserve arrays, complex phase, masks, mappings and nonfinite scalars."""
    arrays, descriptions = {}, {}
    total = 0
    elements = 0

    def encode(value, depth=0):
        nonlocal total, elements
        elements += 1
        if (
            elements > 100000
            or isinstance(value, str)
            and len(value.encode("utf-8")) > 1024**2
        ):
            raise ValueError("Result metadata exceeds element/string budgets")
        if depth > 32:
            raise ValueError("Result nesting is too deep")
        if np.ma.isMaskedArray(value):
            mask = np.ma.getmaskarray(value)
            data_reference = encode(value.data, depth + 1)
            if value.dtype.kind in "biufc":
                description = descriptions[data_reference["name"]]
                valid = ~mask & np.isfinite(value.data)
                description["finite"] = int(valid.sum())
                description["masked_values_excluded"] = True
                key = (
                    "magnitude_statistics" if value.dtype.kind == "c" else "statistics"
                )
                selected = (
                    np.abs(value.data[valid])
                    if value.dtype.kind == "c"
                    else value.data[valid]
                )
                with np.errstate(over="ignore", invalid="ignore"):
                    statistics = (
                        {
                            "min": float(selected.min()),
                            "max": float(selected.max()),
                            "mean": float(selected.mean()),
                        }
                        if selected.size
                        else {}
                    )
                description[key] = {
                    name: number if math.isfinite(number) else None
                    for name, number in statistics.items()
                }
            return {
                "kind": "masked",
                "data": data_reference,
                "mask": encode(mask, depth + 1),
                "fill": encode(value.fill_value, depth + 1),
            }
        if isinstance(value, np.ndarray):
            if value.dtype.hasobject or value.dtype.kind not in "biufcSU":
                raise ValueError(
                    "Object/structured result arrays cannot be saved safely"
                )
            total += value.nbytes
            if total > MAX_RESULT_BYTES or len(arrays) >= 256:
                raise ValueError("Result exceeds safe output array budgets")
            name = f"array_{len(arrays):04d}"
            arrays[name] = value
            description = {"shape": list(value.shape), "dtype": str(value.dtype)}
            if value.dtype.kind in "biufc" and value.size:
                finite = np.isfinite(value)
                description["finite"] = int(finite.sum())
                if finite.any():
                    selected = (
                        np.abs(value[finite])
                        if value.dtype.kind == "c"
                        else value[finite]
                    )
                    with np.errstate(over="ignore", invalid="ignore"):
                        stats = {
                            "min": float(selected.min()),
                            "max": float(selected.max()),
                            "mean": float(selected.mean()),
                        }
                    description[
                        "magnitude_statistics"
                        if value.dtype.kind == "c"
                        else "statistics"
                    ] = {
                        key: number if math.isfinite(number) else None
                        for key, number in stats.items()
                    }
            descriptions[name] = description
            return {"kind": "array", "name": name}
        if isinstance(value, np.generic):
            return encode(value.item(), depth + 1)
        if isinstance(value, complex):
            return {
                "kind": "complex",
                "real": encode(value.real, depth + 1),
                "imag": encode(value.imag, depth + 1),
            }
        if isinstance(value, float) and not math.isfinite(value):
            return {"kind": "nonfinite", "value": str(value)}
        if value is None or isinstance(value, (str, int, float, bool)):
            return {"kind": "scalar", "value": value}
        if isinstance(value, dict):
            return {
                "kind": "mapping",
                "entries": [
                    [encode(key, depth + 1), encode(item, depth + 1)]
                    for key, item in value.items()
                ],
            }
        if isinstance(value, (list, tuple)):
            return {
                "kind": "tuple" if isinstance(value, tuple) else "list",
                "items": [encode(item, depth + 1) for item in value],
            }
        raise ValueError("Unsupported result type: " + type(value).__name__)

    tree = encode(result)
    if len(json.dumps(tree, allow_nan=False).encode("utf-8")) > 4 * 1024**2:
        raise ValueError("Result metadata exceeds 4 MiB; use array inputs/results")
    return tree, arrays, descriptions


def run_core_job(
    operation_id,
    parameters_json,
    output_root,
    *,
    input_npz=None,
    cancel=None,
    progress=None,
):
    """Run one registered operation; only engine-supported cancellation is injected.

    Partial job folders are retained on failure/cancellation for diagnosis.
    A manifest and NPZ are published together by renaming a unique job folder.
    """
    info = operations.operation_info(operation_id)
    root = Path(output_root).resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing output folder")
    _cancel(cancel)
    if progress:
        progress("Reading explicit inputs")
    arrays, input_hash = _read_arrays(input_npz, cancel)
    original, parameters = parse_job_parameters(parameters_json, arrays)
    function = getattr(
        importlib.import_module("." + info["module"].rsplit(".", 1)[1], __package__),
        info["function"],
    )
    signature = inspect.signature(function)
    runtime = next(
        (
            name
            for name in ("canceled", "cancelled", "cancel")
            if name in signature.parameters
        ),
        None,
    )
    if runtime:
        if runtime in parameters:
            raise ValueError("Cancellation callbacks are managed by the host, not JSON")
        parameters[runtime] = cancel
    signature.bind(**parameters)
    _cancel(cancel)
    if progress:
        progress("Executing " + operation_id)
    result = operations.run_operation(operation_id, **parameters)
    _cancel(cancel)
    tree, output_arrays, descriptions = encode_result(result["result"])
    preview_count = [0]

    def preview(node, depth=0):
        preview_count[0] += 1
        if depth > 8 or preview_count[0] > 200:
            return "preview truncated; full result is in the manifest"
        kind = node["kind"]
        if kind == "scalar":
            value = node["value"]
            return (
                value[:240] + "…"
                if isinstance(value, str) and len(value) > 240
                else value
            )
        if kind == "array":
            return {"npz_array": node["name"], **descriptions[node["name"]]}
        if kind == "mapping":
            entries = node["entries"][:20]
            displayed = {
                str(preview(key, depth + 1)): preview(value, depth + 1)
                for key, value in entries
            }
            if len(node["entries"]) > 20:
                displayed["more_entries"] = len(node["entries"]) - 20
            return displayed
        if kind in ("list", "tuple"):
            values = [preview(item, depth + 1) for item in node["items"][:5]]
            return values + (
                [{"more_items": len(node["items"]) - 5}]
                if len(node["items"]) > 5
                else []
            )
        return {
            key: preview(value, depth + 1)
            if isinstance(value, dict) and "kind" in value
            else value
            for key, value in node.items()
        }

    result_preview = preview(tree)
    identity = "core_" + uuid.uuid4().hex
    staging, target = root / (identity + ".partial"), root / identity
    manifest = {
        "schema_version": 1,
        "provenance": result["provenance"],
        "parameters": original,
        "input_archive_sha256": input_hash,
        "result": tree,
        "arrays": descriptions,
        "array_file": "arrays.npz",
        "cancellation": "cooperative"
        if runtime
        else "checked before/after engine; computation itself is not interruptible",
    }
    _cancel(cancel)
    staging.mkdir()
    try:
        if progress:
            progress("Writing a new result bundle")
        np.savez_compressed(staging / "arrays.npz", **output_arrays)
        _cancel(cancel)
        digest = hashlib.sha256()
        with (staging / "arrays.npz").open("rb") as handle:
            while chunk := handle.read(1024**2):
                _cancel(cancel)
                digest.update(chunk)
        manifest["arrays_sha256"] = digest.hexdigest()
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        _cancel(cancel)
        staging.rename(target)
    except Exception as error:
        raise type(error)(
            f"{error}; unpublished partial job retained at {staging}"
        ) from error
    return {
        "folder": str(target),
        "manifest": str(target / "manifest.json"),
        "status": manifest["provenance"]["status"],
        "arrays": descriptions,
        "provenance": manifest["provenance"],
        "preview": result_preview,
    }


def load_core_job(folder):
    """Verify/reconstruct a saved typed result without executing any operation."""
    root = Path(folder).resolve()
    path = root / "manifest.json"
    if path.stat().st_size > 6 * 1024**2:
        raise ValueError("Manifest exceeds size budget")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("array_file") != "arrays.npz"
    ):
        raise ValueError("Unsupported result manifest")
    arrays, digest = _read_arrays(root / "arrays.npz", None)
    if sum(array.nbytes for array in arrays.values()) > MAX_RESULT_BYTES:
        raise ValueError("Saved result exceeds array size budget")
    if digest != manifest["arrays_sha256"]:
        raise ValueError("Result array checksum mismatch")
    count = [0]

    def decode(node, depth=0):
        count[0] += 1
        if depth > 32 or count[0] > 100000:
            raise ValueError("Result structure exceeds budget")
        kind = node["kind"]
        if kind == "scalar":
            value = node["value"]
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("Invalid scalar descriptor")
            return value
        if kind == "array":
            return arrays[node["name"]]
        if kind == "complex":
            return complex(
                decode(node["real"], depth + 1), decode(node["imag"], depth + 1)
            )
        if kind == "nonfinite":
            if node["value"] not in ("nan", "inf", "-inf"):
                raise ValueError("Invalid nonfinite descriptor")
            return float(node["value"])
        if kind == "masked":
            data, mask = (
                decode(node["data"], depth + 1),
                decode(node["mask"], depth + 1),
            )
            if (
                not isinstance(data, np.ndarray)
                or not isinstance(mask, np.ndarray)
                or mask.dtype.kind != "b"
                or data.shape != mask.shape
            ):
                raise ValueError("Invalid masked-array descriptor")
            return np.ma.array(
                data, mask=mask, fill_value=decode(node["fill"], depth + 1)
            )
        if kind == "mapping":
            return {
                decode(key, depth + 1): decode(value, depth + 1)
                for key, value in node["entries"]
            }
        if kind in ("list", "tuple"):
            items = [decode(item, depth + 1) for item in node["items"]]
            return tuple(items) if kind == "tuple" else items
        raise ValueError("Unknown result descriptor")

    return {
        "result": decode(manifest["result"]),
        "provenance": manifest["provenance"],
        "parameters": manifest["parameters"],
    }
