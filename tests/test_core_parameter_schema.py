"""Presentation coverage and validation without importing QGIS."""

import ast
import importlib.util
import inspect
from pathlib import Path
import sys
import struct
from zipfile import ZipFile

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema = load("tw_core_schema", "ui/core_parameter_schema.py")
inspector = load("tw_npz_inspector", "ui/npz_inspector.py")


def test_generic_form_without_operation_keeps_scalar_fields():
    parameter = inspect.Parameter(
        "chargeability", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=0.1
    )
    assert schema.field_kind(None, parameter) == "number"
    assert schema.field_kind("ip.dispersive_forward", parameter) == "json"
    assert schema.field_kind("ip.dispersive_inverse", parameter) == "json"
    assert schema.choices_for(None, "normalization") == ()


def registered_functions():
    tree = ast.parse(
        (ROOT / "terraworkbench_core/operations.py").read_text(encoding="utf-8")
    )
    registry = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_OPERATIONS" for t in n.targets)
    )
    for key, (module, function, *_) in registry.items():
        tree = ast.parse(
            (ROOT / "terraworkbench_core" / (module + ".py")).read_text(
                encoding="utf-8"
            )
        )
        node = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == function
        )
        yield key, [arg.arg for arg in node.args.args + node.args.kwonlyargs]


def test_every_registered_argument_has_authored_labels_in_all_languages():
    for operation_id, names in registered_functions():
        for name in names:
            if name in ("cancel", "canceled", "cancelled"):
                continue
            for locale in schema.LANGUAGES:
                assert schema.parameter_label(name, locale), (
                    operation_id,
                    name,
                    locale,
                )


@pytest.mark.parametrize(
    "kind,value",
    [
        ("number", True),
        ("integer", 3.0),
        ("integer", 2.1),
        ("number", float("nan")),
        ("number", float("inf")),
        ("number", 10**400),
        ("boolean", 1),
        ("string", 2),
    ],
)
def test_scalar_validation_rejects_coercion_and_nonfinite_values(kind, value):
    with pytest.raises(ValueError):
        schema.validate_scalar(kind, value)


def test_npz_header_inspection_preserves_shapes_without_pickle(tmp_path):
    path = tmp_path / "arrays.npz"
    np.savez(
        path,
        traces=np.zeros((4, 32)),
        complex=np.ones(3, dtype=complex),
        mask=np.ones(3, dtype=bool),
    )
    result = inspector.describe_npz(path)
    assert result["traces"]["shape"] == (4, 32)
    assert result["complex"]["dtype"] == "complex128"
    assert result["mask"]["dtype"] == "bool"
    np.savez(path, dangerous=np.array([{}], dtype=object))
    with pytest.raises(ValueError, match="Object arrays"):
        inspector.describe_npz(path)


def test_forwarded_euler_options_are_visible_without_changing_public_signature():
    name = "tw_source_depth_schema_probe"
    module = load(name, "terraworkbench_core/source_depth.py")
    sys.modules[name] = module
    try:
        original = inspect.signature(module.euler_window)
        expanded = schema.presentation_signature(
            module.euler_window, "depth.euler_window"
        )
        assert "structural_index" in expanded.parameters
        assert (
            expanded.parameters["structural_index"].default is inspect.Parameter.empty
        )
        assert "max_relative_depth_error" in expanded.parameters
        assert inspect.signature(module.euler_window) == original
    finally:
        sys.modules.pop(name, None)


def test_only_verified_waveform_relationships_are_checked():
    for parameters in (
        {"dt_s": -1},
        {"window_samples": 4},
        {"window_samples": 7, "traces": [[1, 2, 3]]},
    ):
        with pytest.raises(ValueError):
            schema.validate_relationships("gpr.dewow", parameters)
    with pytest.raises(ValueError, match="nyquist"):
        schema.validate_relationships(
            "waveform.bandpass", {"dt_s": 0.1, "low_hz": 1, "high_hz": 7}
        )
    schema.validate_relationships(
        "gpr.dewow", {"dt_s": 0.01, "window_samples": 3, "traces": [[1, 2, 3, 4]]}
    )


@pytest.mark.parametrize("method", ["euler", "werner", "spi"])
def test_grid_method_options_exclude_inputs_already_supplied_by_facade(method):
    name = "tw_grid_depth_schema_probe"
    module = load(name, "terraworkbench_core/source_depth.py")
    sys.modules[name] = module
    try:
        original = inspect.signature(module.interpret_grid)
        operation_id, signature = schema.depth_grid_options(module, method)
        fields = signature.parameters
        assert not set(fields).intersection(
            {
                "x",
                "y",
                "elevation",
                "field",
                "gradient_x",
                "gradient_y",
                "gradient_z",
                "distance",
                "observation_elevation",
                "second_x",
                "cross_xz",
                "canceled",
            }
        )
        if method == "euler":
            assert fields["structural_index"].default is inspect.Parameter.empty
            assert "max_relative_depth_error" in fields
        elif method == "werner":
            assert "background_degree" in fields and "structural_index" not in fields
        else:
            assert "source_model" in fields and "window_size" not in fields
            assert schema.choices_for(operation_id, "source_model")
        for parameter in fields.values():
            if parameter.kind != inspect.Parameter.VAR_KEYWORD:
                assert all(
                    schema.parameter_label(parameter.name, lang)
                    for lang in schema.LANGUAGES
                )
        assert inspect.signature(module.interpret_grid) == original
        with pytest.raises(ValueError):
            schema.depth_grid_options(module, "unknown")
    finally:
        sys.modules.pop(name, None)


def test_malicious_header_size_is_rejected_before_reading_payload(tmp_path):
    path = tmp_path / "header.npz"
    with ZipFile(path, "w") as bundle:
        bundle.writestr("x.npy", b"\x93NUMPY\x02\x00" + struct.pack("<I", 2**31))
    with pytest.raises(ValueError, match="header exceeds"):
        inspector.describe_npz(path)
    with ZipFile(path, "w") as bundle:
        bundle.writestr("x.npy", b"\x93NUMPY\x01\x00\x01")
    with pytest.raises(ValueError, match="Truncated"):
        inspector.describe_npz(path)
