"""Run the capacity CLI so provenance/path errors cannot hide behind imports."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_capacity_command_records_actual_core_sources_and_completes(tmp_path):
    pytest.importorskip("pyarrow")
    pytest.importorskip("psutil")
    output = tmp_path / "capacity"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/benchmark_survey_capacity.py"),
            "--output",
            str(output),
            "--rows",
            "1024",
            "--transects",
            "4",
            "--extra-channels",
            "2",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "passed"
    assert all(stage["status"] == "passed" for stage in report["stages"])
    assert set(report["core_sources_sha256"]) == {
        "survey_store.py",
        "channel_filters.py",
    }
    for name, expected in report["core_sources_sha256"].items():
        actual = hashlib.sha256(
            (ROOT / "terraworkbench_core" / name).read_bytes()
        ).hexdigest()
        assert actual == expected
