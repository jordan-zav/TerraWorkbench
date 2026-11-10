"""Analytic, conservation, uncertainty and failure checks for new core APIs."""

import numpy as np
import pytest

from terraworkbench_core import electrical as dc
from terraworkbench_core import inversion_diagnostics as diagnostics
from terraworkbench_core import potential_tensors as tensors
from terraworkbench_core import radiometric_spectra as gamma
from terraworkbench_core import spectral_analysis as spectra


def test_psd_parseval_and_directional_anisotropy():
    x = np.arange(64) * 2.0
    a = np.cos(2 * np.pi * x / 16)[None, :] * np.ones((64, 1))
    result = spectra.grid_power_spectrum(a, (2.0, 2.0), detrend="none", window="none")
    assert result["weighted_mean_square"] == pytest.approx(0.5)
    assert result["integrated_power"] == pytest.approx(0.5)
    edges = np.linspace(0.01, np.pi / 2, 14)
    east = spectra.binned_power_spectrum(result, edges, azimuth_deg=0)
    north = spectra.binned_power_spectrum(result, edges, azimuth_deg=90)
    assert np.nansum(east["power"] * east["count"]) > 1e20 * np.nansum(
        north["power"] * north["count"]
    )
    assert east["count"].sum() > 0


def test_psd_window_plane_removal_and_errors():
    rng = np.random.default_rng(7)
    a = rng.normal(size=(32, 48))
    result = spectra.grid_power_spectrum(a, (3.0, 2.0))
    assert result["integrated_power"] == pytest.approx(result["weighted_mean_square"])
    y, x = np.indices((12, 14))
    trend = spectra.grid_power_spectrum(7 + 3 * x - 9 * y, (1.0, 1.0))
    assert trend["integrated_power"] < 1e-24
    for values, spacing in ((np.full((8, 8), np.nan), (1, 1)), (a, (-1, 1))):
        with pytest.raises(ValueError):
            spectra.grid_power_spectrum(values, spacing)
    with pytest.raises(ValueError):
        spectra.binned_power_spectrum(result, [0, 0.4, 0.2])


def test_spectral_depth_angular_wavenumber_and_conditional_errors():
    k = np.linspace(0.001, 0.02, 40)
    power = 170 * k**2 * np.exp(-2 * 125 * k)
    result = spectra.fit_spectral_depth(
        k, power, fit_range=(0.002, 0.019), geometry_exponent=2
    )
    assert result["depth_m"] == pytest.approx(125.0)
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["conditional_depth_std_m"] < 1e-10
    noise = np.random.default_rng(2).normal(0, 0.1, len(k))
    result = spectra.fit_spectral_depth(
        k,
        power * np.exp(noise),
        fit_range=(0.002, 0.019),
        geometry_exponent=2,
        log_power_std=np.full(len(k), 0.1),
    )
    assert abs(result["depth_m"] - 125) < 3 * result["conditional_depth_std_m"]
    growing = spectra.fit_spectral_depth(k, np.exp(2 * 10 * k), fit_range=(0.001, 0.02))
    assert not growing["physical_decay"]
    with pytest.raises(ValueError):
        spectra.fit_spectral_depth(k[:3], power[:3], fit_range=(0.001, 0.02))


def test_wiener_limits():
    np.testing.assert_allclose(
        spectra.wiener_inverse_transfer([1, 2j], 3, 0), [1, -0.5j]
    )
    assert spectra.wiener_inverse_transfer(0, 0, 0) == 0
    assert abs(spectra.wiener_inverse_transfer(0.01, 1, 1)) < 0.011
    with pytest.raises(ValueError):
        spectra.wiener_inverse_transfer(1, 1, -1)


def _wenner():
    # ABMN for equally spaced A M N B: K=2*pi*a.
    xyz = np.column_stack([np.arange(4) * 5.0, np.zeros((4, 2))])
    return xyz, np.array([[0, 3, 1, 2]])


def test_electrical_geometry_units_and_polarity():
    xyz, q = _wenner()
    k = dc.geometric_factor(xyz, q)
    assert k[0] == pytest.approx(2 * np.pi * 5)
    voltage = 100 / k * 0.05
    result = dc.apparent_resistivity(xyz, q, voltage, 0.05)
    assert result["rho_a_ohm_m"][0] == pytest.approx(100)
    reverse = q[:, [0, 1, 3, 2]]
    assert dc.apparent_resistivity(xyz, reverse, -voltage, 0.05)["rho_a_ohm_m"][
        0
    ] == pytest.approx(100)
    assert dc.apparent_resistivity(xyz, q, -voltage, 0.05)["negative_rho"][0]
    assert dc.geometric_factor(xyz, q, space="full")[0] == pytest.approx(2 * k[0])
    assert dc.geometric_factor(xyz, np.array([[0, -1, 1, -1]]))[0] == pytest.approx(
        k[0]
    )
    with pytest.raises(ValueError):
        dc.apparent_resistivity(xyz, q, voltage, 0)
    xyz[2, 2] = 1
    with pytest.raises(ValueError, match="horizontal"):
        dc.geometric_factor(xyz, q)


def test_reciprocal_grouping_signs_and_repeats():
    q = np.array([[0, 3, 1, 2], [3, 0, 1, 2], [1, 2, 0, 3], [1, 2, 3, 0], [0, 2, 1, 3]])
    result = dc.reciprocal_errors(q, [10.0, -10, 11, -11, 4])
    assert result["paired_groups"] == 1
    assert result["unpaired_groups"] == 1
    assert result["reciprocal_error_percent"][0] == pytest.approx(200 / 21)
    np.testing.assert_array_equal(result["repeat_counts"], [[2, 2]])
    assert dc.reciprocal_errors(q[:2], [10.0, -10])["paired_groups"] == 0


def test_ip_gate_integration_and_cole_cole_convention():
    t = np.array([0.0, 0.1, 0.3, 0.6])
    decay = 2 * (0.02 - 0.01 * t)
    # Exact for a linear decay, gate average at midpoint .225.
    result = dc.integrated_chargeability(t, decay, 2.0, gate_s=(0.05, 0.4))
    assert result == pytest.approx(1000 * (0.02 - 0.01 * 0.225))
    batch = dc.integrated_chargeability(
        t, [decay, -decay], [2.0, 2.0], gate_s=(0.05, 0.4)
    )
    np.testing.assert_allclose(batch, [result, -result])
    rho = dc.cole_cole_resistivity([0, 1, 1e20], 100.0, 0.2, 0.5, 0.8)
    assert rho[0] == 100
    assert rho[-1].real == pytest.approx(80)
    assert rho[1].imag < 0
    with pytest.raises(ValueError):
        dc.integrated_chargeability(t, decay, 2.0, gate_s=(0.05, 0.7))


def test_energy_rebin_conserves_counts_and_reports_loss_and_correlation():
    raw = np.array([10.0, 20.0])
    result = gamma.energy_rebin(raw, [0, 1, 2], [0, 0.5, 1.5, 2])
    np.testing.assert_allclose(result["counts"], [5, 15, 10])
    assert result["lost_counts"] == pytest.approx(0)
    a = result["rebin_matrix"].toarray()
    covariance = (a * raw) @ a.T
    assert covariance[0, 1] == 2.5
    np.testing.assert_allclose(np.diag(covariance), result["variance_diagonal"])
    partial = gamma.energy_rebin([raw, raw * 2], [0, 1, 2], [0.5, 1.5])
    np.testing.assert_allclose(partial["lost_counts"], [15, 30])
    with pytest.raises(ValueError):
        gamma.energy_rebin(raw, [0, 1, 1], [0, 2])


def test_calibration_and_overlapping_window_covariance():
    channels = np.array([100, 400, 800, 1500])
    fit = gamma.fit_energy_calibration(
        channels, 3.2 + 1.5 * channels, energy_std=np.ones(4)
    )
    assert fit["offset"] == pytest.approx(3.2)
    assert fit["gain"] == pytest.approx(1.5)
    assert np.linalg.eigvalsh(fit["covariance"]).min() > 0
    result = gamma.integrate_energy_windows(
        [10.0, 20.0], [0, 1, 2], [[0, 1.5], [0.5, 2]]
    )
    np.testing.assert_allclose(result["counts"], [20, 25])
    np.testing.assert_allclose(result["covariance"], [[15, 15], [15, 22.5]])
    transformed = gamma.linear_covariance_transform(
        result["counts"], result["covariance"], [[1, -1]]
    )
    assert transformed["values"][0] == -5
    assert transformed["covariance"][0, 0] == pytest.approx(7.5)
    with pytest.raises(ValueError):
        gamma.linear_covariance_transform([1, 2], [[1, 2], [2, 1]], [[1, 0]])


def test_nasvd_full_rank_reconstruction_and_poisson_noise_reduction():
    rng = np.random.default_rng(12)
    exposure = np.linspace(0.5, 2.0, 100)
    rates = np.r_[np.linspace(20, 70, 30), 0]
    truth = exposure[:, None] * rates
    raw = rng.poisson(truth).astype(float)
    full = gamma.poisson_nasvd(raw, min(raw.shape), exposure_s=exposure)
    np.testing.assert_allclose(full["counts"], raw, atol=1e-12)
    reduced = gamma.poisson_nasvd(raw, 1, exposure_s=exposure)
    assert np.mean((reduced["counts"] - truth) ** 2) < 0.2 * np.mean((raw - truth) ** 2)
    assert np.all(reduced["counts"][:, -1] == 0)
    assert gamma.poisson_nasvd(np.zeros((3, 4)), 1)["rank"] == 0
    with pytest.raises(ValueError, match="budget"):
        gamma.poisson_nasvd(raw, 1, max_elements=10)


def test_full_spectrum_fit_identifiability_and_covariance():
    response = np.array([[1.0, 0], [0.5, 0.3], [0, 1], [0.2, 1.2]])
    fit = gamma.fit_full_spectrum(
        response @ np.array([3.0, 5]), response, count_std=np.ones(4)
    )
    np.testing.assert_allclose(fit["coefficients"], [3, 5], atol=1e-12)
    np.testing.assert_allclose(
        fit["conditional_covariance"], np.linalg.inv(response.T @ response)
    )
    with pytest.raises(ValueError, match="identifiable"):
        gamma.fit_full_spectrum(np.ones(4), np.ones((4, 2)), count_std=np.ones(4))


def test_linear_resolution_known_diagonal_and_doi():
    result = diagnostics.linear_resolution(
        np.diag([1.0, 2]), np.ones(2), np.eye(2), beta=1
    )
    np.testing.assert_allclose(result["posterior_covariance"], np.diag([0.5, 0.2]))
    np.testing.assert_allclose(result["resolution"], np.diag([0.5, 0.8]))
    assert result["effective_parameters"] == pytest.approx(1.3)
    doi = diagnostics.reference_model_doi(
        [3.0, 2], [1.0, 2], [4.0, 1], [0.0, 1], minimum_contrast=0.1
    )
    assert doi["doi"][0] == 0.5
    assert np.isnan(doi["doi"][1])
    with pytest.raises(ValueError, match="budget"):
        diagnostics.linear_resolution(
            np.eye(10), np.ones(10), np.eye(10), beta=1, max_elements=10
        )
    with pytest.raises(ValueError, match="constrain"):
        diagnostics.linear_resolution(
            np.zeros((2, 2)), np.ones(2), np.zeros((2, 2)), beta=1
        )


def test_tensor_rotations_invariant_and_reject_reflection():
    a = np.array([[3.0, 2, 0], [2, -2, 1], [0, 1, -1]])
    angle = 0.7
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
    )
    rotated = tensors.rotate_tensor(a, rotation)
    original, transformed = (
        tensors.tensor_invariants(a),
        tensors.tensor_invariants(rotated),
    )
    for key in original:
        np.testing.assert_allclose(original[key], transformed[key], atol=1e-12)
    with pytest.raises(ValueError):
        tensors.rotate_tensor(a, np.diag([1, 1, -1]))


def test_prism_tensor_point_mass_limit_and_laplace():
    pytest.importorskip("harmonica")
    xyz = np.array([[50.0, 80, 200], [-70.0, 20, 240]])
    prism = np.array([[-1.0, 1, -1, 1, -102, -100]])
    result = tensors.prism_gravity_tensor(xyz, prism, [1000.0], block_size=1)
    radius = xyz - np.array([0, 0, -101])
    length = np.linalg.norm(radius, axis=1)
    point = (
        6.67430e-11
        * 8000
        * (
            3 * radius[:, :, None] * radius[:, None, :] / length[:, None, None] ** 5
            - np.eye(3) / length[:, None, None] ** 3
        )
        * 1e9
    )
    np.testing.assert_allclose(result["tensor_eotvos"], point, rtol=2e-4, atol=1e-8)
    np.testing.assert_allclose(result["invariants"]["trace"], 0, atol=1e-10)
    with pytest.raises(InterruptedError):
        tensors.prism_gravity_tensor(xyz, prism, [1000.0], cancel=lambda: True)


def test_fdem_halfspace_analytic_and_conductivity_recovery():
    pytest.importorskip("simpeg")
    from geoana.em.fdem import MagneticDipoleHalfSpace
    from scipy.constants import mu_0
    from terraworkbench_core.layered_em import fdem_layered, fit_fdem_conductivity

    f = np.logspace(2, 4, 9)
    geometry = dict(source_m=[0.0, 0, 0], receiver_m=[10.0, 0, 0])
    predicted = fdem_layered(f, [0.03], [], **geometry)["secondary_b_t"]
    analytic = MagneticDipoleHalfSpace(
        f, sigma=0.03, orientation="Z", location=[0, 0, 0]
    )
    reference = analytic.magnetic_field(np.array([10.0, 0]))[:, 2] * mu_0
    np.testing.assert_allclose(predicted, reference, rtol=1e-3, atol=1e-15)
    fit = fit_fdem_conductivity(
        f,
        predicted,
        real_std_t=np.full(9, 1e-12),
        imag_std_t=np.full(9, 1e-12),
        initial_conductivity_s_m=[0.01],
        thicknesses_m=[],
        **geometry,
    )
    assert fit["success"]
    assert fit["conductivity_s_m"][0] == pytest.approx(0.03, rel=1e-4)
    with pytest.raises(InterruptedError):
        fit_fdem_conductivity(
            f,
            predicted,
            real_std_t=np.full(9, 1e-12),
            imag_std_t=np.full(9, 1e-12),
            initial_conductivity_s_m=[0.01],
            thicknesses_m=[],
            cancel=lambda: True,
            **geometry,
        )


def test_tem_analytic_sign_and_gate_convergence():
    pytest.importorskip("simpeg")
    from geoana.em.tdem import VerticalMagneticDipoleHalfSpace
    from scipy.constants import mu_0
    from terraworkbench_core.layered_em import tem_stepoff_layered, tem_gate_average

    times = np.logspace(-4, -2, 7)
    geometry = dict(source_m=[0.0, 0, 0], receiver_m=[10.0, 0, 0])
    predicted = tem_stepoff_layered(times, [0.03], [], **geometry)["dbdt_t_s"]
    analytic = VerticalMagneticDipoleHalfSpace(times, sigma=0.03, location=[0, 0, 0])
    reference = analytic.magnetic_field_time_derivative([10.0, 0])[:, 2] * mu_0
    np.testing.assert_allclose(predicted, reference, rtol=0.02, atol=1e-14)
    gates = [[0.0001, 0.0003], [0.001, 0.002]]
    a = tem_gate_average(gates, [0.03], [], quadrature_order=6, **geometry)
    b = tem_gate_average(gates, [0.03], [], quadrature_order=12, **geometry)
    np.testing.assert_allclose(a["gate_dbdt_t_s"], b["gate_dbdt_t_s"], rtol=1e-4)


def test_mt_halfspace_units_thick_layer_limits_and_phase_tensor():
    from scipy.constants import mu_0
    from terraworkbench_core import magnetotellurics as mt

    f = np.logspace(-3, 3, 30)
    z = mt.layered_impedance(f, [100.0], [])["impedance_ohm"]
    response = mt.apparent_resistivity_phase(f, z)
    np.testing.assert_allclose(response["rho_a_ohm_m"], 100.0)
    np.testing.assert_allclose(response["phase_deg"], 45.0)
    converted = mt.mt_units_to_ohms(z / (1000 * mu_0))
    np.testing.assert_allclose(converted, z)
    homogeneous = mt.layered_impedance(f, [100.0, 100, 100], [20.0, 400])[
        "impedance_ohm"
    ]
    np.testing.assert_allclose(homogeneous, z)
    thick = mt.layered_impedance(f, [100.0, 1.0], [1e10])["impedance_ohm"]
    np.testing.assert_allclose(thick, z)
    impedance = np.zeros((len(f), 2, 2), dtype=complex)
    impedance[:, 0, 1], impedance[:, 1, 0] = z, -z
    np.testing.assert_allclose(
        mt.phase_tensor(impedance)["phase_tensor"],
        np.broadcast_to(np.eye(2), (len(f), 2, 2)),
    )
    distortion = np.array([[2.0, 0.4], [0.1, 0.7]])
    np.testing.assert_allclose(
        mt.phase_tensor(distortion @ impedance)["phase_tensor"],
        mt.phase_tensor(impedance)["phase_tensor"],
        atol=1e-14,
    )
    with pytest.raises(ValueError, match="condition"):
        mt.phase_tensor(np.ones((2, 2), complex))


def test_mt_two_layer_recovery_and_failure_status():
    from terraworkbench_core import magnetotellurics as mt

    f = np.logspace(-2, 3, 40)
    z = mt.layered_impedance(f, [40.0, 500.0], [200.0])["impedance_ohm"]
    std = abs(z) * 0.02
    args = dict(
        real_std_ohm=std,
        imag_std_ohm=std,
        initial_resistivity_ohm_m=[80.0, 200.0],
        thicknesses_m=[200.0],
    )
    fit = mt.fit_layered_resistivity(f, z, **args)
    assert fit["success"]
    np.testing.assert_allclose(fit["resistivity_ohm_m"], [40.0, 500.0], rtol=1e-5)
    incomplete = mt.fit_layered_resistivity(f, z, max_evaluations=1, **args)
    assert not incomplete["success"]
    with pytest.raises(InterruptedError):
        mt.fit_layered_resistivity(f, z, cancel=lambda: True, **args)


def test_gravity_network_drift_and_exact_anchor_recovery():
    from terraworkbench_core.gravity_network import adjust_gravity_network

    station = np.array(["BASE", "A", "B", "BASE", "A", "B", "BASE"])
    times = np.arange(7) * 100.0
    true_gravity = {"BASE": 980000.0, "A": 980001.2, "B": 979999.3}
    readings = np.array([true_gravity[s] for s in station]) + 3.4 + 0.001 * times
    fit = adjust_gravity_network(
        station,
        np.repeat("METER1", 7),
        times,
        readings,
        np.full(7, 0.01),
        anchors_mgal={"BASE": 980000.0},
    )
    for s, g in zip(fit["station_ids"], fit["gravity_mgal"]):
        assert g == pytest.approx(true_gravity[s], abs=1e-8)
    assert fit["drift_coefficients_mgal"][0, 1] / fit["time_scales_s"][
        0
    ] == pytest.approx(0.001, abs=1e-10)
    assert fit["degrees_of_freedom"] == 3
    assert fit["chi_squared"] < 1e-12
    with pytest.raises(ValueError, match="Rank"):
        adjust_gravity_network(
            ["BASE", "A", "B"],
            ["one", "two", "two"],
            [0, 1, 2],
            [1, 2, 3],
            [0.1, 0.1, 0.1],
            anchors_mgal={"BASE": 1.0},
        )


def test_gravity_density_identifiability():
    from terraworkbench_core.gravity_network import fit_bouguer_density

    effect = np.linspace(0.001, 0.02, 20)
    gravity = 4.3 + 2670 * effect
    fit = fit_bouguer_density(gravity, effect, gravity_std_mgal=np.full(20, 0.02))
    assert fit["density_kg_m3"] == pytest.approx(2670.0)
    assert fit["conditional_density_std_kg_m3"] > 0
    assert fit["chi_squared"] < 1e-20
    with pytest.raises(ValueError, match="separable"):
        fit_bouguer_density(gravity, np.ones(20), gravity_std_mgal=np.full(20, 0.02))


def test_operation_catalog_provenance_no_input_mutation():
    import json
    from terraworkbench_core.operations import (
        list_operations,
        operation_info,
        run_operation,
    )

    entries = list_operations()
    assert len(entries) >= 30
    assert len({row["id"] for row in entries}) == len(entries)
    assert operation_info("fdem.layered_forward")["optional_engine"] == "SimPEG 0.25.x"
    values = np.arange(64.0).reshape(8, 8)
    original = values.copy()
    args = dict(values=values, spacing=(2.0, 3.0))
    first = run_operation("spectra.grid_psd", **args)
    second = run_operation("spectra.grid_psd", **args)
    np.testing.assert_array_equal(values, original)
    assert first["provenance"]["input_sha256"] == second["provenance"]["input_sha256"]
    assert len(first["provenance"]["source_sha256"]) == 64
    json.dumps(first["provenance"], allow_nan=False)
    args["values"] = values + 1
    changed = run_operation("spectra.grid_psd", **args)
    assert changed["provenance"]["input_sha256"] != first["provenance"]["input_sha256"]
    with pytest.raises(ValueError):
        run_operation("not_implemented")


def test_dc_sounding_halfspace_layer_recovery_and_remote_electrodes():
    pytest.importorskip("simpeg")
    from terraworkbench_core.layered_electrical import dc_layered, fit_dc_resistivity

    spacings = np.logspace(0, 2.5, 20)
    xyz = np.array(
        [
            [position * a, 0.0, 123.0]
            for a in spacings
            for position in (-1.5, -0.5, 0.5, 1.5)
        ]
    )
    q = np.array(
        [[4 * i, 4 * i + 3, 4 * i + 1, 4 * i + 2] for i in range(len(spacings))]
    )
    homogeneous = dc_layered(xyz, q, [100.0], [])
    np.testing.assert_allclose(homogeneous["rho_a_ohm_m"], 100.0, rtol=1e-3)
    remote = dc_layered(xyz, [[0, -1, 1, -1]], [100.0], [])
    assert remote["rho_a_ohm_m"][0] == pytest.approx(100.0, rel=1e-3)
    two_layer = dc_layered(xyz, q, [60.0, 400.0], [25.0])
    assert two_layer["rho_a_ohm_m"][0] < two_layer["rho_a_ohm_m"][-1]
    fit = fit_dc_resistivity(
        xyz,
        q,
        two_layer["resistance_ohm"],
        resistance_std_ohm=abs(two_layer["resistance_ohm"]) * 0.02,
        initial_resistivity_ohm_m=[100.0, 200.0],
        thicknesses_m=[25.0],
    )
    assert fit["success"]
    np.testing.assert_allclose(fit["resistivity_ohm_m"], [60.0, 400.0], rtol=1e-4)


def test_equivalent_sources_holdout_on_different_height_and_budget():
    pytest.importorskip("harmonica")
    from terraworkbench_core.equivalent_sources import equivalent_source_predict

    x, y = np.meshgrid(np.linspace(-100, 100, 7), np.linspace(-100, 100, 7))
    obs = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])
    sources = np.array([[-40.0, 20, -70], [50, -30, -60]])
    coefficients = np.array([300.0, -120.0])

    def analytic(coordinates):
        return np.sum(
            coefficients / np.linalg.norm(coordinates[:, None, :] - sources, axis=-1),
            axis=1,
        )

    target = obs[::2] + [7.0, 12, 30]
    result = equivalent_source_predict(
        obs, analytic(obs), sources, target, damping=None, prediction_block_size=5
    )
    np.testing.assert_allclose(result["predicted"], analytic(target), atol=1e-12)
    np.testing.assert_allclose(result["source_coefficients"], coefficients, atol=1e-10)
    with pytest.raises(ValueError, match="budget"):
        equivalent_source_predict(
            obs, analytic(obs), sources, target, damping=None, max_kernel_elements=5
        )
    with pytest.raises(InterruptedError):
        equivalent_source_predict(
            obs, analytic(obs), sources, target, damping=None, cancel=lambda: True
        )


def test_catalog_has_real_callables_and_valid_backlog_links():
    import importlib
    import inspect
    import json
    from pathlib import Path
    from terraworkbench_core.operations import list_operations, operation_info

    root = Path(__file__).resolve().parents[1]
    backlog = json.loads(
        (root / "docs/research/geophysics_backlog.json").read_text(encoding="utf-8")
    )
    candidate_ids = {
        family["id"] + "-" + str(i).zfill(2)
        for family in backlog["families"]
        for i in range(1, len(family["candidates"]) + 1)
    }
    for row in list_operations():
        info = operation_info(row["id"])
        assert row["related_backlog_candidate"] in candidate_ids
        assert info["documentation"]
        assert info["backlog_coverage"] == "partial"
        assert info["validation"] == "synthetic_tests_only"
        assert isinstance(info["signature"], str)
        assert inspect.isfunction(
            getattr(importlib.import_module(info["module"]), info["function"])
        )


def test_base_operations_work_without_optional_engines_or_qgis():
    import subprocess
    import sys

    code = """
import sys
class BlockOptional:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qgis','PyQt5','PyQt6','simpeg','harmonica'}:
            raise AssertionError('Unexpected optional dependency: '+fullname)
sys.meta_path.insert(0, BlockOptional())
from terraworkbench_core.operations import list_operations, operation_info, run_operation
assert len(list_operations()) >= 79
assert operation_info('fdem.layered_forward')['optional_extra'] == 'em'
assert operation_info('potential.equivalent_sources')['optional_extra'] == 'prisms'
mt = run_operation('mt.layered_forward', frequency_hz=[1.,10.], resistivity_ohm_m=[100.], thicknesses_m=[])
assert mt['provenance']['status'] == 'completed'
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_masked_data_are_not_silently_treated_as_observations():
    from terraworkbench_core.operations import run_operation

    a = np.ma.array(np.ones((8, 8)), mask=False)
    a.mask[0, 0] = True
    with pytest.raises(ValueError, match="Masked"):
        spectra.grid_power_spectrum(a, (1, 1))
    with pytest.raises(ValueError, match="Masked"):
        run_operation("spectra.grid_psd", values=a, spacing=(1, 1))
    c = np.ma.array([[1.0, 3.0], [2.0, 4.0]], mask=[[False, True], [False, False]])
    with pytest.raises(ValueError, match="Masked"):
        gamma.poisson_nasvd(c, 1)
