import numpy as np
import pandas as pd


def test_core_operation_snapshots_are_exact_and_observational():
    from terraworkbench_core.profile_preparation import preprocess_frame

    x = np.arange(180) * 0.1
    frame = pd.DataFrame(
        dict(X=x, Y=np.zeros(len(x)), B=50000 + 2 * x + np.sin(x * 2), Line=1)
    )
    config = dict(
        zero_traverse="mean", deslope=True, spike_tol=20, highpass_m=1, bw_low_m=1
    )
    kwargs = dict(
        x_column="X",
        y_column="Y",
        value_column="B",
        track_column="Line",
        crs="EPSG:32617",
    )
    base, report = preprocess_frame(frame, config, **kwargs)
    snapshots = []
    observed, observed_report = preprocess_frame(
        frame,
        config,
        stage_callback=lambda step, a: snapshots.append((step, a.copy())),
        **kwargs,
    )
    pd.testing.assert_frame_equal(base, observed)
    assert report == observed_report
    assert [s["operation"] for s, a in snapshots] == [
        s["operation"] for s in report["steps"]
    ]
    assert len(snapshots) == 5
    np.testing.assert_equal(snapshots[-1][1][:, 2], observed["B"].to_numpy())
    np.testing.assert_allclose(snapshots[0][1][:, 2], frame.B - frame.B.mean())
    assert abs(snapshots[-1][1][20:-20, 2]).max() < 10
    assert frame.B.min() > 49000


def test_compensation_step_callback_preserves_diurnal_outputs(tmp_path):
    from terraworkbench_core.magnetic_compensation import compensate_frame

    base = tmp_path / "base.csv"
    pd.DataFrame({"T": np.arange(10.0), "B": 50000 + np.arange(10.0)}).to_csv(
        base, index=False
    )
    frame = pd.DataFrame({"T": np.arange(10.0), "B": 50100 + np.arange(10.0)})
    config = {
        "diurnal": {
            "path": str(base),
            "time_column": "T",
            "value_column": "B",
            "time_unit": "s",
        },
        "time_unit": "s",
    }
    kwargs = dict(magnetic_column="B", time_column="T")
    expected, report = compensate_frame(frame, config, **kwargs)
    steps = []
    observed, actual = compensate_frame(
        frame, config, stage_callback=lambda step, f: steps.append((step, f)), **kwargs
    )
    pd.testing.assert_frame_equal(expected, observed)
    assert report == actual and len(steps) == 1
    pd.testing.assert_frame_equal(steps[0][1], observed)
