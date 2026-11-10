"""Independent physical, covariance and interpolation checks for 2-D additions."""

import numpy as np
import pytest
from scipy.constants import G
from scipy.integrate import dblquad

from terraworkbench_core.gravity_profiles import (
    polygon_gravity_2d,
    fit_polygon_densities,
)
from terraworkbench_core.radon_corrections import (
    upward_window_radon,
    calibrated_window_radon,
    full_spectrum_radon,
)
from terraworkbench_core.geostatistics import ordinary_kriging, empirical_variogram
from terraworkbench_core.radiometry import background_correction
from terraworkbench_core.gravity_network import adjust_gravity_network


def test_network_uncertain_anchor_propagates_common_datum_variance():
    options = dict(
        station_ids=["A", "B", "A", "B"],
        instrument_ids=["one"] * 4,
        times_s=[0.0, 1.0, 2.0, 3.0],
        readings_mgal=[100.0, 105.0, 100.0, 105.0],
        reading_std_mgal=np.ones(4),
        anchors_mgal={"A": 100.0},
        drift_degree=0,
    )
    exact = adjust_gravity_network(**options)
    soft = adjust_gravity_network(**options, anchor_std_mgal={"A": 2.0})
    np.testing.assert_allclose(soft["gravity_mgal"], [100.0, 105.0], atol=1e-11)
    np.testing.assert_allclose(
        soft["formal_std_mgal"] ** 2, exact["formal_std_mgal"] ** 2 + 4.0, atol=1e-11
    )
    # Shared anchor uncertainty induces station covariance, preserving the
    # relative precision of the gravity difference instead of double counting.
    np.testing.assert_allclose(
        soft["covariance"][:2, :2], [[4.0, 4.0], [4.0, 5.0]], atol=1e-11
    )
    assert not soft["anchors_are_exact"]
    assert exact["anchors_are_exact"]
    with pytest.raises(ValueError, match="every anchor"):
        adjust_gravity_network(**options, anchor_std_mgal={"A": 0.0})


RECT = np.array([[-70.0, -250.0], [90.0, -250.0], [90.0, -100.0], [-70.0, -100.0]])


def test_registered_extension_has_source_and_input_provenance():
    from terraworkbench_core.operations import run_operation

    output = run_operation(
        "gravity.polygon_forward",
        observation_xz_m=[[0.0, 0.0]],
        polygons_xz_m=[RECT.tolist()],
        density_kg_m3=[500.0],
    )
    assert output["result"]["gravity_mgal"].shape == (1,)
    assert output["provenance"]["status"] == "completed"
    assert len(output["provenance"]["source_sha256"]) == 64
    assert len(output["provenance"]["input_sha256"]) == 64
    assert output["provenance"]["optional_engine"] is None


def test_full_spectrum_exact_channel_projection_has_nonnegative_variance():
    output = full_spectrum_radon(
        [[2.0, 3.0]], np.eye(2), [1.0, 1.0], ["ground", "radon"], radon_component=1
    )
    np.testing.assert_allclose(output["corrected_spectra"], [[2.0, 0.0]])
    np.testing.assert_allclose(output["corrected_variance"], [[1.0, 0.0]], atol=1e-15)


@pytest.mark.parametrize("reverse", [False, True])
def test_polygon_rectangle_against_independent_area_integration(reverse):
    obs = np.array([[0.0, 0.0], [140.0, 40.0], [-200.0, -20.0]])
    p = RECT[::-1] if reverse else RECT
    actual = polygon_gravity_2d(obs, [p], [2670.0])["gravity_mgal"]
    expected = []
    for x, z in obs:
        value = dblquad(
            lambda zs, xs: (
                -2 * G * 2670 * 1e5 * (zs - z) / ((xs - x) ** 2 + (zs - z) ** 2)
            ),
            -70,
            90,
            lambda _: -250,
            lambda _: -100,
            epsabs=1e-10,
        )[0]
        expected.append(value)
    np.testing.assert_allclose(actual, expected, atol=1e-10)


def test_polygon_circle_cylinder_horizontal_edges_and_translation():
    angle = np.linspace(0, 2 * np.pi, 512, endpoint=False)
    radius, depth, rho = 50.0, 200.0, 500.0
    polygon = np.c_[radius * np.cos(angle), -depth + radius * np.sin(angle)]
    x = np.linspace(-400, 400, 41)
    obs = np.c_[x, np.zeros_like(x)]
    expected = 2 * np.pi * G * rho * radius**2 * depth / (x * x + depth**2) * 1e5
    actual = polygon_gravity_2d(obs, [polygon], [rho])["gravity_mgal"]
    np.testing.assert_allclose(actual, expected, rtol=5e-5)
    shift = np.array([600000.0, -4000.0])
    shifted = polygon_gravity_2d(obs + shift, [polygon + shift], [rho])["gravity_mgal"]
    np.testing.assert_allclose(shifted, actual, atol=1e-10)
    # Observation on an edge extension or vertex is not moved by epsilon.
    assert np.isfinite(
        polygon_gravity_2d(RECT[:2], [RECT], [rho])["gravity_mgal"]
    ).all()


def test_polygon_concave_matches_adjacent_rectangles_and_signed_density():
    p = np.array(
        [
            [0.0, -200.0],
            [200.0, -200.0],
            [200.0, -100.0],
            [100.0, -100.0],
            [100.0, 0.0],
            [0.0, 0.0],
        ]
    )
    a = np.array([[0.0, -200.0], [200.0, -200.0], [200.0, -100.0], [0.0, -100.0]])
    b = np.array([[0.0, -100.0], [100.0, -100.0], [100.0, 0.0], [0.0, 0.0]])
    obs = np.array([[0.0, 50.0], [140.0, 60.0], [-100.0, 70.0]])
    actual = polygon_gravity_2d(obs, [p], [-500.0])["gravity_mgal"]
    expected = polygon_gravity_2d(obs, [a, b], [-500.0, -500.0])["gravity_mgal"]
    np.testing.assert_allclose(actual, expected, atol=1e-11)


@pytest.mark.parametrize(
    "polygon",
    [
        [[0, 0], [1, 1], [0, 1], [1, 0]],
        [[0, 0], [1, 0], [1, 0], [0, 1]],
        [[0, 0], [1, 0], [2, 0]],
        [[0, 0], [2, 0], [0, 2], [1, 0], [2, 2]],
    ],
)
def test_bad_polygon_geometry_rejected(polygon):
    with pytest.raises(ValueError):
        polygon_gravity_2d([[0, 1]], [polygon], [1.0])


def test_polygon_density_fit_known_errors_and_rank_failure():
    polygons = [RECT, RECT + np.array([400.0, -80.0])]
    obs = np.c_[np.linspace(-400, 800, 51), np.zeros(51)]
    signal = polygon_gravity_2d(obs, polygons, [300.0, -150.0])["gravity_mgal"] + 0.7
    result = fit_polygon_densities(
        obs, polygons, signal, np.full(51, 0.02), fit_offset=True
    )
    np.testing.assert_allclose(result["density_kg_m3"], [300.0, -150.0], atol=1e-8)
    assert result["offset_mgal"] == pytest.approx(0.7)
    assert (np.diag(result["density_covariance"]) > 0).all()
    with pytest.raises(ValueError, match="rank deficient|ill-conditioned"):
        fit_polygon_densities(obs, [RECT, RECT], signal, np.ones(51))
    with pytest.raises(ValueError, match="budget"):
        polygon_gravity_2d(obs, polygons, [1.0, 1.0], max_interactions=3)
    with pytest.raises(InterruptedError):
        polygon_gravity_2d(obs, polygons, [1.0, 1.0], canceled=lambda: True)


def upward_model(p):
    a1, a2, au, at, bu, bt = p
    return np.array([[a1, a2, au], [1.0, 0.0, 1.0], [0.0, 1.0, at]]), np.array(
        [bu, 0.0, bt]
    )


def test_iaea_upward_equation_against_dense_mixing_inverse_and_covariance():
    p = np.array([0.1, 0.03, 0.8, 0.12, 0.4, 0.2])
    matrix, offset = upward_model(p)
    truth = np.array([[10.0, 20.0, 3.0], [15.0, 25.0, -1.0]])
    measurements = truth @ matrix.T + offset
    cov = np.array([[2.0, 0.2, 0.1], [0.2, 3.0, 0.3], [0.1, 0.3, 1.0]])
    actual = upward_window_radon(*measurements.T, cov, p, block_size=1)
    np.testing.assert_allclose(actual["radon_u_rate"], truth[:, 2])
    np.testing.assert_allclose(actual["terrestrial_u_rate"], truth[:, 0])
    np.testing.assert_allclose(actual["terrestrial_th_rate"], truth[:, 1])
    inverse = np.linalg.inv(matrix)
    expected = inverse @ cov @ inverse.T
    np.testing.assert_allclose(actual["radon_variance"], expected[2, 2])
    np.testing.assert_allclose(
        actual["terrestrial_covariance"], np.broadcast_to(expected[:2, :2], (2, 2, 2))
    )
    assert actual["negative_radon"][1]


def test_upward_calibration_uncertainty_against_independent_finite_differences():
    p = np.array([0.1, 0.03, 0.8, 0.12, 0.4, 0.2])
    matrix, offset = upward_model(p)
    measurements = matrix @ np.array([10.0, 20.0, 3.0]) + offset
    covariance = np.diag([1e-6] * 4 + [1e-4] * 2)
    actual = upward_window_radon(
        *measurements[:, None], np.zeros((3, 3)), p, coefficient_covariance=covariance
    )
    jac = []
    for i in range(6):
        step = np.zeros(6)
        step[i] = 1e-6
        plus, op = upward_model(p + step)
        minus, om = upward_model(p - step)
        jac.append(
            (
                np.linalg.solve(plus, measurements - op)
                - np.linalg.solve(minus, measurements - om)
            )
            / 2e-6
        )
    j = np.array(jac).T
    expected = j @ covariance @ j.T
    np.testing.assert_allclose(actual["radon_variance"], expected[2, 2], rtol=1e-8)
    np.testing.assert_allclose(
        actual["terrestrial_covariance"][0], expected[:2, :2], rtol=1e-8
    )
    with pytest.raises(ValueError, match="cannot separate"):
        upward_window_radon(
            [1.0], [1.0], [1.0], np.eye(3), [1.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        )


def test_window_separation_and_same_measurement_subtraction_covariance():
    response = np.array(
        [
            [1.0, 0.2, 0.3, 1.2],
            [0.1, 1.0, 0.2, 0.3],
            [0.2, 0.1, 1.0, 0.4],
            [0.3, 0.2, 0.1, 1.0],
        ]
    )
    truth = np.array([[10.0, 20.0, 5.0, 3.0], [4.0, 5.0, 6.0, -1.0]])
    noise = np.diag([1.0, 2.0, 3.0, 4.0])
    actual = calibrated_window_radon(truth @ response.T, noise, response)
    np.testing.assert_allclose(actual["component_rates"], truth)
    ground = truth.copy()
    ground[:, 3] = 0
    np.testing.assert_allclose(actual["corrected_window_rates"], ground @ response.T)
    inverse = np.linalg.inv(response)
    projection = np.eye(4) - response[:, 3, None] @ inverse[3, None, :]
    expected = projection @ noise @ projection.T
    np.testing.assert_allclose(
        actual["corrected_window_covariance"], np.broadcast_to(expected, (2, 4, 4))
    )


def test_full_spectrum_separation_dense_gls_reference_and_signed_estimates():
    rng = np.random.default_rng(17)
    response = rng.uniform(0.1, 2.0, (13, 4))
    truth = np.array([[1.0, 2.0, 3.0, 4.0], [2.0, 3.0, 4.0, -1.0]])
    std = np.linspace(0.2, 0.7, 13)
    y = truth @ response.T
    actual = full_spectrum_radon(y, response, std, ["K", "U", "Th", "Rn"])
    np.testing.assert_allclose(actual["component_rates"], truth, atol=1e-12)
    weight = np.diag(1 / std**2)
    cov = np.linalg.inv(response.T @ weight @ response)
    operator = cov @ response.T @ weight
    projection = np.eye(13) - response[:, 3, None] @ operator[3, None, :]
    np.testing.assert_allclose(
        actual["component_covariance"], np.broadcast_to(cov, (2, 4, 4)), atol=1e-12
    )
    np.testing.assert_allclose(
        actual["corrected_variance"],
        np.broadcast_to(np.diag(projection @ np.diag(std**2) @ projection.T), (2, 13)),
        atol=1e-12,
    )
    assert actual["negative_components"][1, 3]
    with pytest.raises(ValueError, match="rank deficient|ill-conditioned"):
        full_spectrum_radon(y, np.ones((13, 4)), std, ["K", "U", "Th", "Rn"])
    with pytest.raises(InterruptedError):
        full_spectrum_radon(
            y, response, std, ["K", "U", "Th", "Rn"], canceled=lambda: True
        )


def test_background_channels_accept_calibrated_time_varying_radon_and_nulls():
    np.testing.assert_allclose(
        background_correction(
            [10.0, 20.0, np.nan], 1.0, [2.0, 3.0, 4.0], [3.0, 5.0, 6.0]
        ),
        [4.0, 11.0, np.nan],
        equal_nan=True,
    )
    with pytest.raises(ValueError):
        background_correction([1.0], radon=[np.inf])


@pytest.mark.parametrize("model", ["spherical", "exponential", "gaussian"])
def test_ordinary_kriging_against_independent_covariance_equations(model):
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [2.0, 0.5]])
    z = np.array([1.0, 2.0, 4.0, 3.0, 5.0])
    query = np.array([[0.3, 0.4], [0.8, 0.7]])
    partial, nugget, ran = 2.0, 0.2, 3.0
    result = ordinary_kriging(
        xy, z, query, ran, partial, nugget, model=model, neighbors=5
    )

    def covariance(a, b):
        h = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=-1) / ran
        if model == "spherical":
            corr = np.where(h < 1, 1 - 1.5 * h + 0.5 * h**3, 0.0)
        elif model == "exponential":
            corr = np.exp(-3 * h)
        else:
            corr = np.exp(-3 * h * h)
        return partial * corr + nugget * (h == 0)

    c = covariance(xy, xy)
    matrix = np.block([[c, np.ones((5, 1))], [np.ones((1, 5)), np.zeros((1, 1))]])
    rhs = np.vstack([covariance(xy, query), np.ones(2)])
    solution = np.linalg.solve(matrix, rhs)
    expected = z @ solution[:-1]
    variance = (
        partial + nugget - np.sum(solution[:-1] * rhs[:-1], axis=0) - solution[-1]
    )
    np.testing.assert_allclose(result["predicted"], expected, atol=1e-12)
    np.testing.assert_allclose(result["variance"], variance, atol=1e-12)
    exact = ordinary_kriging(xy, z, xy, ran, partial, nugget, model=model, neighbors=5)
    np.testing.assert_allclose(exact["predicted"], z, atol=1e-12)
    np.testing.assert_allclose(exact["variance"], 0.0, atol=1e-12)


def test_kriging_support_and_budget():
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    result = ordinary_kriging(
        xy, [1.0, 2.0, 3.0], [[10.0, 10.0]], 2.0, 1.0, search_radius_m=1.0
    )
    assert np.isnan(result["predicted"]).all()
    exact = ordinary_kriging(
        xy, [1.0, 2.0, 3.0], [[0.0, 0.0]], 2.0, 1.0, search_radius_m=0.1
    )
    np.testing.assert_array_equal(exact["predicted"], [1.0])
    np.testing.assert_array_equal(exact["variance"], [0.0])
    with pytest.raises(ValueError, match="Duplicate"):
        ordinary_kriging([[0, 0], [0, 0], [1, 1]], [1, 2, 3], [[1, 1]], 2.0, 1.0)
    with pytest.raises(ValueError, match="budget"):
        ordinary_kriging(xy, [1.0, 2.0, 3.0], [[0.0, 0.0]], 2.0, 1.0, max_elements=1)
    with pytest.raises(InterruptedError):
        ordinary_kriging(
            xy, [1.0, 2.0, 3.0], [[0.0, 0.0]], 2.0, 1.0, canceled=lambda: True
        )


def test_empirical_variogram_pairs_direction_sampling_and_right_edge():
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [2.0, 0.0]])
    z = np.array([0.0, 1.0, 2.0, 3.0])
    result = empirical_variogram(xy, z, [0.0, 1.0, 2.0, 3.0])
    counts = np.zeros(3, int)
    total = np.zeros(3)
    for i in range(4):
        for j in range(i + 1, 4):
            d = np.linalg.norm(xy[i] - xy[j])
            b = min(int(d), 2)
            counts[b] += 1
            total[b] += 0.5 * (z[i] - z[j]) ** 2
    np.testing.assert_array_equal(result["pair_count"], counts)
    np.testing.assert_allclose(
        result["semivariance"],
        np.divide(total, counts, out=np.full(3, np.nan), where=counts > 0),
        equal_nan=True,
    )
    east = empirical_variogram(
        xy, z, [0.0, 3.0], azimuth_deg=90.0, angular_tolerance_deg=1.0
    )
    assert east["pair_count"][0] == 3
    first = empirical_variogram(xy, z, [0.0, 3.0], max_pairs=3, seed=12)
    second = empirical_variogram(xy, z, [0.0, 3.0], max_pairs=3, seed=12)
    np.testing.assert_array_equal(first["semivariance"], second["semivariance"])
