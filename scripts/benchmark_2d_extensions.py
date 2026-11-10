"""Public-field and independent-reference validation of the 2-D extensions.

Reuses the pinned cache from benchmark_public_processing. No private data,
plots, assumed airborne calibration or downloaded executable code.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import platform
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402
from scripts.benchmark_public_processing import fetch, member_bytes, compare, MANIFEST  # noqa: E402


def run(cache, output, offline=False):
    import pandas as pd
    import xarray as xr
    from scipy.linalg import lstsq
    from pykrige.ok import OrdinaryKriging
    from terraworkbench_core.geostatistics import ordinary_kriging, empirical_variogram
    from terraworkbench_core.radon_corrections import full_spectrum_radon
    from terraworkbench_core.gravity_profiles import (
        polygon_gravity_2d,
        fit_polygon_densities,
    )

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    sources = json.loads(MANIFEST.read_text())
    paths = {
        key: fetch(cache, sources[key], offline=offline)
        for key in ("lightning", "spectra")
    }
    report = dict(
        utc=datetime.now(timezone.utc).isoformat(),
        status="running",
        datasets={k: sources[k] for k in paths},
        versions={
            name: version(name)
            for name in ("numpy", "scipy", "xarray", "pandas", "pykrige")
        },
        cases={},
        source_sha256={
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "terraworkbench_core").glob("*.py")
        },
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        git_head=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        git_dirty=repository_provenance(ROOT)["dirty"],
        platform=platform.platform(),
        limits=[
            "Kriging variograms are declared stress-case models, not validated geological covariance.",
            "Full-spectrum fitting uses published simulated templates and measured spectra, not an airborne calibration transfer.",
            "Polygon gravity is an infinite-strike 2-D model; no finite-strike or geological uniqueness claim.",
        ],
    )

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save()
    try:
        grid = xr.load_dataarray(paths["lightning"]).isel(
            northing=slice(40, 137), easting=slice(40, 141)
        )
        x = grid.easting.values - grid.easting.values[0]
        y = grid.northing.values - grid.northing.values[0]
        xx, yy = np.meshgrid(x, y)
        train = np.zeros(grid.shape, bool)
        train[::5, ::5] = True
        withheld = (xx > 1700) & (xx < 2700) & (yy > 1700) & (yy < 2700)
        train[withheld] = False
        xy, z = np.c_[xx[train], yy[train]], grid.values[train]
        query = np.c_[xx[withheld], yy[withheld]]
        partial_sill = float(grid.values.var())
        range_m = 1000.0
        nugget = 0.0
        comparisons = {}
        predictions = {}
        for model in ("spherical", "exponential", "gaussian"):
            actual = ordinary_kriging(
                xy, z, query, range_m, partial_sill, nugget, model=model, neighbors=32
            )
            # PyKrige Gaussian uses scale=4*range/7. Match the physical kernel,
            # not identically spelled parameters with different conventions.
            reference_range = (
                range_m if model != "gaussian" else 7 * range_m / (4 * np.sqrt(3))
            )
            ref = OrdinaryKriging(
                xy[:, 0],
                xy[:, 1],
                z,
                variogram_model=model,
                variogram_parameters={
                    "psill": partial_sill,
                    "range": reference_range,
                    "nugget": nugget,
                },
                exact_values=True,
                enable_plotting=False,
                verbose=False,
            )
            expected, var = ref.execute(
                "points", query[:, 0], query[:, 1], backend="loop", n_closest_points=32
            )
            metrics = dict(
                prediction=compare(
                    actual["predicted"], np.asarray(expected), atol=1e-7, rtol=1e-10
                ),
                variance=compare(
                    actual["variance"], np.asarray(var), atol=1e-7, rtol=1e-10
                ),
                withheld_rms_nt=float(
                    np.sqrt(np.mean((actual["predicted"] - grid.values[withheld]) ** 2))
                ),
                core_range_m=range_m,
                reference_range_m=float(reference_range),
                partial_sill_nt2=partial_sill,
                recipe=actual["recipe"],
            )
            comparisons[model] = metrics
            predictions[model] = actual["predicted"]
        empirical = empirical_variogram(xy, z, np.linspace(0, 5000, 21))
        report["cases"]["public_kriging"] = dict(
            status="passed"
            if all(
                m["prediction"]["passed"] and m["variance"]["passed"]
                for m in comparisons.values()
            )
            else "failed",
            training_points=len(z),
            withheld_cells=len(query),
            comparisons=comparisons,
            empirical_variogram=dict(
                lag_edges_m=empirical["lag_edges_m"].tolist(),
                semivariance=[
                    float(v) if np.isfinite(v) else None
                    for v in empirical["semivariance"]
                ],
                pair_count=empirical["pair_count"].tolist(),
            ),
            scope="Independent PyKrige moving-neighborhood reference on the pinned public grid; withheld accuracy diagnostic is not raw-survey validation.",
        )
        np.savez_compressed(
            output / "kriging.npz", expected=grid.values[withheld], **predictions
        )
        save()
        fits = {}
        for case in ("HF_Cs", "HF_Ba"):
            prefix = "data_v1_1_0/" + case
            raw = member_bytes(
                paths["spectra"], prefix + "/Data/gross_all.csv"
            ).decode()
            live = float(raw.splitlines()[0].split("=")[1])
            frame = pd.read_csv(io.StringIO(raw), comment="#")
            energy = frame.iloc[:, 0].to_numpy()
            counts = frame.iloc[:, 1].to_numpy(float)
            widths = np.gradient(energy)
            names = ["K", "U", "Th", "Rn", "Cs" if case == "HF_Cs" else "Ba"]
            templates = []
            headers = {}
            valid = (energy >= 100) & (energy <= 2800)
            for name in names:
                template = pd.read_csv(
                    io.BytesIO(
                        member_bytes(
                            paths["spectra"], prefix + "/Templates/" + name + ".csv"
                        )
                    )
                )
                tx, ty = template.iloc[:, 0].to_numpy(), template.iloc[:, 1].to_numpy()
                valid &= (energy >= tx.min()) & (energy <= tx.max())
                templates.append(np.interp(energy, tx, ty) * widths * live)
                headers[name] = str(template.columns[1])
            response = np.column_stack(templates)[valid]
            measured = counts[valid]
            std = np.sqrt(np.maximum(measured, 1.0))
            actual = full_spectrum_radon(
                measured[None, :], response, std, names, radon_component=3
            )
            coefficients = lstsq(response / std[:, None], measured / std)[0]
            corrected = measured - response[:, 3] * coefficients[3]
            fits[case] = dict(
                coefficients=actual["component_rates"][0].tolist(),
                template_density_units=headers,
                radon_coefficient=float(coefficients[3]),
                negative_components=actual["negative_components"][0].tolist(),
                corrected_reference=compare(
                    actual["corrected_spectra"][0], corrected, atol=1e-6, rtol=1e-9
                ),
                coefficient_reference=compare(
                    actual["component_rates"][0], coefficients, atol=1e-7, rtol=1e-9
                ),
                minimum_propagated_variance=float(actual["corrected_variance"].min()),
                reduced_chi_squared=float(
                    actual["chi_squared"][0] / actual["degrees_of_freedom"]
                ),
            )
        report["cases"]["public_spectral_radon"] = dict(
            status="passed"
            if all(
                f["corrected_reference"]["passed"]
                and f["coefficient_reference"]["passed"]
                and f["minimum_propagated_variance"] >= 0
                for f in fits.values()
            )
            else "failed",
            fits=fits,
            scope="Signed GLS, declared sqrt-count noise floor; source templates are geometry-specific. Negative coefficients/model misfit remain reported, not clipped or promoted to atmospheric concentration.",
        )
        save()
        angle = np.linspace(0, 2 * np.pi, 720, endpoint=False)
        polygon = np.c_[50 * np.cos(angle), -200 + 50 * np.sin(angle)]
        x = np.linspace(-500, 500, 101)
        obs = np.c_[x, np.zeros_like(x)]
        actual = polygon_gravity_2d(obs, [polygon], [500.0])["gravity_mgal"]
        from scipy.constants import G

        expected = 2 * np.pi * G * 500 * 50**2 * 200 / (x * x + 200**2) * 1e5
        physical = compare(actual, expected, atol=1e-8, rtol=3e-5)
        fit = fit_polygon_densities(
            obs, [polygon], actual + 0.3, np.full(len(x), 0.01), fit_offset=True
        )
        report["cases"]["analytic_polygon"] = dict(
            status="passed"
            if physical["passed"]
            and abs(fit["density_kg_m3"][0] - 500) < 1e-7
            and abs(fit["offset_mgal"] - 0.3) < 1e-9
            else "failed",
            cylinder_reference=physical,
            estimated_density_kg_m3=float(fit["density_kg_m3"][0]),
            estimated_offset_mgal=fit["offset_mgal"],
            scope="Analytic infinite horizontal cylinder approximated by 720 vertices, plus synthetic density/offset recovery. No measured profile geometry was invented.",
        )
        report["status"] = (
            "passed"
            if all(v["status"] == "passed" for v in report["cases"].values())
            else "failed"
        )
    except Exception as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        save()
    print(
        json.dumps(
            {
                "status": report["status"],
                "cases": {k: v["status"] for k, v in report["cases"].items()},
            }
        ),
        flush=True,
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    report = run(args.cache, args.output, args.offline)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
