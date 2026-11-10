"""Prepare a single saved channel step without silently substituting versions."""

import ast
import copy

from .survey_store import Formula
from .channel_filters import ChannelFilterOptions


def prepare_channel_step(store, database_id, node):
    if node["database_id"] != database_id:
        raise ValueError("Recipe belongs to another database")
    provenance = node["provenance"]
    operation = provenance.get("operation")
    if operation not in ("formula", "channel_filter"):
        raise ValueError("Only formula and channel-filter steps have connected editors")
    inputs = provenance.get("inputs", {})
    if not inputs:
        raise ValueError("Saved recipe does not identify its input versions")
    current = {row["version_id"]: row for row in store.channels(database_id)}
    if any(version not in current for version in inputs.values()):
        raise ValueError(
            "A saved input version is no longer current; refusing to substitute newer data. Create a new process explicitly instead."
        )
    names = {name: current[version]["name"] for name, version in inputs.items()}
    expected = {names[name]: version for name, version in inputs.items()}
    plan = {
        "operation": operation,
        "expected_versions": expected,
        "source_version": node["id"],
        "unit": provenance.get("unit", node.get("unit", "")),
    }
    if operation == "formula":
        tree = copy.deepcopy(Formula(provenance["expression"]).tree)
        for item in ast.walk(tree):
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "c"
            ):
                item.args[0].value = names[item.args[0].value]
        expression = ast.unparse(tree)
        Formula(expression)
        plan["expression"] = expression
    else:
        parameters = dict(provenance["parameters"])
        for role in ("axis", "group", "sensor"):
            if parameters.get(role):
                parameters[role] = names[parameters[role]]
        options = ChannelFilterOptions(**parameters)
        options.validate()
        # The store serializes inputs in signal, axis, group, sensor order.
        signal = provenance.get("signal", next(iter(inputs)))
        plan.update({"channel": names[signal], "parameters": options.to_dict()})
    return plan
