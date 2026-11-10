"""Known periodic two-wavelength signal and upward continuation."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from terraworkbench_core.spectral import apply_transfer, frequency_grid


def synthetic_case():
    spacing, height = 10.0, 50.0
    x = np.arange(256) * spacing
    values = np.tile(
        np.sin(2 * np.pi * x / 640) + 0.25 * np.sin(2 * np.pi * x / 160), (32, 1)
    )
    _, _, radial = frequency_grid(values.shape, spacing, spacing)
    actual = apply_transfer(values, np.exp(-radial * height))
    expected = np.tile(
        np.exp(-2 * np.pi * height / 640) * np.sin(2 * np.pi * x / 640)
        + 0.25 * np.exp(-2 * np.pi * height / 160) * np.sin(2 * np.pi * x / 160),
        (32, 1),
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    return (
        x,
        values,
        actual,
        expected,
        {
            "kind": "synthetic periodic operator check",
            "spacing_m": spacing,
            "height_m": height,
            "wavelengths_m": [640.0, 160.0],
            "max_error": float(np.max(abs(actual - expected))),
            "field_data": False,
        },
    )


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    x, values, actual, expected, metrics = synthetic_case()
    np.savez_compressed(
        output / "arrays.npz", x=x, original=values, continued=actual, expected=expected
    )
    (output / "summary.json").write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
