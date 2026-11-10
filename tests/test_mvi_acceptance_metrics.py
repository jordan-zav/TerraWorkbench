"""Depth scoring follows ENU and correctly matches separate components."""

import numpy as np
import pytest
from scripts.benchmark_mvi_acceptance import depth_errors


def test_separated_components_depth_and_fortran_cell_order():
    pytest.importorskip("discretize")
    from discretize import TensorMesh

    mesh = TensorMesh(
        [np.ones(4) * 100, np.ones(2) * 100, np.ones(4) * 100], origin=[0, 0, -400]
    )
    truth = np.zeros((mesh.nC, 3))
    grid = np.arange(mesh.nC).reshape((4, 2, 4), order="F")
    truth[grid[0, 0, 0], 0] = 1
    truth[grid[3, 0, 2], 1] = 1
    recovered = truth.copy()
    result = depth_errors(
        mesh.cell_centers, mesh.cell_volumes, recovered, truth, 0.5, (4, 2, 4)
    )
    assert result["maximum_depth_error_m"] == 0
    recovered[grid[0, 0, 0]] = 0
    recovered[grid[0, 0, 1], 0] = 1
    result = depth_errors(
        mesh.cell_centers, mesh.cell_volumes, recovered, truth, 0.5, (4, 2, 4)
    )
    assert result["maximum_depth_error_m"] == 100
    recovered[grid[3, 0, 2]] = 0
    assert (
        depth_errors(
            mesh.cell_centers, mesh.cell_volumes, recovered, truth, 0.5, (4, 2, 4)
        )["maximum_depth_error_m"]
        is None
    )
