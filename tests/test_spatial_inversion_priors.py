"""Hard per-cell model bounds and independent geological weights in real solves."""

import numpy as np
import pytest

pytest.importorskip("simpeg")


@pytest.mark.parametrize("kind", ["gravity", "susceptibility", "mvi"])
def test_fixed_background_is_preserved_by_scalar_and_vector_solvers(kind):
    from discretize import TensorMesh
    from simpeg import maps
    from simpeg.potential_fields import gravity, magnetics
    from terraworkbench_core.inversion import run_potential_field_inversion

    mesh = TensorMesh([[(100.0, 3)]] * 3, origin=[-150.0, -150.0, -300.0])
    active = np.ones(mesh.nC, bool)
    x, y = np.meshgrid([-100.0, 0.0, 100.0], [-100.0, 0.0, 100.0])
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 50.0)]
    n = mesh.nC
    support = np.zeros(n, bool)
    support[13] = True
    size = n * (3 if kind == "mvi" else 1)
    model = np.zeros(size)
    if kind == "mvi":
        model[[13, 13 + n, 13 + 2 * n]] = [0.01, 0.02, -0.01]
    else:
        model[13] = 0.3 if kind == "gravity" else 0.02
    if kind == "gravity":
        survey = gravity.survey.Survey(
            gravity.sources.SourceField(
                receiver_list=[gravity.receivers.Point(xyz, components="gz")]
            )
        )
        sim = gravity.simulation.Simulation3DIntegral(
            mesh,
            survey=survey,
            rhoMap=maps.IdentityMap(nP=size),
            active_cells=active,
            engine="choclo",
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
        sim = magnetics.simulation.Simulation3DIntegral(
            mesh,
            survey=survey,
            chiMap=maps.IdentityMap(nP=size),
            model_type="vector" if kind == "mvi" else "scalar",
            active_cells=active,
            engine="choclo",
        )
    data = sim.dpred(model)
    lo = np.where(support, -0.1 if kind == "mvi" else 0.0, 0.0)
    hi = np.where(support, 0.1 if kind == "mvi" else 1.0, 0.0)
    result = run_potential_field_inversion(
        kind,
        xyz,
        data,
        np.full(len(xyz), max(abs(data).max() * 0.01, 1e-5)),
        cell_xy=100.0,
        cell_z=100.0,
        depth=300.0,
        mesh=mesh,
        active_cells=active,
        lower=lo,
        upper=hi,
        cell_weights=np.ones(n),
        iterations=20,
        cg_maxiter=100,
    )
    mask = np.tile(support, 3) if kind == "mvi" else support
    np.testing.assert_array_equal(result.model[~mask], 0.0)
    assert result.diagnostics["free_parameter_count"] == int(mask.sum())
    assert result.diagnostics["fixed_parameter_count"] == int((~mask).sum())
    assert result.diagnostics["geological_cell_weights_supplied"]
    assert np.linalg.norm(result.model[mask]) > 0
