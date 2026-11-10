"""Synthetic channel-workspace tutorial. No survey or private input required."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from terraworkbench_core.survey_store import SurveyStore
from terraworkbench_core.survey_text_import import inspect_text


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    line = np.repeat(np.arange(4), 100)
    position = np.tile(np.arange(100), 4)
    x, y = 500000 + position * 5.0, 6000000 + line * 25.0
    known = 30 * np.sin(position / 12.0) + line
    raw, offset = known + 5.0, np.full(len(x), 5.0)
    source = output / "synthetic.csv"
    np.savetxt(
        source,
        np.column_stack([line, x, y, raw, offset]),
        delimiter=",",
        header="line,x,y,field_nt,offset_nt",
        comments="",
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    store = SurveyStore(output / "workspace", create=True)
    options, _, _ = inspect_text(source)
    database = store.import_file(source, "Synthetic tutorial", text_options=options)
    store.configure_geometry(database, "x", "y", "EPSG:32618")
    store.rename_channel(database, "field_nt", "field_nt", unit="nT")
    store.rename_channel(database, "offset_nt", "offset_nt", unit="nT")
    store.derive(
        database,
        "corrected_nt",
        'c("field_nt")-c("offset_nt")',
        "nT",
        new_channel_only=True,
    )
    table = pa.Table.from_batches(list(store.batches(database, ["corrected_nt"])))
    corrected = table["corrected_nt"].to_numpy()
    np.testing.assert_allclose(corrected, known, atol=1e-12)
    versions = {
        row["name"]: row["version_id"]
        for row in store.channels(database)
        if row["name"] in ("x", "y")
    }
    store.publish_channels(
        database,
        {"tutorial_selected": (position % 10 == 0).astype(float)},
        units={"tutorial_selected": "code"},
        inputs=versions,
        provenance={
            "operation": "tutorial_selection",
            "parameters": {"every": 10},
            "engine": "NumPy",
            "scope": "artificial points, not field validation",
        },
    )
    store.export_csv(
        database,
        ["line", "x", "y", "corrected_nt", "tutorial_selected"],
        output / "corrected.csv",
    )
    (output / "pipeline.json").write_text(
        json.dumps(store.channel_pipeline(database, "corrected_nt"), indent=2)
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    result = {
        "kind": "synthetic tutorial",
        "database_id": database,
        "rows": len(x),
        "max_formula_error_nt": float(np.max(abs(corrected - known))),
        "original_unchanged": True,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
