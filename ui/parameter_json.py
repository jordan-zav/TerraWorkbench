"""Bounded, strict parameter/manifest decoding without Qt or scientific engines."""

import json
from pathlib import Path

MAX_FILE_BYTES = 6 * 1024**2
MAX_PARAMETER_BYTES = 1024**2


class ParameterJSONError(ValueError):
    pass


def _unique(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ParameterJSONError("duplicate_keys")
        result[name] = value
    return result


def _invalid_constant(_):
    raise ParameterJSONError("nonfinite")


def read_parameter_json(path, operation_id):
    """Return reviewed object and bounded pretty JSON; never executes a recipe."""
    source = Path(path)
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ParameterJSONError("file_budget")
    with source.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ParameterJSONError("file_budget")
    try:
        data = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=_unique,
            parse_constant=_invalid_constant,
        )
    except ParameterJSONError:
        raise
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ParameterJSONError("invalid_json") from error
    if not isinstance(data, dict):
        raise ParameterJSONError("object_required")
    if "provenance" in data and "parameters" in data:
        provenance = data["provenance"]
        if (
            not isinstance(provenance, dict)
            or provenance.get("operation_id") != operation_id
        ):
            raise ParameterJSONError("wrong_operation")
        data = data["parameters"]
    if not isinstance(data, dict):
        raise ParameterJSONError("object_required")
    try:
        encoded = json.dumps(data, indent=2, allow_nan=False)
    except RecursionError as error:
        # Some runtimes decode deeper JSON than the pretty encoder can handle.
        # Keep nesting failures distinct from nonfinite numeric values.
        raise ParameterJSONError("invalid_json") from error
    except ValueError as error:
        raise ParameterJSONError("nonfinite") from error
    if len(encoded.encode("utf-8")) > MAX_PARAMETER_BYTES:
        raise ParameterJSONError("parameter_budget")
    return data, encoded
