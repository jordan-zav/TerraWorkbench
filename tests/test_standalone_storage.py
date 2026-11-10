"""Standalone storage/import migration preserves wrappers and persisted format."""

import json

import numpy as np
import pyarrow as pa

from terraworkbench_core.survey_store import SurveyStore
from terraworkbench_core.survey_text_import import ColumnSpec, TextImportOptions


def test_standalone_storage_typed_import_geometry_channel_lineage(tmp_path):
    source = tmp_path / "survey.txt"
    source.write_text(
        "line;x;y;signal;base\n001;500000;4000000;100;5\n002;500001;4000001;110;6\n",
        encoding="utf-8",
    )
    options = TextImportOptions(
        delimiter=";",
        columns=[
            ColumnSpec("line"),
            ColumnSpec("x", "float", role="x", unit="m"),
            ColumnSpec("y", "float", role="y", unit="m"),
            ColumnSpec("signal", "float", unit="nT"),
            ColumnSpec("base", "float", unit="nT"),
        ],
    )
    original = source.read_bytes()
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(source, text_options=options)
    store.configure_geometry(database, "x", "y", "EPSG:32618")
    store.derive(database, "signal_corrected", 'c("signal")-c("base")', unit="nT")
    reopened = SurveyStore(store.root)
    actual = pa.Table.from_batches(
        list(reopened.batches(database, ["line", "signal_corrected"], batch_size=1))
    ).to_pydict()
    assert actual == {"line": ["001", "002"], "signal_corrected": [95.0, 104.0]}
    geometry = json.loads(reopened.databases()[0]["metadata"])["geometry"]
    assert geometry["crs"] == "EPSG:32618"
    selected = pa.Table.from_batches(
        list(
            reopened.batches(database, ["signal_corrected"], filters={"line": ["002"]})
        )
    )
    np.testing.assert_array_equal(selected.column(0).to_numpy(), [104.0])
    assert source.read_bytes() == original
    pipeline = reopened.channel_pipeline(database, "signal_corrected")
    assert pipeline
    assert any(
        row["provenance"].get("operation") == "formula"
        for row in pipeline["nodes"].values()
    )
    assert len(pipeline["edges"]) == 2


def test_legacy_storage_and_parser_objects_are_same_implementation():
    import compat.survey_store as survey_store
    import compat.survey_grid_pipeline as survey_grid_pipeline
    import compat.text_import as text_import
    from terraworkbench_core.survey_grid_pipeline import run_magnetic_grid_pipeline

    assert survey_store.SurveyStore is SurveyStore
    assert text_import.TextImportOptions is TextImportOptions
    assert text_import.ColumnSpec is ColumnSpec
    assert survey_grid_pipeline.run_magnetic_grid_pipeline is run_magnetic_grid_pipeline


def test_historical_table_inspection_api_is_not_replaced(tmp_path):
    from terraworkbench_core import text_import as tables
    from terraworkbench_core import survey_text_import as surveys

    source = tmp_path / "table.csv"
    source.write_text("x,y,value\n1,2,3\n4,5,6\n", encoding="utf-8")
    info = tables.inspect_text(source, separator="comma")
    assert info["columns"] == ["x", "y", "value"]
    assert info["sep"] == ","
    assert callable(tables.read_text_table) and callable(tables.csv_options)
    assert surveys.inspect_text is not tables.inspect_text
