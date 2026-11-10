"""Conditional prism resolution and JSON-safe inner-solver diagnostics."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from terraworkbench_core.inversion import _cg_metrics


def test_cg_quality_is_independent_and_json_safe():
    diagnostic = _cg_metrics(
        SimpleNamespace(cg_count=100, cg_rel_resid=0.8, cg_rtol=0.001)
    )
    assert diagnostic["cg_tolerance_met"] is False
    assert diagnostic["cg_iterations"] == 100
    incomplete = _cg_metrics(SimpleNamespace(cg_rel_resid=np.nan, cg_rtol=0.001))
    assert (
        incomplete["cg_relative_residual"] is None
        and incomplete["cg_tolerance_met"] is None
    )
    json.dumps(incomplete, allow_nan=False)


def test_prism_resolution_agrees_with_svd_and_degrades_with_noise():
    pytest.importorskip("harmonica")
    from scripts.validate_inversion_resolution import resolution_case

    low = resolution_case(150.0, 90.0, 50.0)
    high = resolution_case(150.0, 90.0, 50.0, noise_scale=4.0)
    deep = resolution_case(650.0, 90.0, 50.0)
    for kind in low:
        assert (
            0
            < high[kind]["effective_parameters"]
            < low[kind]["effective_parameters"]
            <= 2
        )
        assert deep[kind]["effective_parameters"] < low[kind]["effective_parameters"]
        assert np.all(
            np.asarray(high[kind]["posterior_std"]) > low[kind]["posterior_std"]
        )


def test_geometry_profiles_preserve_deep_ambiguity_and_grid_censoring(tmp_path):
    pytest.importorskip("harmonica")
    from scripts.validate_inversion_resolution import geometry_profiles

    geometry_profiles(tmp_path)
    result = json.loads((tmp_path / "geometry_profiles.json").read_text())
    for kind in ("gravity", "susceptibility"):
        shallow = result[kind + "_separation_150m"]
        deep = result[kind + "_separation_650m"]
        assert shallow["best_value_m"] == shallow["truth_value_m"] == 100.0
        assert len(deep["delta_chi_squared_one_set_m"]) > len(
            shallow["delta_chi_squared_one_set_m"]
        )
        assert deep["touches_grid_edge"]
        assert "not a confidence interval" in deep["definition"]
