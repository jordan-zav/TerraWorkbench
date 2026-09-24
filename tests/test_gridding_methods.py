import numpy as np
import pytest

from gridding_methods import MinimumCurvatureGridder, SincGridder


def _plane_points(size=5):
    yy, xx = np.mgrid[0:size, 0:size]
    xy = np.column_stack((xx.ravel(), yy.ravel())).astype(float)
    values = 4.0 + 2.0 * xy[:, 0] - 3.0 * xy[:, 1]
    return xy, values


def test_minimum_curvature_recovers_a_plane_through_an_interior_gap():
    xy, values = _plane_points()
    missing = np.all(xy == [2.0, 2.0], axis=1)
    gridder = MinimumCurvatureGridder(
        xy[~missing], values[~missing], 1.0,
        tolerance=1e-8, pass_tolerance=99.0, max_iterations=200,
        coarse_grid=1,
    )
    result = gridder.grid(np.arange(5.0), np.arange(5.0))
    expected = 4.0 + 2.0 * 2.0 - 3.0 * 2.0
    assert result[2, 2] == pytest.approx(expected, abs=1e-5)
    assert gridder.metadata["algorithm"] == "minimum_curvature_multilevel"
    assert gridder.metadata["levels"][-1]["factor"] == 1


def test_minimum_curvature_blanking_and_parameter_metadata():
    xy, values = _plane_points()
    gridder = MinimumCurvatureGridder(
        xy, values, 1.0, blanking_distance=0.1, coarse_grid=4,
        search_radius=2.0, desample_factor=1,
    )
    result = gridder.grid(np.arange(7.0), np.arange(7.0))
    assert np.isfinite(result[:5, :5]).all()
    assert np.isnan(result[6, 6])
    assert gridder.metadata["search_radius"] == 2.0


def test_sinc_interpolator_is_an_interpolator_and_preserves_exact_grid_samples():
    xy, values = _plane_points(size=2)
    gridder = SincGridder(xy, values, 1.0, radius=4, blanking_distance=1.1)
    query = np.array([[0.0, 0.0], [0.5, 0.5], [3.0, 3.0]])
    result = gridder.evaluate(query)
    assert result[0] == pytest.approx(values[0])
    assert result[1] == pytest.approx(np.mean(values), abs=1e-10)
    assert np.isnan(result[2])
    assert gridder.metadata["fallback"] == "nodata"
    gridder.grid(np.arange(2.0), np.arange(2.0))
    assert gridder.metadata["algorithm"] == "regular_lattice_windowed_sinc"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cell_size": 0.0},
        {"cell_size": 1.0, "coarse_grid": 3},
        {"cell_size": 1.0, "tension": 2.0},
    ],
)
def test_minimum_curvature_rejects_invalid_parameters(kwargs):
    xy, values = _plane_points()
    with pytest.raises(ValueError):
        MinimumCurvatureGridder(xy, values, **kwargs)


def test_sinc_rejects_invalid_parameters():
    xy, values = _plane_points(size=2)
    with pytest.raises(ValueError):
        SincGridder(xy, values, 1.0, radius=0)


def test_sinc_rejects_irregular_points():
    xy, z = _plane_points()
    xy[3, 0] += .03
    with pytest.raises(ValueError, match="regular sample lattice"):
        SincGridder(xy, z, 1.)


def test_sinc_cardinality_sinusoid_and_anisotropic_spacing():
    y, x = np.mgrid[0:32, 0:32]
    xy = np.column_stack((x.ravel()*.5, y.ravel()*2.))
    z = np.cos(2*np.pi*x/16)+np.sin(2*np.pi*y/16)
    model = SincGridder(xy, z.ravel(), (.5, 2.), radius=8)
    np.testing.assert_allclose(model.evaluate(xy), z.ravel(), atol=1e-12)
    q = np.array([[5.25, 19.], [7.125, 29.5]])
    exact = np.cos(2*np.pi*q[:,0]/8)+np.sin(2*np.pi*q[:,1]/32)
    np.testing.assert_allclose(model.evaluate(q), exact, atol=.002)


def test_sinc_holes_remain_missing():
    xy, z = _plane_points(9)
    keep = np.any(xy != [4,4], axis=1)
    model = SincGridder(xy[keep], z[keep], 1.)
    assert np.isnan(model.evaluate([[4,4], [4.5,4.5]])).all()
    assert np.isfinite(model.evaluate([[1,1]])).all()


def test_minimum_curvature_affine_invariance_on_sparse_points():
    rng = np.random.default_rng(101)
    xy = rng.uniform(0, 20, (80,2))
    z = 12 + 3*xy[:,0] - 2*xy[:,1]
    model = MinimumCurvatureGridder(xy, z, .5)
    axis = np.arange(0,20,.5)
    result = model.grid(axis, axis)
    x,y = np.meshgrid(axis,axis)
    np.testing.assert_allclose(result, 12+3*x-2*y, atol=1e-10)


def test_minimum_curvature_reports_failed_residual_check(monkeypatch):
    # An exhausted numerical solve must never be certified by its iteration count.
    import scipy.sparse.linalg
    class FailedFactorization:
        def solve(self, rhs):
            return np.zeros_like(rhs)
    monkeypatch.setattr(scipy.sparse.linalg, "splu", lambda matrix: FailedFactorization())
    xy,z = _plane_points(5)
    z[13] += 10
    model = MinimumCurvatureGridder(xy,z,.5,max_iterations=1,tolerance=1e-8,solver="variational")
    model.grid(np.arange(0,4.5,.5),np.arange(0,4.5,.5))
    assert not model.metadata['converged']
    assert model.metadata['levels'][-1]['stop_reason'] == 'refinement_limit'


def test_offnode_constraints_reproduce_quadratic_including_mixed_term():
    from gridding_methods import _offnode_constraints
    axis = np.arange(-2., 7.)
    xy = np.array([[.31,.27], [1.8,2.4], [3.1,.7], [3.7,3.6]])
    def field(x,y):
        return 3+2*x-y+.2*x*x-.4*x*y+.7*y*y
    z = field(xy[:,0],xy[:,1])
    a, target = _offnode_constraints(xy,z,axis,axis)
    xx, yy = np.meshgrid(axis,axis)
    np.testing.assert_allclose(a@field(xx,yy).ravel(),target,atol=1e-12)


def test_constrained_solution_minimizes_bending_energy():
    from gridding_methods import _offnode_constraints, _bending_energy, _solve_surface
    from scipy.linalg import null_space
    axis = np.arange(-2., 6.)
    xy = np.array([[0.,0.], [2.,0.], [0.,2.], [2.,2.], [1.2,.8]])
    z = np.array([0., 1., 1., 0., 2.])
    result, report = _solve_surface(xy,z,axis,axis,0.,1e-8,3,None)
    a,target = _offnode_constraints(xy,z,axis,axis)
    q = _bending_energy(len(axis),len(axis),0.)
    u = result.ravel()
    np.testing.assert_allclose(a@u,target,atol=1e-8)
    feasible = null_space(a.toarray())
    np.testing.assert_allclose(feasible.T@(q@u),0.,atol=1e-8)
    assert report['converged']
    for perturbation in np.random.default_rng(11).normal(size=(5,feasible.shape[1])):
        trial = u+feasible@perturbation
        assert trial@q@trial >= u@q@u-1e-8


def test_minimum_curvature_subset_matches_full_domain():
    xy,z = _plane_points(7)
    z[24] += 5
    full = MinimumCurvatureGridder(xy,z,1.).grid(np.arange(7.),np.arange(7.))
    subset = MinimumCurvatureGridder(xy,z,1.).grid(np.arange(2.,5.),np.arange(2.,5.))
    np.testing.assert_allclose(subset,full[2:5,2:5],atol=1e-8)


def test_multilevel_checks_offnode_data_and_equation_residuals():
    from gridding_methods import _multilevel_surface, _briggs_constraints
    yy, xx = np.mgrid[2:5, 2:5]
    xy = np.column_stack((xx.ravel()+.2, yy.ravel()-.15))
    z = np.sin(xy[:, 0]/3)+np.cos(xy[:, 1]/2)
    axis = np.arange(7.)
    result, levels, _ = _multilevel_surface(
        xy,z,axis,axis,1.,coarse_grid=2,search_radius=4.,weighting_power=2.,
        tension=0.,tolerance=1e-6,pass_tolerance=100.,max_iterations=4000)
    assert levels[-1]['converged']
    assert levels[-1]['max_diagonal_scaled_residual'] <= 1e-6
    a,target,_ = _briggs_constraints(xy,z,axis,axis)
    np.testing.assert_allclose(a@result.ravel(),target,atol=1e-6)


@pytest.mark.parametrize("tension", [0., .3, 1.])
def test_briggs_harmonic_polynomials_all_quadrants_and_near_node(tension):
    from gridding_methods import _briggs_constraints
    axis = np.arange(-3., 4.)
    xx, yy = np.meshgrid(axis, axis)
    for dx, dy in [(0., 0.), (1e-12, -1e-12), (.3, 0.), (0., -.2),
                   (.3, .2), (-.3, .2), (.3, -.2), (-.3, -.2), (.5, .5)]:
        point = np.array([[dx, dy]])
        for field in (lambda x, y: 3+2*x-y, lambda x, y: x*x-y*y,
                      lambda x, y: x*y):
            z = field(point[:, 0], point[:, 1])
            a, target, anchors = _briggs_constraints(point, z, axis, axis, tension)
            assert anchors[0] == 24
            assert np.isfinite(a.data).all()
            np.testing.assert_allclose(a@field(xx, yy).ravel(), target, atol=1e-12)


def test_briggs_quadratic_curvature_and_distinct_from_value_constraint():
    from gridding_methods import _briggs_constraints, _offnode_constraints
    axis = np.arange(-3., 4.)
    point = np.array([[.31, -.27]])
    xx, yy = np.meshgrid(axis, axis)
    def field(x, y):
        return 3+2*x-y+.2*x*x-.4*x*y+.7*y*y
    z = field(point[:, 0], point[:, 1])
    a, target, _ = _briggs_constraints(point, z, axis, axis)
    np.testing.assert_allclose(a@field(xx, yy).ravel(), target, atol=1e-12)
    taylor, _ = _offnode_constraints(point, z, axis, axis)
    assert not np.allclose(a.toarray(), taylor.toarray())


def test_multilevel_iteration_limit_and_active_seed_controls():
    xy,z = _plane_points(7)
    z[24] += 20.
    results = []
    for radius in (.1, 20.):
        model = MinimumCurvatureGridder(xy+.2,z,1.,coarse_grid=4,search_radius=radius,
                                       max_iterations=1,tolerance=1e-10)
        results.append(model.grid(np.arange(7.),np.arange(7.)))
        assert not model.metadata['converged']
        assert model.metadata['levels'][-1]['stop_reason'] == 'iteration_limit'
        assert model.metadata['legacy_controls_not_used'] == []
    assert not np.allclose(results[0],results[1],rtol=1e-10,atol=1e-8)


def test_multilevel_cancellation_during_iteration():
    xy,z = _plane_points(9)
    z[40] += 10.
    model = MinimumCurvatureGridder(xy+.2,z,1.,coarse_grid=1,tolerance=1e-12,pass_tolerance=100.)
    checks = 0
    def canceled():
        nonlocal checks
        checks += 1
        return checks > 160
    with pytest.raises(InterruptedError):
        model.grid(np.arange(9.),np.arange(9.),canceled=canceled)


def test_converged_surface_is_orientation_invariant_on_unaligned_domain():
    from scripts.audit_curvature_symmetry import audit
    results = audit(10, [5000])
    for orientation in results.values():
        assert orientation['direct_symmetry_max_error'] < 1e-10
        run = orientation['runs'][0]
        assert run['final_level']['converged']
        assert run['rmse_to_direct'] < 1e-7
        assert run['symmetry_max_error'] < 1e-7
