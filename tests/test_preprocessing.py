import numpy as np

from preprocessing import (
    BASE_DRIFT,
    BASE_SPIKE,
    QC_CLEARANCE,
    QC_SPACING,
    QC_SPEED,
    QC_TIME_GAP,
    QC_TURN,
    QC_VALUE_RATE,
    flight_line_metrics,
    flight_quality_flags,
    base_station_quality,
    estimate_time_lag,
    line_spacing_quality,
    magnetic_elements,
    unwrap_time_seconds,
)


def test_magnetic_elements_use_positive_down_inclination():
    total, horizontal, declination, inclination = magnetic_elements(
        [0.0, 100.0], [100.0, 0.0], [-100.0, 0.0]
    )
    assert np.allclose(total, [np.sqrt(20_000.0), 100.0])
    assert np.allclose(horizontal, 100.0)
    assert np.allclose(declination, [0.0, 90.0])
    assert np.allclose(inclination, [45.0, 0.0])


def test_flight_metrics_and_flags_report_each_enabled_failure():
    metrics = flight_line_metrics(
        [0.0, 10.0, 40.0, 40.0],
        [0.0, 0.0, 0.0, 10.0],
        [0.0, 1.0, 4.0, 5.0],
        values=[0.0, 2.0, 20.0, 21.0],
        clearance=[100.0, 100.0, 300.0, 100.0],
    )
    flags = flight_quality_flags(
        metrics,
        maximum_time_gap=2.0,
        maximum_spacing=20.0,
        minimum_speed=11.0,
        maximum_speed=20.0,
        maximum_turn=45.0,
        minimum_clearance=50.0,
        maximum_clearance=200.0,
        maximum_value_rate=5.0,
    )
    assert flags[1] & QC_SPEED
    assert flags[2] & QC_TIME_GAP
    assert flags[2] & QC_SPACING
    assert flags[2] & QC_CLEARANCE
    assert flags[2] & QC_VALUE_RATE
    assert flags[3] & QC_SPEED
    assert flags[3] & QC_TURN


def test_time_rollover_and_automatic_lag_are_explicit():
    assert np.allclose(unwrap_time_seconds([86399.0, 0.0, 1.0]), [86399.0, 86400.0, 86401.0])
    time = np.arange(0.0, 30.0, 0.25)
    reference = np.sin(time * 0.73) + 0.2 * np.cos(time * 1.91)
    response = np.sin((time - 1.5) * 0.73) + 0.2 * np.cos((time - 1.5) * 1.91)
    result = estimate_time_lag(time, response, time, reference, maximum_lag=3.0, lag_step=0.25)
    assert np.isclose(result["lag"], 1.5)
    assert result["correlation"] > 0.999


def test_base_station_qc_flags_spike_and_record_drift():
    time = np.arange(20.0)
    values = 100.0 + 0.2 * time
    values[10] += 20.0
    result = base_station_quality(
        time,
        values,
        spike_window=3,
        spike_sigma=4.0,
        maximum_drift_rate=0.1,
    )
    assert result["flags"][10] & BASE_SPIKE
    assert np.all(result["flags"] & BASE_DRIFT)


def test_line_spacing_qc_finds_large_gap():
    result = line_spacing_quality(
        [[0.0, 0.0], [100.0, 0.0], [300.0, 0.0]],
        [0.0, 0.0, 0.0],
        expected_spacing=100.0,
        tolerance=0.25,
    )
    assert np.isclose(result["survey_azimuth"], 0.0)
    assert np.allclose(result["spacing"][1:], [100.0, 200.0])
    assert not result["flag"][1]
    assert result["flag"][2]
