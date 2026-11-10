"""Offline provenance checks; CI never downloads the public survey archives."""

import hashlib
import io
import json
import zipfile

import numpy as np
import pytest

from scripts import benchmark_public_processing as benchmark


def source(payload):
    return dict(
        filename="field.csv",
        url="https://example.invalid/field.csv",
        bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_fetch_checks_cache_and_does_not_overwrite_tampered_inputs(
    tmp_path, monkeypatch
):
    payload = b"x,y,mag\n1,2,3\n"
    calls = []

    def download(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(payload)

    monkeypatch.setattr(benchmark, "urlopen", download)
    item = source(payload)
    path = benchmark.fetch(tmp_path, item)
    assert path.read_bytes() == payload
    assert len(calls) == 1
    benchmark.fetch(tmp_path, item, offline=True)
    assert len(calls) == 1
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Cached checksum"):
        benchmark.fetch(tmp_path, item)
    assert path.read_bytes() == b"corrupt" and len(calls) == 1


def test_fetch_rejects_wrong_download_and_preserves_diagnostic_bytes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(benchmark, "urlopen", lambda *a, **k: io.BytesIO(b"wrong"))
    with pytest.raises(ValueError, match="Downloaded checksum"):
        benchmark.fetch(tmp_path, source(b"right"))
    assert (tmp_path / "field.csv").read_bytes() == b"wrong"
    with pytest.raises(FileNotFoundError, match="Offline cache"):
        benchmark.fetch(tmp_path / "other", source(b"right"), offline=True)


def test_named_zip_reader_never_extracts_and_rejects_oversized_members(tmp_path):
    path = tmp_path / "spectra.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape.txt", b"do not extract")
        archive.writestr("Data/spectrum.csv", b"energy,counts\n1,4\n")
    assert benchmark.member_bytes(path, "Data/spectrum.csv").startswith(b"energy")
    assert not (tmp_path / "escape.txt").exists()
    with pytest.raises(ValueError, match="budget"):
        benchmark.member_bytes(path, "Data/spectrum.csv", maximum=1)


def test_reference_comparison_rejects_validity_and_shape_mismatch():
    with pytest.raises(AssertionError, match="mask"):
        benchmark.compare([1.0, np.nan], [1.0, 2.0], atol=1e-6)
    with pytest.raises(AssertionError, match="shape"):
        benchmark.compare([1.0], [[1.0]], atol=1e-6)
    assert not benchmark.compare([1.0], [2.0], atol=0.1)["passed"]


def test_public_evidence_keeps_metrics_and_provenance_without_cache_locations():
    private = {
        "status": "passed",
        "datasets": {
            "field": {
                "sha256": "abc",
                "cache_path": ("D" + ":/private/cache/file"),
                "url": "https://example.invalid/file",
            }
        },
        "cases": {"gravity": {"max_abs_error": 1e-8}},
    }
    public = benchmark.publication_report(private)
    assert "private" not in json.dumps(public)
    assert public["datasets"]["field"]["sha256"] == "abc"
    assert public["cases"] == private["cases"]
    assert "cache_path" in private["datasets"]["field"]
    with pytest.raises(ValueError, match="completed"):
        benchmark.publication_report({"status": "running"})


def test_campaign_records_failed_case_and_runs_remaining_cases(tmp_path, monkeypatch):
    manifest = tmp_path / "sources.json"
    manifest.write_text("{}")
    monkeypatch.setattr(benchmark, "MANIFEST", manifest)
    monkeypatch.setattr(benchmark, "CASE_DATASETS", {"bad": (), "good": ()})

    def fail(paths, output):
        raise ArithmeticError("reference mismatch")

    monkeypatch.setattr(
        benchmark,
        "CASES",
        {
            "bad": fail,
            "good": lambda paths, output: {"passed": True},
        },
    )
    output = tmp_path / "run"
    result = benchmark.run(tmp_path / "cache", output, offline=True)
    saved = json.loads((output / "report.json").read_text())
    assert result["status"] == saved["status"] == "failed"
    assert saved["cases"]["good"]["status"] == "passed"
    assert "ArithmeticError" in saved["cases"]["bad"]["error"]
    public = json.loads((output / "report.public.json").read_text())
    assert public["status"] == "failed"
    assert public["cases"]["bad"]["status"] == "failed"
    assert public["cases"]["good"]["status"] == "passed"
    assert saved["source_sha256"][
        "terraworkbench_core/radiometry.py"
    ] == benchmark.digest(benchmark.ROOT / "terraworkbench_core/radiometry.py")
    with pytest.raises(FileExistsError):
        benchmark.run(tmp_path / "cache", output, offline=True)


def test_failed_publication_keeps_metrics_and_redacts_exception_paths():
    source = {
        "status": "failed",
        "datasets": {},
        "cases": {
            "bad": {"error": "FileNotFoundError('" + "D" + ":/private/cache/file')", "rmse": 4.5}
        },
    }
    public = benchmark.publication_report(source)
    assert public["cases"]["bad"]["rmse"] == 4.5
    assert ("D" + ":/private") not in json.dumps(public)
    assert source["cases"]["bad"]["error"].startswith("FileNotFoundError")
