"""Advanced jobs: safe artifacts, real kernels, resource guards and no overwrite."""

from io import BytesIO
import hashlib
import json
from zipfile import ZipFile

import numpy as np
import pytest

from terraworkbench_core import operation_jobs as jobs


def test_job_runs_real_kernel_and_preserves_npz_input(tmp_path):
    source = tmp_path / "input.npz"
    np.savez(source, traces=np.arange(40.0).reshape(2, 20))
    original = source.read_bytes()
    text = json.dumps(
        {"traces": {"$array": "traces"}, "dt_s": 0.01, "window_samples": 3}
    )
    result = jobs.run_core_job("gpr.dewow", text, tmp_path, input_npz=source)
    manifest = json.loads((tmp_path / result["folder"] / "manifest.json").read_text())
    assert result["status"] == "completed"
    assert manifest["input_archive_sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["provenance"]["source_sha256"]
    output = tmp_path / result["folder"] / "arrays.npz"
    assert hashlib.sha256(output.read_bytes()).hexdigest() == manifest["arrays_sha256"]
    with np.load(output, allow_pickle=False) as archive:
        assert len(archive.files) == 2
        arrays = [archive[name] for name in archive.files]
        np.testing.assert_allclose(
            arrays[0] + arrays[1], np.arange(40.0).reshape(2, 20)
        )
    assert source.read_bytes() == original
    loaded = jobs.load_core_job(result["folder"])
    np.testing.assert_allclose(
        loaded["result"]["traces"] + loaded["result"]["removed_trend"],
        np.arange(40.0).reshape(2, 20),
    )
    another = jobs.run_core_job("gpr.dewow", text, tmp_path, input_npz=source)
    assert another["folder"] != result["folder"]
    with ZipFile(output, "a") as archive:
        archive.writestr("tamper.npy", b"invalid")
    with pytest.raises((ValueError, EOFError)):
        jobs.load_core_job(result["folder"])


def test_parameter_parser_rejects_unsafe_or_ambiguous_values():
    for text in (
        '{"x": NaN}',
        '{"x": 1e999}',
        '{"x": 1, "x": 2}',
        "[]",
        '{"x": {"$array": "missing"}}',
    ):
        with pytest.raises(ValueError):
            jobs.parse_job_parameters(text, {})
    array = np.arange(5.0)
    original, resolved = jobs.parse_job_parameters(
        '{"x": {"$array":"x"}, "nested": [true, null]}', {"x": array}
    )
    assert resolved["x"] is array
    assert original["x"] == {"$array": "x"}


def test_npz_rejects_pickle_and_declared_allocation_bomb(tmp_path):
    path = tmp_path / "unsafe.npz"
    np.savez(path, bad=np.array([object()], dtype=object))
    with pytest.raises(ValueError, match="Unsafe"):
        jobs._read_arrays(path, None)
    header = BytesIO()
    np.lib.format.write_array_header_1_0(
        header, {"descr": "<f8", "fortran_order": False, "shape": (10**12,)}
    )
    with ZipFile(tmp_path / "bomb.npz", "w") as archive:
        archive.writestr("huge.npy", header.getvalue())
    with pytest.raises(ValueError, match="declared array sizes"):
        jobs._read_arrays(tmp_path / "bomb.npz", None)


def test_result_encoding_preserves_complex_masks_nonfinite_and_key_types():
    masked = np.ma.array([1.0, 2.0], mask=[False, True])
    tree, arrays, descriptions = jobs.encode_result(
        {
            1: np.array([1 + 2j]),
            "masked": masked,
            "scalar": float("nan"),
            "tuple": (3, 4),
        }
    )
    text = json.dumps(tree, allow_nan=False)
    assert '"masked"' in text and '"nonfinite"' in text and '"tuple"' in text
    assert any(array.dtype.kind == "c" for array in arrays.values())
    assert any(array.dtype.kind == "b" for array in arrays.values())
    assert any(
        "magnitude_statistics" in description for description in descriptions.values()
    )
    with pytest.raises(ValueError):
        jobs.encode_result(np.array([object()], dtype=object))


def test_cancel_never_publishes_a_job(tmp_path):
    with pytest.raises(InterruptedError):
        jobs.run_core_job("gpr.dewow", "{}", tmp_path, cancel=lambda: True)
    assert list(tmp_path.iterdir()) == []


def test_nonconvergence_status_is_not_relabelled_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        jobs.operations,
        "run_operation",
        lambda *args, **kwargs: {
            "result": {"success": False, "model": np.ones(3)},
            "provenance": {"status": "not_converged"},
        },
    )
    result = jobs.run_core_job(
        "gpr.dewow", '{"traces": [[1,2,3,4]], "dt_s": 1, "window_samples": 3}', tmp_path
    )
    assert result["status"] == "not_converged"


def test_complex_and_masked_result_roundtrip(tmp_path, monkeypatch):
    values = {
        "phase": np.array([1 + 2j, -3 + 4j]),
        "masked": np.ma.array([1.0, 999.0], mask=[False, True]),
    }
    monkeypatch.setattr(
        jobs.operations,
        "run_operation",
        lambda *args, **kwargs: {
            "result": values,
            "provenance": {"status": "completed"},
        },
    )
    result = jobs.run_core_job(
        "gpr.dewow", '{"traces": [[1,2,3,4]], "dt_s": 1, "window_samples": 3}', tmp_path
    )
    loaded = jobs.load_core_job(result["folder"])["result"]
    np.testing.assert_array_equal(loaded["phase"], values["phase"])
    np.testing.assert_array_equal(loaded["masked"].mask, [False, True])
    assert any(
        description.get("masked_values_excluded")
        and description["statistics"]["mean"] == 1
        for description in result["arrays"].values()
    )
