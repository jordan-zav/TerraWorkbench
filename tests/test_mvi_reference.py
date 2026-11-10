"""Independent MVI forward/reference solves and explicit connectivity contracts."""

import numpy as np
import pytest

from terraworkbench_core.recovery_metrics import model_recovery_metrics
from scripts.benchmark_voxel_recovery import CRITERIA


def assess(edges, **options):
    return model_recovery_metrics(
        np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [300.0, 0.0, 0.0]]),
        np.ones(3),
        np.array([1.0, 1.0, 0.0]),
        np.array([1.0, 1.0, 0.0]),
        criteria=CRITERIA,
        connectivity_edges=edges,
        **options,
    )


def test_explicit_adjacency_preserves_coarse_cell_connections():
    result = assess(np.array([[0, 1], [1, 2]]))
    assert result["truth_component_count"] == 1
    assert result["connectivity"] == "explicit_cell_adjacency"
    assert result["recovery_passed"]


def test_edges_cannot_bridge_through_an_absent_support_cell():
    result = assess(np.array([[0, 2], [2, 1]]))
    assert result["truth_component_count"] == 2


@pytest.mark.parametrize(
    "edges,extra",
    [
        ([[0.0, 1.0]], {}),
        ([[-1, 0]], {}),
        ([[0, 3]], {}),
        ([[1, 1]], {}),
        ([0, 1], {}),
        ([[0, 1]], {"connectivity_radius_m": 100.0}),
        ([[0, 1], [1, 2]], {"max_links": 1}),
    ],
)
def test_invalid_adjacency_is_rejected(edges, extra):
    with pytest.raises(ValueError, match="Adjacency"):
        assess(edges, **extra)


def test_native_and_core_mvi_recovery_campaign(tmp_path):
    pytest.importorskip("simpeg")
    pytest.importorskip("harmonica")
    from scripts.benchmark_mvi_reference import run

    report = run(tmp_path / "mvi", "quick")
    native, core, oracle, uniform = report["cases"]
    a = np.load(tmp_path / "mvi/native_simpeg.npz")
    b = np.load(tmp_path / "mvi/core.npz")
    np.testing.assert_allclose(b["model"], a["model"], rtol=2e-4, atol=1e-7)
    assert native["diagnostics"]["independent_forward_max_nt"] < 1e-5
    assert core["weighted_rms"] < 1.2
    # This deliberately underdetermined voxel problem must not be certified
    # merely because it predicts the magnetic data well.
    assert not core["recovery"]["recovery_passed"]
    assert oracle["exact_support_in_fit"] and oracle["recovery"]["recovery_passed"]
    assert oracle["recovery"]["body_metrics"][0]["direction_error_deg"] < 2.0
    assert uniform["recovery"]["recovery_passed"]
    assert uniform["diagnostics"]["free_parameters"] == 3


def test_mvi_smoothing_still_rejects_an_implicit_scalar_reference():
    pytest.importorskip("simpeg")
    from terraworkbench_core.inversion import run_potential_field_inversion

    with pytest.raises(ValueError, match="Cartesian vector reference"):
        run_potential_field_inversion(
            "mvi",
            np.zeros((5, 3)),
            np.zeros(5),
            np.ones(5),
            cell_xy=100.0,
            cell_z=100.0,
            depth=300.0,
            reference_in_smooth=True,
        )


def test_adaptive_tree_uses_face_topology():
    pytest.importorskip("simpeg")
    from pathlib import Path
    from discretize import TreeMesh
    from scripts.benchmark_mvi_reference import mesh_edges

    mesh = TreeMesh.read_UBC(
        str(Path(__file__).parent / "data/regularization_profiles/tree.msh")
    )
    edges = mesh_edges(mesh, np.ones(mesh.nC, bool))
    result = model_recovery_metrics(
        mesh.cell_centers,
        mesh.cell_volumes,
        np.ones(mesh.nC),
        np.ones(mesh.nC),
        criteria=CRITERIA,
        connectivity_edges=edges,
    )
    assert result["truth_component_count"] == 1
    assert result["recovery_passed"]


@pytest.mark.parametrize("mode", ["amplitude", "vector_smooth"])
def test_explicit_vector_reference_has_zero_smallness_and_interface_cost(
    mode, monkeypatch
):
    pytest.importorskip("simpeg")
    from simpeg import inverse_problem
    from scripts.benchmark_mvi_reference import fixture
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh, active, xyz, observed, sigma, truth, _, _ = fixture("quick")
    reference = truth * 0.5
    native = inverse_problem.BaseInvProblem
    inspected = []

    class InspectReference(native):
        def __init__(self, misfit, reg, opt, **kwargs):
            ref = reference.ravel(order="F")
            assert reg(ref) == pytest.approx(0.0, abs=1e-20)
            assert reg(np.zeros_like(ref)) > 0.0
            inspected.append(True)
            super().__init__(misfit, reg, opt, **kwargs)

    monkeypatch.setattr(inverse_problem, "BaseInvProblem", InspectReference)
    result = run_potential_field_inversion(
        "mvi",
        xyz,
        observed,
        np.full(len(xyz), sigma),
        mesh=mesh,
        active_cells=active,
        cell_xy=100.0,
        cell_z=100.0,
        depth=400.0,
        iterations=1,
        cg_maxiter=100,
        reference_model=reference,
        starting_model=reference,
        reference_in_smooth=True,
        mvi_regularization=mode,
    )
    assert inspected and np.isfinite(result.model).all()
