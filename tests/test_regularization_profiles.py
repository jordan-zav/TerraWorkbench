"""Independent historical-library priors, plus actual standalone solves."""

import json
import hashlib
from pathlib import Path
import numpy as np
import pytest

pytest.importorskip("simpeg")

FIXTURES = Path(__file__).parent / "data/regularization_profiles"


@pytest.mark.parametrize("name", ["uniform", "nonuniform", "tree"])
@pytest.mark.parametrize("case", ["l2", "l1_active", "mixed_active"])
def test_cell_difference_matches_historical_objective_gradient_and_hessian(name, case):
    from discretize import TensorMesh, TreeMesh
    from terraworkbench_core.regularization_profiles import build_cell_difference_prior

    with np.load(FIXTURES / f"{name}_{case}.npz", allow_pickle=False) as data:
        mesh = (
            TreeMesh.read_UBC(str(FIXTURES / "tree.msh"))
            if name == "tree"
            else TensorMesh([data["hx"], data["hy"], data["hz"]], origin=data["origin"])
        )
        np.testing.assert_array_equal(mesh.cell_centers, data["xyz"])
        active = data["active"] if case != "l2" else np.ones(mesh.nC, bool)
        norms = (
            [0.0, 1.0, 1.5, 2.0]
            if case == "mixed_active"
            else ([1.0] * 4 if case == "l1_active" else [2.0] * 4)
        )
        reg, _ = build_cell_difference_prior(
            mesh, active, data["reference"], norms, [1.0] * 4
        )
        reg.set_weights(sensitivity=data["sensitivity"] / data["sensitivity"].max())
        if case != "l2":
            reg.irls_threshold = 0.01
            reg.update_weights(data["model"])
        # Both current data misfit and prior use the full quadratic. Historical
        # SimPEG used half quadratics, so the SAME factor two applies to all terms.
        for axis, term in zip("sxyz", reg.objfcts):
            np.testing.assert_allclose(
                term(data["model"]), 2.0 * data["phi_" + axis], rtol=1e-10, atol=1e-12
            )
            np.testing.assert_allclose(
                term.deriv(data["model"]),
                2.0 * data["gradient_" + axis],
                rtol=1e-10,
                atol=1e-12,
            )
            np.testing.assert_allclose(
                term.deriv2(data["model"]).toarray(),
                2.0 * data["H_" + axis],
                rtol=1e-10,
                atol=1e-12,
            )


@pytest.mark.parametrize("kind", ["gravity", "susceptibility"])
@pytest.mark.parametrize("storage", ["ram", "matrix_free"])
def test_cell_difference_runs_real_scalar_workflow(kind, storage, tmp_path):
    from discretize import TensorMesh
    from simpeg import maps
    from simpeg.potential_fields import gravity, magnetics
    from terraworkbench_core.inversion import run_inversion_workflow

    mesh = TensorMesh([[(100.0, 3)]] * 3, origin=[-150.0, -150.0, -300.0])
    active = np.ones(mesh.nC, bool)
    x, y = np.meshgrid([-100.0, 0.0, 100.0], [-100.0, 0.0, 100.0])
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    mapping = maps.IdentityMap(nP=mesh.nC)
    truth = np.zeros(mesh.nC)
    truth[13] = 0.3 if kind == "gravity" else 0.02
    if kind == "gravity":
        survey = gravity.survey.Survey(
            gravity.sources.SourceField(
                receiver_list=[gravity.receivers.Point(xyz, components="gz")]
            )
        )
        simulation = gravity.simulation.Simulation3DIntegral(
            mesh, survey=survey, rhoMap=mapping, engine="choclo"
        )
    else:
        survey = magnetics.survey.Survey(
            magnetics.sources.UniformBackgroundField(
                receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
                amplitude=50000.0,
                inclination=60.0,
                declination=0.0,
            )
        )
        simulation = magnetics.simulation.Simulation3DIntegral(
            mesh, survey=survey, chiMap=mapping, engine="choclo"
        )
    observed = simulation.dpred(truth)
    output = tmp_path / kind
    result = run_inversion_workflow(
        kind,
        xyz,
        observed,
        np.full(len(xyz), max(float(abs(observed).max()) * 0.05, 1e-5)),
        output_directory=output,
        mesh=mesh,
        active_cells=active,
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        regularization_convention="cell_difference",
        regularization_weights=[1.0, 1.0, 1.0, 1.0],
        regularization_norms=[1.0, 1.0, 1.0, 1.0],
        irls_iterations=2,
        iterations=5,
        cg_maxiter=100,
        sensitivity_mode=storage,
    )
    assert np.isfinite(result.model).all() and np.isfinite(result.predicted).all()
    assert result.diagnostics["regularization_convention"] == "cell_difference"
    if storage == "matrix_free":
        assert result.diagnostics["stored_sensitivity_bytes"] == 0
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["state"] == "complete"
    assert "regularization_profiles.py" in manifest["core_sources_sha256"]


def test_independent_fixture_manifest():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert manifest["versions"]["SimPEG"] == "0.15.0"
    for name, expected in manifest["files_sha256"].items():
        payload = (FIXTURES / name).read_bytes()
        if name.endswith(".msh"):
            payload = payload.replace(b"\r\n", b"\n")
        assert hashlib.sha256(payload).hexdigest() == expected


@pytest.mark.parametrize(
    "kind,convention,weights",
    [
        ("mvi", "cell_difference", [1.0] * 4),
        ("susceptibility", "cell_difference", None),
        ("susceptibility", "unknown", [1.0] * 4),
    ],
)
def test_unsupported_profiles_fail_before_allocating_mesh(kind, convention, weights):
    from terraworkbench_core.inversion import run_potential_field_inversion

    with pytest.raises(ValueError, match="convention|Cell-difference"):
        run_potential_field_inversion(
            kind,
            np.zeros((5, 3)),
            np.zeros(5),
            np.ones(5),
            cell_xy=100.0,
            cell_z=100.0,
            depth=300.0,
            regularization_convention=convention,
            regularization_weights=weights,
        )
