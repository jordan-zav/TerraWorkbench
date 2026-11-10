import numpy as np
import pytest

from terraworkbench_core.lineament_geometry import skeleton_paths


def test_straight_graph_coordinates_length_and_isolated_pixels():
    pytest.importorskip("skimage")
    features = np.zeros((11, 11), bool)
    features[5, 2:9] = True
    features[1, 1] = True
    result = skeleton_paths(features, (2.0, 3.0), (100.0, 200.0))
    assert len(result["paths"]) == 1
    path = result["paths"][0]
    assert path["length_m"] == 18.0
    np.testing.assert_array_equal(path["xy"][0], [106, 210])
    np.testing.assert_allclose(path["segment_azimuth_degrees_axial"], 90)
    assert result["isolated_xy"].shape == (1, 2)
    assert not path["closed"]


def test_branches_and_closed_cycles_are_not_lost():
    pytest.importorskip("skimage")
    features = np.zeros((15, 15), bool)
    features[2:9, 5] = True
    features[5, 2:9] = True
    result = skeleton_paths(features, (1, 1), (0, 0))
    assert len(result["paths"]) == 4
    assert sum(path["length_m"] for path in result["paths"]) == 12
    ring = np.zeros((15, 15), bool)
    ring[3, 3:12] = ring[11, 3:12] = True
    ring[3:12, 3] = ring[3:12, 11] = True
    result = skeleton_paths(ring, (1, 1), (0, 0))
    assert len(result["paths"]) == 1 and result["paths"][0]["closed"]
    assert result["recipe"]["traced_edges"] > 0


def test_geometry_guards_and_short_path_accounting():
    pytest.importorskip("skimage")
    mask = np.eye(9, dtype=bool)
    result = skeleton_paths(mask, (1, 1), (0, 0), minimum_length_m=100)
    assert not result["paths"] and result["recipe"]["omitted_short_paths"] == 1
    with pytest.raises(ValueError):
        skeleton_paths(mask.astype(float), (1, 1), (0, 0))
    with pytest.raises(ValueError):
        skeleton_paths(mask, (1, 1), (0, 0), max_skeleton_pixels=3)
    with pytest.raises(RuntimeError, match="canceled"):
        skeleton_paths(mask, (1, 1), (0, 0), canceled=lambda: True)
