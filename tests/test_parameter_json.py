"""Strict, bounded recipe-file decoding without QGIS."""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "tw_parameter_json", Path(__file__).resolve().parents[1] / "ui/parameter_json.py"
)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


@pytest.mark.parametrize("manifest", [False, True])
def test_parameter_files_and_manifests_with_bom_are_read_only(tmp_path, manifest):
    parameters = {"text": "Información", "nullable": None, "x": {"$array": "positions"}}
    content = (
        {"provenance": {"operation_id": "chosen"}, "parameters": parameters}
        if manifest
        else parameters
    )
    raw = json.dumps(content, ensure_ascii=False).encode("utf-8-sig")
    source = tmp_path / "recipe.json"
    source.write_bytes(raw)
    actual, encoded = parser.read_parameter_json(source, "chosen")
    assert actual == parameters and json.loads(encoded) == parameters
    assert source.read_bytes() == raw


@pytest.mark.parametrize(
    "raw,code",
    [
        (b'{"x": 1, "x": 2}', "duplicate_keys"),
        (b'{"x": {"k": 1, "k": 2}}', "duplicate_keys"),
        (b'{"x": NaN}', "nonfinite"),
        (b'{"x": Infinity}', "nonfinite"),
        (b'{"x": 1e400}', "nonfinite"),
        (b"[]", "object_required"),
        (b'{"provenance": [], "parameters": {}}', "wrong_operation"),
        (
            b'{"provenance": {"operation_id": "other"}, "parameters": {}}',
            "wrong_operation",
        ),
        (
            b'{"provenance": {"operation_id": "chosen"}, "parameters": []}',
            "object_required",
        ),
        (b"\xff", "invalid_json"),
        (b"{", "invalid_json"),
        (b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}", "invalid_json"),
    ],
)
def test_invalid_files_are_rejected(tmp_path, raw, code):
    source = tmp_path / "recipe.json"
    source.write_bytes(raw)
    with pytest.raises(parser.ParameterJSONError, match=code):
        parser.read_parameter_json(source, "chosen")


def test_file_growth_is_bounded_even_if_stat_was_small(monkeypatch):
    class Stream(io.BytesIO):
        def read(self, size):
            assert size == 33
            return super().read(size)

    source = SimpleNamespace(
        stat=lambda: SimpleNamespace(st_size=1), open=lambda mode: Stream(b" " * 200)
    )
    monkeypatch.setattr(parser, "Path", lambda _: source)
    monkeypatch.setattr(parser, "MAX_FILE_BYTES", 32)
    with pytest.raises(parser.ParameterJSONError, match="file_budget"):
        parser.read_parameter_json("recipe.json", "chosen")


def test_parameter_budget_is_checked_after_manifest_extraction(tmp_path, monkeypatch):
    source = tmp_path / "recipe.json"
    source.write_text(
        json.dumps(
            {"provenance": {"operation_id": "chosen"}, "parameters": {"x": [1] * 20}}
        )
    )
    monkeypatch.setattr(parser, "MAX_PARAMETER_BYTES", 32)
    with pytest.raises(parser.ParameterJSONError, match="parameter_budget"):
        parser.read_parameter_json(source, "chosen")


def test_file_size_preflight(tmp_path, monkeypatch):
    source = tmp_path / "recipe.json"
    source.write_bytes(b" " * 33)
    monkeypatch.setattr(parser, "MAX_FILE_BYTES", 32)
    with pytest.raises(parser.ParameterJSONError, match="file_budget"):
        parser.read_parameter_json(source, "chosen")
