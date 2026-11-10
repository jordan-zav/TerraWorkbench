from types import SimpleNamespace
import json
import numpy as np
from terraworkbench_core import survey_processing as survey


def test_raw_tile_cache_is_optional_and_preserves_background_behavior(monkeypatch):
    calls = []

    class Gridder:
        def __init__(self, *args, **kwargs):
            self.metadata = {"working_nodes": 25, "converged": True}

        def grid(self, x, y, **kwargs):
            calls.append(1)
            gx, gy = np.meshgrid(x, y)
            return gx + gy

    monkeypatch.setattr(survey, "MinimumCurvatureGridder", Gridder)

    class Cache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(json.dumps(key, sort_keys=True))

        def put(self, key, value):
            self.values[json.dumps(key, sort_keys=True)] = value

    cache = Cache()
    x = y = np.arange(5.0)
    gx, gy = np.meshgrid(x, y)
    points = np.column_stack((gx.ravel(), gy.ravel(), (gx + gy).ravel()))
    opt = SimpleNamespace(
        cell_size=1.0,
        crosshatch_lattice="directional",
        tile_cells=400,
        blanking=0.0,
        blanking_metric="euclidean",
        search_radius=0.0,
        max_iterations=30,
        tolerance=0.01,
        pass_tolerance=99.0,
    )
    args = dict(
        core=400, halo=1, radius=1, check=lambda: None, emit=lambda *a, **k: None
    )
    initial = survey.grid_survey([points], x, y, opt, **args, tile_cache=cache)
    repeat = survey.grid_survey([points], x, y, opt, **args, tile_cache=cache)
    assert len(calls) == 1
    np.testing.assert_equal(initial[3], repeat[3])
    full = survey.grid_survey([points], x, y, opt, **args)
    assert len(calls) == 2
    np.testing.assert_equal(full[3], repeat[3])
