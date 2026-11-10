"""Recovery gates must reject data-equivalent wrong bodies and invalid priors."""

import numpy as np
import pytest

from terraworkbench_core.spatial_constraints import spatial_property_constraints
from terraworkbench_core.recovery_metrics import model_recovery_metrics


CRITERIA = dict(
    location_tolerance_m=50.0,
    volume_relative_tolerance=0.35,
    contrast_relative_tolerance=0.35,
    support_dice_min=0.6,
    direction_tolerance_deg=15.0,
    model_relative_tolerance=0.5,
)


def assess(xyz, model, truth, **options):
    return model_recovery_metrics(
        xyz,
        np.ones(len(xyz)),
        model,
        truth,
        criteria=CRITERIA,
        connectivity_radius_m=101.0,
        **options,
    )


@pytest.mark.parametrize("vector", [False, True])
def test_exact_geometry_properties_and_direction_pass(vector):
    xyz = np.array([[0.0, 0.0, -100.0], [100.0, 0.0, -100.0], [200.0, 0.0, -100.0]])
    truth = np.array([1.0, 1.0, 0.0])
    if vector:
        truth = truth[:, None] * np.array([1.0, 2.0, -1.0])
    result = assess(xyz, truth, truth, vector=vector)
    assert result["recovery_passed"]
    assert result["support_dice"] == pytest.approx(1.0)
    assert result["maximum_location_error_m"] == 0.0
    assert result["volume_relative_error"] == 0.0


@pytest.mark.parametrize("vector", [False, True])
def test_relative_model_error_uses_physical_cell_volumes(vector):
    xyz = np.array([[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]])
    volumes = np.array([1.0, 9.0])
    truth, model = np.array([1.0, 1.0]), np.array([2.0, 1.0])
    if vector:
        truth = truth[:, None] * np.array([1.0, 2.0, -1.0])
        model = model[:, None] * np.array([1.0, 2.0, -1.0])
    result = model_recovery_metrics(
        xyz,
        volumes,
        model,
        truth,
        criteria=CRITERIA,
        connectivity_radius_m=101.0,
        vector=vector,
    )
    # The only error lies in the cell occupying one tenth of the volume.
    assert result["model_relative_error"] == pytest.approx(np.sqrt(0.1))
    assert result["model_relative_error"] != pytest.approx(np.sqrt(0.5))
    scaled = model_recovery_metrics(
        xyz,
        volumes * 1000,
        model,
        truth,
        criteria=CRITERIA,
        connectivity_radius_m=101.0,
        vector=vector,
    )
    assert scaled["model_relative_error"] == pytest.approx(
        result["model_relative_error"]
    )


def test_perfect_data_fit_does_not_pass_wrong_location():
    xyz = np.array([[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]])
    sensitivity = np.array([[1.0, 1.0]])
    truth, model = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    np.testing.assert_array_equal(sensitivity @ truth, sensitivity @ model)
    result = assess(xyz, model, truth)
    assert result["recovery_status"] == "recovery_failed"
    assert not result["checks"]["location"] and not result["checks"]["support"]


@pytest.mark.parametrize("vector", [False, True])
def test_reversed_polarity_or_direction_fails_despite_same_support(vector):
    xyz = np.array([[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]])
    truth = np.ones(2)
    if vector:
        truth = truth[:, None] * np.array([0.0, 0.0, 1.0])
    result = assess(xyz, -truth, truth, vector=vector)
    assert result["support_dice"] == 1.0
    assert not result["recovery_passed"]
    assert not result["checks"]["direction" if vector else "polarity"]


def test_missing_body_reports_failure_without_nan_or_infinite_metrics():
    xyz = np.array([[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]])
    result = assess(xyz, np.zeros(2), np.ones(2))
    assert result["maximum_location_error_m"] is None
    assert result["predicted_component_count"] == 0
    assert not result["recovery_passed"]
    import json

    json.dumps(result, allow_nan=False)


def test_multiple_bodies_are_matched_and_not_replaced_by_global_centroid():
    xyz = np.array([[-200.0, 0.0, -100.0], [0.0, 0.0, -100.0], [200.0, 0.0, -100.0]])
    result = assess(xyz, [0.0, 2.0, 0.0], [1.0, 0.0, 1.0])
    assert result["truth_component_count"] == 2
    assert result["predicted_component_count"] == 1
    assert not result["checks"]["location"]


def test_recovery_budgets_and_predeclared_criteria_are_required():
    xyz = np.c_[np.arange(10.0), np.zeros(10), np.zeros(10)]
    with pytest.raises(ValueError, match="link budget"):
        assess(xyz, np.ones(10), np.ones(10), max_links=1)
    with pytest.raises(InterruptedError):
        assess(xyz, np.ones(10), np.ones(10), canceled=lambda: True)
    with pytest.raises(ValueError, match="nonzero"):
        assess(xyz, np.zeros(10), np.zeros(10))
    with pytest.raises(ValueError, match="criteria"):
        model_recovery_metrics(
            xyz,
            np.ones(10),
            np.ones(10),
            np.ones(10),
            criteria={},
            connectivity_radius_m=1.0,
        )


def test_explicit_hard_support_and_soft_depth_weights():
    xyz = np.array([[0.0, 0.0, -50.0], [0.0, 0.0, -150.0], [300.0, 0.0, -150.0]])
    hard = spatial_property_constraints(
        xyz,
        lower=0.0,
        upper=0.8,
        background_value=0.0,
        support_prisms_m=[[-100.0, 100.0, -100.0, 100.0, -200.0, 0.0]],
        depth_limits_m=[100.0, 200.0],
        surface_elevation_m=0.0,
    )
    np.testing.assert_array_equal(hard["support_mask"], [False, True, False])
    np.testing.assert_allclose(hard["upper"], [0.0, 0.8, 0.0])
    assert hard["fixed_cells"] == 2
    soft = spatial_property_constraints(
        xyz,
        lower=-1.0,
        upper=1.0,
        background_value=0.0,
        depth_limits_m=[100.0, 200.0],
        surface_elevation_m=[0.0, 0.0, 100.0],
        mode="soft",
        outside_weight=10.0,
    )
    np.testing.assert_allclose(soft["cell_weights"], [10.0, 1.0, 10.0])
    np.testing.assert_allclose(soft["upper"], 1.0)


def test_spatial_prior_rejects_empty_support_and_missing_surface():
    xyz = [[0.0, 0.0, -100.0]]
    with pytest.raises(ValueError, match="surface"):
        spatial_property_constraints(
            xyz, lower=0.0, upper=1.0, background_value=0.0, depth_limits_m=[1.0, 200.0]
        )
    with pytest.raises(ValueError, match="No cell"):
        spatial_property_constraints(
            xyz,
            lower=0.0,
            upper=1.0,
            background_value=0.0,
            support_prisms_m=[[10.0, 20.0, 10.0, 20.0, -200.0, 0.0]],
        )


def test_fragmented_predictions_fail_without_unbounded_component_matching():
    xyz = np.c_[np.arange(130.0) * 200.0, np.zeros(130), np.zeros(130)]
    truth = np.zeros(130)
    truth[0] = 1.0
    result = assess(xyz, np.ones(130), truth)
    assert result["predicted_component_count"] == 130
    assert not result["checks"]["location"]
    with pytest.raises(ValueError, match="64 truth"):
        assess(xyz, np.ones(130), np.ones(130))


@pytest.mark.parametrize("vector", [False, True])
def test_recovery_does_not_overflow_when_squaring_finite_properties(vector):
    xyz = np.array([[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]])
    truth = np.array([1e200, 1e200])
    if vector:
        truth = truth[:, None] * np.array([0.0, 0.0, 1.0])
    result = assess(xyz, truth, truth, vector=vector)
    assert result["recovery_passed"]
    assert result["model_relative_error"] == 0.0


def test_strict_campaign_gate_rejects_completed_but_failed_recovery(
    monkeypatch, tmp_path
):
    from scripts import benchmark_voxel_recovery as campaign

    monkeypatch.setattr(
        campaign,
        "run",
        lambda *_: dict(
            state="complete", scientific_status="recovery_not_validated", cases=[]
        ),
    )
    monkeypatch.setattr(
        "sys.argv", ["benchmark", "--output", str(tmp_path), "--require-recovery"]
    )
    with pytest.raises(SystemExit) as error:
        campaign.main()
    assert error.value.code == 2
