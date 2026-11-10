"""A killed writer may leave scratch bytes but must never publish a channel."""

import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from terraworkbench_core.survey_store import SurveyStore


def test_abrupt_exit_during_derive_keeps_catalog_readable_and_retry_safe(tmp_path):
    source = tmp_path / "source.parquet"
    pq.write_table(pa.table({"mag": np.arange(150_000, dtype=float)}), source)
    original = source.read_bytes()
    store = SurveyStore(tmp_path / "workspace", create=True)
    database = store.import_file(source)
    channels, history = store.channels(database), store.history(database)
    script = """
import os, sys
sys.path.insert(0, sys.argv[1])
from terraworkbench_core.survey_store import SurveyStore
store = SurveyStore(sys.argv[2])
store.derive(sys.argv[3], 'unfinished', 'c("mag") + 1', progress=lambda count: os._exit(73))
"""
    child = subprocess.run(
        [
            sys.executable,
            "-I", "-B",
            "-c",
            script,
            str(Path(__file__).resolve().parents[1]),
            str(store.root),
            database,
        ],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=60,
    )
    assert child.returncode == 73
    reopened = SurveyStore(store.root)
    assert (
        reopened.channels(database) == channels
        and reopened.history(database) == history
    )
    assert list(store.root.rglob("*.partial"))  # retained, never treated as a channel
    reopened.derive(database, "unfinished", 'c("mag") + 1')
    values = pa.Table.from_batches(list(reopened.batches(database, ["unfinished"])))
    np.testing.assert_array_equal(
        values["unfinished"].to_numpy(), np.arange(150_000) + 1
    )
    assert source.read_bytes() == original
