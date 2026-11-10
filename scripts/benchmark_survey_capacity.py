"""Reproducible synthetic storage/filter campaign; never reads private surveys.

Requires installed storage extra and psutil for sampled process RSS. Output must
be a new directory. Each stage checkpoints metrics, assertions and source hashes.
No timing threshold is presented as a portable performance guarantee.
"""

import argparse
from contextlib import contextmanager
import hashlib
import inspect
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import threading
import time

import numpy as np
import psutil
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terraworkbench_core.channel_filters import ChannelFilterOptions  # noqa: E402
from terraworkbench_core.survey_store import SurveyStore  # noqa: E402


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def run(output, rows, transects, extra_channels):
    if not 8 <= rows <= 50_000_000 or not 1 <= transects <= min(rows // 8, 32767):
        raise ValueError("Require 8..50M rows and at least 8 rows per transect")
    if not 0 <= extra_channels <= 32:
        raise ValueError("Extra channels must be 0..32")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "running",
        "rows": rows,
        "transects": transects,
        "extra_channels": extra_channels,
        "stages": [],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{name: version(name) for name in ("numpy", "scipy", "pyarrow", "psutil")},
        },
        "memory_scope": "Process RSS sampled every 20 ms, not a hard maximum; excludes OS file cache",
        "core_sources_sha256": {
            Path(inspect.getsourcefile(implementation)).name: digest(
                Path(inspect.getsourcefile(implementation))
            )
            for implementation in (SurveyStore, ChannelFilterOptions)
        },
    }
    process = psutil.Process()

    def checkpoint():
        (output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

    @contextmanager
    def stage(name):
        item = {
            "name": name,
            "status": "running",
            "rss_start_bytes": process.memory_info().rss,
        }
        report["stages"].append(item)
        checkpoint()
        peak = [item["rss_start_bytes"]]
        stop = threading.Event()

        def sample():
            while not stop.wait(0.02):
                peak[0] = max(peak[0], process.memory_info().rss)

        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        started = time.perf_counter()
        try:
            yield item
            item["status"] = "passed"
        except BaseException as error:
            item["status"] = report["status"] = "failed"
            item["error"] = repr(error)
            raise
        finally:
            stop.set()
            monitor.join()
            item["seconds"] = time.perf_counter() - started
            item["sampled_peak_rss_bytes"] = max(peak[0], process.memory_info().rss)
            checkpoint()
            print(json.dumps(item), flush=True)

    source = output / "synthetic.parquet"
    with stage("generate"):
        writer = None
        try:
            for start in range(0, rows, 65536):
                index = np.arange(start, min(start + 65536, rows), dtype=np.int64)
                line = index * transects // rows
                first = (line * rows + transects - 1) // transects
                local = (index - first).astype(float)
                values = {
                    "row": index,
                    "line": line.astype(np.int16),
                    "time": local,
                    "mag": 50000.0
                    + line * 1000.0
                    + local * 0.001
                    + 2 * np.sin(2 * np.pi * local / 101),
                    "base": np.full(len(index), 5.0),
                    **{
                        f"aux_{i}": np.cos(index * (0.0001 + i * 0.00001))
                        for i in range(extra_channels)
                    },
                }
                table = pa.table(values)
                if writer is None:
                    writer = pq.ParquetWriter(source, table.schema, compression="zstd")
                writer.write_table(table, row_group_size=65536)
        finally:
            if writer is not None:
                writer.close()
        report["source_sha256"] = digest(source)
        report["source_bytes"] = source.stat().st_size

    store = SurveyStore(output / "workspace", create=True)
    with stage("import") as item:
        database = store.import_file(source)
        report["database_id"] = database
        assert store.databases()[0]["rows"] == rows

    for names in (["mag"], ["mag", "base"], list(pq.read_schema(source).names)):
        with stage("read_" + str(len(names)) + "_channels") as item:
            seen, maximum = 0, 0
            for batch in store.batches(database, names):
                assert batch.schema.names == names
                seen += len(batch)
                maximum = max(maximum, len(batch))
            assert seen == rows and maximum <= 65536
            item.update(rows_read=seen, maximum_batch_rows=maximum)

    with stage("derive"):
        store.derive(database, "corrected", 'c("mag") - c("base")', unit="nT")
        for batch in store.batches(database, ["mag", "base", "corrected"]):
            a, b, c = [batch.column(i).to_numpy() for i in range(3)]
            np.testing.assert_array_equal(c, a - b)

    with stage("cancel_mid_derive") as item:
        canceled = [False]
        requested = [None]

        def progress(count):
            if count >= min(131072, rows):
                canceled[0], requested[0] = True, time.perf_counter()

        channels = store.channels(database)
        try:
            store.derive(
                database,
                "cancelled",
                'c("mag") + 1',
                canceled=lambda: canceled[0],
                progress=progress,
            )
        except InterruptedError:
            item["cancel_latency_seconds"] = time.perf_counter() - requested[0]
        else:
            raise AssertionError("Cancellation did not interrupt publication")
        assert store.channels(database) == channels
        assert not list(store.root.rglob("*.partial"))

    with stage("mean_filter") as item:
        options = ChannelFilterOptions(
            method="mean", window=5, domain="time", axis="time", group="line"
        )
        stats = store.filter_channel(database, "corrected", "mean_w5", options)
        assert stats["rows"] == rows and stats["segments"] == transects
        assert stats["output_null_rows"] == 4 * transects
        item["statistics"] = stats

    with stage("verify_every_filtered_row") as item:
        error, seen = 0.0, 0
        omega = 2 * np.pi / 101
        gain = (1 + 2 * np.cos(omega) + 2 * np.cos(2 * omega)) / 5
        for batch in store.batches(database, ["row", "line", "time", "mean_w5"]):
            index, line, local, actual = [
                batch.column(i).to_numpy(zero_copy_only=False) for i in range(4)
            ]
            line = line.astype(np.int64)
            lengths = ((line + 1) * rows + transects - 1) // transects - (
                line * rows + transects - 1
            ) // transects
            valid = (local >= 2) & (local < lengths - 2)
            assert np.array_equal(np.isfinite(actual), valid)
            expected = (
                49995.0
                + line * 1000.0
                + local * 0.001
                + 2 * gain * np.sin(omega * local)
            )
            error = max(
                error, float(np.max(np.abs(actual[valid] - expected[valid]), initial=0))
            )
            seen += len(index)
        assert seen == rows and error < 1e-8
        item["max_abs_error_nt"] = error

    with stage("reopen_selection_export") as item:
        reopened = SurveyStore(store.root)
        selected = reopened.export_csv(
            database,
            ["row", "mean_w5"],
            output / "first_line.csv",
            filters={"line": [0]},
        )
        assert selected == (rows + transects - 1) // transects
        graph = reopened.channel_pipeline(database, "mean_w5")
        assert len(graph["edges"]) >= 3
        assert digest(source) == report["source_sha256"]
        item["exported_rows"] = selected
    report["status"] = "passed"
    report["workspace_bytes"] = sum(
        p.stat().st_size for p in store.root.rglob("*") if p.is_file()
    )
    checkpoint()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--transects", type=int, default=30)
    parser.add_argument("--extra-channels", type=int, default=8)
    args = parser.parse_args()
    run(args.output, args.rows, args.transects, args.extra_channels)


if __name__ == "__main__":
    main()
