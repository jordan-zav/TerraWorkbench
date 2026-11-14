"""Numerical window, cancellation and optional integration contracts."""

from terraworkbench_core.live_preview import (
    LatestRequest,
    preview_window,
    product_palette,
)
import pytest
import numpy as np
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


def test_visible_crop_includes_real_margin_and_preserves_georeferencing():
    window = preview_window(
        (0, 10, 0, 10000, 0, -10), (1000, 1000), (4000, 4000, 6000, 6000), (100, 100)
    )
    assert (window.xoff, window.yoff, window.width, window.height) == (
        300,
        300,
        400,
        400,
    )
    assert (window.columns, window.rows) == (200, 200)
    assert window.transform == (3000, 20, 0, 7000, 0, -20)


def test_clipping_never_reads_outside_source_or_upsamples():
    window = preview_window(
        (0, 10, 0, 100, 0, -10), (10, 10), (-100, -100, 200, 200), (1000, 1000)
    )
    assert (window.xoff, window.yoff, window.width, window.height) == (0, 0, 10, 10)
    assert (window.columns, window.rows) == (10, 10)
    with pytest.raises(ValueError):
        preview_window(
            (0, 10, 0, 100, 0, -10), (10, 10), (200, 200, 300, 300), (100, 100)
        )


def test_large_source_work_is_bounded_by_screen_size():
    for size in (512, 2048, 16384):
        window = preview_window(
            (0, 1, 0, size, 0, -1),
            (size, size),
            (size / 4, size / 4, size * 0.75, size * 0.75),
            (512, 512),
            max_side=512,
        )
        assert max(window.columns, window.rows) <= 1024


def test_latest_request_cancels_before_next_debounce_and_rejects_stale_result():
    latest = LatestRequest()
    first, cancelled = latest.replace()
    second, current = latest.replace()
    assert cancelled.is_set() and not current.is_set()
    assert not latest.accepts(first) and latest.accepts(second)


def test_windowed_continuation_matches_full_grid_in_view_centre():
    from terraworkbench_core.spectral import (
        prepare_fft_grid,
        finish_fft_grid,
        frequency_grid,
        apply_transfer,
    )

    yy, xx = np.mgrid[:1024, :1024]
    data = np.exp(-((xx - 512) ** 2 + (yy - 512) ** 2) / (2 * 35**2))

    def continuation(values):
        prepared, state = prepare_fft_grid(values, detrend_order=-1)
        _, _, radial = frequency_grid(prepared.shape, 1, 1)
        return finish_fft_grid(
            apply_transfer(prepared, np.exp(-radial * 10)), state, False
        )

    full = continuation(data)
    window = preview_window(
        (0, 1, 0, 1024, 0, -1), data.shape, (384, 384, 640, 640), (256, 256)
    )
    assert window.width == 512 and window.columns == 512
    preview = continuation(
        data[
            window.yoff : window.yoff + window.height,
            window.xoff : window.xoff + window.width,
        ]
    )
    np.testing.assert_allclose(
        preview[192:320, 192:320], full[448:576, 448:576], atol=5e-4, rtol=0
    )


@pytest.mark.parametrize(
    "name,expected",
    [
        ("fft_upward_continuation", "classic_geophysics"),
        ("reduction_to_pole", "classic_geophysics"),
        ("fft_derivative_vertical", "blue_white_red"),
        ("tilt_angle", "blue_white_red"),
    ],
)
def test_product_palette(name, expected):
    assert product_palette(name) == expected


def test_georamp_present_and_absent_use_public_plugin_interface(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    parent = ModuleType("preview_bridge_test")
    parent.__path__ = [str(root)]
    monkeypatch.setitem(sys.modules, parent.__name__, parent)
    spec = importlib.util.spec_from_file_location(
        "preview_bridge_test.qgis_plugin.georamp", root / "qgis_plugin/georamp.py"
    )
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    calls = []
    iface = SimpleNamespace(setActiveLayer=lambda layer: calls.append(layer))
    monkeypatch.setattr(
        bridge, "show_georamp_manager", lambda iface: calls.append("manager:GeoRamp")
    )
    assert not bridge.open_georamp(iface, None, plugins={})
    assert calls == ["manager:GeoRamp"]

    class Combo:
        def findData(self, value):
            calls.append(value)
            return 2

        def setCurrentIndex(self, value):
            calls.append(value)

    layer = SimpleNamespace(id=lambda: "preview-layer")
    plugin = SimpleNamespace(
        run=lambda: calls.append("run"),
        dialog=SimpleNamespace(layer_combo=Combo(), palette_combo=Combo()),
    )
    assert bridge.open_georamp(
        iface, layer, "reduction_to_pole", plugins={"georamp": plugin}
    )
    assert calls[-4:] == ["preview-layer", 2, "classic_geophysics", 2]
