"""Quasi-static 3D EM units, analytic full-space, inversion and safety tests."""

import numpy as np
import pytest

from terraworkbench_core.fdem_3d import fdem_3d_forward, fit_fdem_3d_zones
from terraworkbench_core.complex_calibration import (
    fit_complex_response,
    apply_complex_response,
)


def test_calibrated_fdem_inverse_uses_full_real_imaginary_covariance():
    pytest.importorskip("simpeg")
    args = dict(
        mesh_widths=[np.full(4, 5.0)] * 3,
        mesh_origin=[-10.0] * 3,
        source_m=[0.0, 0.0, 0.0],
        receiver_m=[5.0, 0.0, 0.0],
        parameter_labels=np.zeros(64, int),
    )
    frequency = [1000.0, 10000.0]
    true_b = fdem_3d_forward(**args, frequency_hz=frequency, conductivity_s_m=[0.1])[
        "secondary_b_t"
    ]
    refs = np.array([0j, 1e-10 + 0j, -1e-10 + 1e-10j, 1e-10 + 1e-10j])
    gain, offset = 1.3 + 0.4j, 2e-13 - 1e-13j
    calibration = fit_complex_response(refs, gain * refs + offset, np.eye(2) * 1e-28)
    corrected = apply_complex_response(
        gain * true_b + offset,
        [[1e-28, 0.3e-28], [0.3e-28, 2e-28]],
        calibration=calibration,
    )
    fit = fit_fdem_3d_zones(
        **args,
        frequency_hz=frequency,
        observed_secondary_b_t=corrected["corrected"],
        data_covariance_t2=corrected["covariance_real_imag"],
        initial_conductivity_s_m=[0.08],
        reference_conductivity_s_m=[0.1],
        beta=1e-6,
    )
    assert fit["success"]
    np.testing.assert_allclose(fit["conductivity_s_m"], [0.1], rtol=1e-5)
    delta = fit["predicted_secondary_b_t"] - corrected["corrected"]
    d = np.column_stack([delta.real, delta.imag])
    expected_chi = np.einsum(
        "ni,nij,nj->", d, np.linalg.inv(corrected["covariance_real_imag"]), d
    )
    assert fit["data_chi_squared"] == pytest.approx(expected_chi, abs=1e-16)
    assert "Full within-record" in fit["data_noise_model"]
    with pytest.raises(ValueError, match="not both"):
        fit_fdem_3d_zones(
            **args,
            frequency_hz=frequency,
            observed_secondary_b_t=true_b,
            real_std_t=[1e-14] * 2,
            imag_std_t=[1e-14] * 2,
            data_covariance_t2=np.eye(2) * 1e-28,
            initial_conductivity_s_m=[0.08],
            reference_conductivity_s_m=[0.1],
            beta=1e-6,
        )


def domain():
    h = np.r_[
        1.0 * 2 ** np.arange(3, 0, -1), np.ones(4) * 1.0, 1.0 * 2 ** np.arange(1, 4)
    ]
    return dict(
        mesh_widths=[h, h, h],
        mesh_origin=[-h.sum() / 2] * 3,
        source_m=[0.0, 0.0, 0.0],
        receiver_m=[1.5, 0.0, 0.0],
        parameter_labels=np.zeros(len(h) ** 3, dtype=int),
    )


def test_fdem_3d_analytic_fullspace_and_moment_units():
    pytest.importorskip("simpeg")
    from geoana.em.fdem import MagneticDipoleWholeSpace
    from scipy.constants import mu_0

    coarse = np.full(8, 4.0)
    args = dict(
        mesh_widths=[coarse, coarse, coarse],
        mesh_origin=[-coarse.sum() / 2] * 3,
        source_m=[0.0, 0.0, 0.0],
        receiver_m=[5.0, 0.0, 0.0],
        parameter_labels=np.zeros(len(coarse) ** 3, int),
        max_cells=2000,
        max_unknowns=8000,
    )
    frequency = np.array([10000.0])
    result = fdem_3d_forward(**args, frequency_hz=frequency, conductivity_s_m=[1.0])
    analytic = MagneticDipoleWholeSpace(
        frequency,
        sigma=1.0,
        orientation="Z",
        location=[0.0, 0.0, 0.0],
        quasistatic=True,
    )
    total = np.asarray(analytic.magnetic_flux_density(np.array(args["receiver_m"])))[
        ..., 2
    ]
    static = -mu_0 / (4 * np.pi * 5.0**3)
    expected = total - static
    np.testing.assert_allclose(
        result["secondary_b_t"], np.atleast_1d(expected), rtol=0.7, atol=1e-14
    )
    scaled = fdem_3d_forward(
        **args, frequency_hz=frequency, conductivity_s_m=[1.0], moment_a_m2=2.0
    )
    np.testing.assert_allclose(
        scaled["secondary_b_t"], 2 * result["secondary_b_t"], rtol=1e-10, atol=1e-20
    )
    # Refine the ENTIRE domain: core-only refinement with fixed coarse padding
    # did not show monotonic error reduction. This is one full-space benchmark,
    # not a claim of monotonic convergence for arbitrary adaptive meshes.
    fine = np.full(16, 2.0)
    refined_args = dict(
        args,
        mesh_widths=[fine, fine, fine],
        parameter_labels=np.zeros(len(fine) ** 3, int),
        max_cells=5000,
        max_unknowns=16000,
    )
    refined = fdem_3d_forward(
        **refined_args, frequency_hz=frequency, conductivity_s_m=[1.0]
    )
    coarse_error = abs(result["secondary_b_t"] - expected) / abs(expected)
    fine_error = abs(refined["secondary_b_t"] - expected) / abs(expected)
    assert fine_error[0] < coarse_error[0]
    assert fine_error[0] < 0.1


def test_fdem_3d_input_budgets_and_cancel_before_optional_backend():
    args = domain()
    with pytest.raises(ValueError, match="budget"):
        fdem_3d_forward(
            **args, frequency_hz=[100.0], conductivity_s_m=[0.1], max_cells=1
        )
    with pytest.raises(InterruptedError):
        fdem_3d_forward(
            **args, frequency_hz=[100.0], conductivity_s_m=[0.1], cancel=lambda: True
        )
    with pytest.raises(ValueError, match="Coincident"):
        fdem_3d_forward(
            **{**args, "receiver_m": args["source_m"]},
            frequency_hz=[100.0],
            conductivity_s_m=[0.1],
        )


def test_fdem_3d_zone_fit_and_strict_forward_budget():
    pytest.importorskip("simpeg")
    from discretize import TensorMesh

    h = np.r_[8.0, 4.0, np.repeat(2.0, 4), 4.0, 8.0]
    mesh = TensorMesh([h, h, h], x0=[-h.sum() / 2] * 3)
    x, y, z = mesh.cell_centers.T
    labels = ((abs(x) < 4) & (abs(y) < 4) & (z < 0) & (z > -4)).astype(int)
    args = dict(
        mesh_widths=[h, h, h],
        mesh_origin=mesh.x0,
        source_m=[0.0, 0.0, 0.0],
        receiver_m=[3.0, 0.0, 0.0],
        parameter_labels=labels,
    )
    f = [1000.0, 10000.0]
    truth = [0.1, 0.3]
    observed = fdem_3d_forward(**args, frequency_hz=f, conductivity_s_m=truth)[
        "secondary_b_t"
    ]
    inverse_args = dict(
        **args,
        frequency_hz=f,
        observed_secondary_b_t=observed,
        real_std_t=abs(observed) * 0.02 + 1e-14,
        imag_std_t=abs(observed) * 0.02 + 1e-14,
        initial_conductivity_s_m=[0.08, 0.25],
        reference_conductivity_s_m=[0.1, 0.1],
        beta=1e-6,
    )
    fit = fit_fdem_3d_zones(**inverse_args)
    assert fit["success"]
    np.testing.assert_allclose(fit["conductivity_s_m"], truth, rtol=0.005)
    with pytest.raises(RuntimeError, match="budget"):
        fit_fdem_3d_zones(**inverse_args, max_forward_evaluations=1)
    with pytest.raises(InterruptedError):
        fit_fdem_3d_zones(**inverse_args, cancel=lambda: True)


def test_fdem_frequency_row_order_and_repeated_sources():
    pytest.importorskip("simpeg")
    h = np.r_[8.0, 4.0, np.repeat(2.0, 4), 4.0, 8.0]
    args = dict(
        mesh_widths=[h, h, h],
        mesh_origin=[-h.sum() / 2] * 3,
        source_m=[0.0, 0.0, 0.0],
        receiver_m=[3.0, 0.0, 0.0],
        parameter_labels=np.zeros(len(h) ** 3, int),
    )
    result = fdem_3d_forward(
        **args, frequency_hz=[10000.0, 1000.0, 10000.0], conductivity_s_m=[0.1]
    )
    np.testing.assert_allclose(
        result["secondary_b_t"][0], result["secondary_b_t"][2], rtol=1e-12
    )
    assert result["frequency_factorizations"] == 2
