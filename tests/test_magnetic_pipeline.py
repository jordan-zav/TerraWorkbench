import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from magnetic_pipeline import MagneticPipelineOptions, magnetic_grid_products, line_correction_surface
from spectral import prepare_fft_grid, finish_fft_grid
from survey_store import SurveyStore


def options(**kwargs):
    return MagneticPipelineOptions(90., 0., padding_rows=0, padding_columns=0, **kwargs)


def test_prepare_preserves_mask_and_exact_padding():
    values = np.arange(20., dtype=float).reshape(4, 5)
    values[1, 2] = np.nan
    prepared, state = prepare_fft_grid(values, -1, 0, 0, padding_cells=(2, 3))
    assert prepared.shape == (8, 11) and np.isfinite(prepared).all()
    restored = finish_fft_grid(prepared, state, False)
    np.testing.assert_allclose(restored, values, equal_nan=True)
    with pytest.raises(ValueError):
        prepare_fft_grid(values, nodata_policy="reject")
    with pytest.raises(ValueError):
        prepare_fft_grid(np.full((4, 4), np.nan))


def test_retained_fft_chain_analytical_derivatives_and_units():
    yy, xx = np.indices((32, 32))
    k = 2 * np.pi / 32
    field = np.sin(k * xx) + np.cos(k * yy)
    products, recipe = magnetic_grid_products(field, (1., 1.), options(continuation_height=2.))
    np.testing.assert_allclose(products["RTP"], field, atol=1e-12)
    np.testing.assert_allclose(products["DX"], k * np.cos(k * xx), atol=1e-12)
    np.testing.assert_allclose(products["DZ_1VD"], -k * field, atol=1e-12)
    np.testing.assert_allclose(products["UC"], np.exp(-k * 2) * field, atol=1e-12)
    deg, _ = magnetic_grid_products(field, (1., 1.), options(angle_units="degrees"))
    np.testing.assert_allclose(deg["Tilt"], np.degrees(products["Tilt"]), atol=1e-10)
    assert recipe["parameters"]["derivative_method"] == "fft"


def test_mask_methods_cancellation_and_validation():
    values = np.arange(48.).reshape(6, 8)
    values[2, 3] = np.nan
    for method in ("fft", "finite_difference"):
        products, _ = magnetic_grid_products(values, (2., 2.), options(derivative_method=method))
        for value in products.values():
            np.testing.assert_array_equal(np.isnan(value), np.isnan(values))
    with pytest.raises(InterruptedError):
        magnetic_grid_products(values, (2., 2.), options(), lambda: True)
    with pytest.raises(ValueError):
        options(angle_units="unknown").validate()
    with pytest.raises(ValueError):
        magnetic_grid_products(values, (-1., 2.), options())


def test_correction_surface_across_batches_and_support():
    data = pa.table({"x": [0., 1, 2, 3, 0, 1, 2, 3], "y": [0.] * 4 + [3.] * 4,
                     "line": ["a"] * 4 + ["b"] * 4, "correction": [5.] * 8})
    support = np.ones((4, 4), dtype=bool)
    support[1, 2] = False
    surface, info = line_correction_surface(data.to_batches(max_chunksize=3), "x", "y", "line", "correction",
                                            np.arange(4), np.arange(4), support)
    np.testing.assert_allclose(surface[support], 5)
    assert np.isnan(surface[1, 2]) and info["lines"] == 2 and info["source_rows"] == 8
    bad = data.take(pa.array([0, 4, 1]))
    with pytest.raises(ValueError, match="contiguous"):
        line_correction_surface(bad.to_batches(), "x", "y", "line", "correction", np.arange(4), np.arange(4), support)


def test_database_line_leveling_atomic_provenance(tmp_path):
    source = tmp_path / "source.parquet"
    pq.write_table(pa.table({"mag": [10., 12., 14., None], "line": ["a", "a", "b", "b"]}), source)
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(source)
    result = store.level_lines(database, "mag", "line", [("a", "b", 4.)], "corr", "leveled")
    assert result["statistics"]["rms_after"] < 1e-12
    values = next(store.batches(database, ["corr", "leveled"])).to_pydict()
    np.testing.assert_allclose(values["corr"], [-2., -2., 2., 2.])
    assert values["leveled"][3] is None
    graph = store.channel_pipeline(database, "leveled")
    provenance = graph["nodes"][graph["root"]]["provenance"]
    assert provenance["output_role"] == "corrected_signal" and len(provenance["crossovers_sha256"]) == 64
    assert json.loads(store.channels(database)[0]["provenance"])
    before = set(store.root.rglob("*.parquet"))
    with pytest.raises(ValueError, match="missing from"):
        store.level_lines(database, "mag", "line", [("a", "c", 2.)], "corr2", "leveled2")
    assert set(store.root.rglob("*.parquet")) == before
    assert not list(store.root.rglob("*.partial"))
    with pytest.raises(InterruptedError):
        store.level_lines(database, "mag", "line", [("a", "b", 2.)], "corr3", "leveled3", canceled=lambda: True)
