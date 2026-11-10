"""Convergence budgets, held-out prediction and conditional linear resolution.

No QGIS/private surveys. Resolution uses two prescribed prism coefficients,
not a regional voxel posterior. The large public cases run in isolated children.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def unit_prism_fields(depth, center, height):
    import harmonica as hm
    from scipy.constants import mu_0
    from scripts.validate_inversion_campaign import direction

    x, y = np.meshgrid(np.linspace(-300.0, 300.0, 9), np.linspace(-300.0, 300.0, 9))
    coordinates = (x.ravel(), y.ravel(), np.full(x.size, height))
    field = direction(60.0, 25.0)
    prism = [center - 40, center + 40, -40.0, 40.0, -depth - 40, -depth + 40]
    magnetic = hm.prism_magnetic(
        coordinates,
        prism,
        tuple((50000e-9 / mu_0 * field)[:, None]),
        field="b",
        parallel=False,
    )
    return {
        "gravity": -hm.prism_gravity(
            coordinates, prism, [1000.0], field="g_z", parallel=False
        ),
        "susceptibility": np.asarray(magnetic).T @ field,
    }


def resolution_case(depth, separation, height, noise_scale=1.0):
    from terraworkbench_core.inversion_diagnostics import linear_resolution

    matrices = {"gravity": [], "susceptibility": []}
    for center in (-separation / 2, separation / 2):
        values = unit_prism_fields(depth, center, height)
        for kind in matrices:
            matrices[kind].append(values[kind])
    result = {}
    for kind, columns in matrices.items():
        matrix = np.column_stack(columns)
        scale, sigma = (0.4, 0.002) if kind == "gravity" else (0.025, 0.3)
        std = np.full(len(matrix), sigma * noise_scale)
        diagnostic = linear_resolution(matrix, std, np.eye(2) / scale, beta=1.0)
        h = matrix / std[:, None] * scale
        _, singular, vt = np.linalg.svd(h, full_matrices=False)
        expected = (vt.T * (singular**2 / (singular**2 + 1))) @ vt
        np.testing.assert_allclose(
            diagnostic["resolution"], expected, rtol=1e-10, atol=1e-10
        )
        np.testing.assert_allclose(
            diagnostic["posterior_covariance"],
            (vt.T * (scale**2 / (singular**2 + 1))) @ vt,
            rtol=1e-10,
            atol=1e-10,
        )
        result[kind] = dict(
            effective_parameters=diagnostic["effective_parameters"],
            resolution_diagonal=np.diag(diagnostic["resolution"]).tolist(),
            posterior_std=diagnostic["posterior_std"].tolist(),
            singular_values_prior_scaled=singular.tolist(),
            column_cosine=float(
                np.dot(h[:, 0], h[:, 1])
                / (np.linalg.norm(h[:, 0]) * np.linalg.norm(h[:, 1]))
            ),
        )
    return result


def resolution_sweep(output):
    cases = {
        "shallow_separated": (150.0, 200.0, 50.0, 1.0),
        "shallow_adjacent": (150.0, 90.0, 50.0, 1.0),
        "deep_adjacent": (650.0, 90.0, 50.0, 1.0),
        "higher_observation": (150.0, 90.0, 250.0, 1.0),
        "larger_noise": (150.0, 90.0, 50.0, 4.0),
    }
    result = {
        key: {"geometry": values, "diagnostics": resolution_case(*values)}
        for key, values in cases.items()
    }
    for kind in ("gravity", "susceptibility"):
        base = result["shallow_adjacent"]["diagnostics"][kind]["effective_parameters"]
        assert (
            result["larger_noise"]["diagnostics"][kind]["effective_parameters"] < base
        )
        assert (
            result["deep_adjacent"]["diagnostics"][kind]["effective_parameters"] < base
        )
    (output / "resolution.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        "PASS: two-prism linear resolution, independent SVD and noise/depth comparisons",
        flush=True,
    )


def geometry_profiles(output):
    """Profile alternative geometries with one fitted amplitude; no confidence claim."""
    rng = np.random.default_rng(52)
    result = {}
    for depth in (150.0, 650.0):
        for parameter in ("depth", "separation"):
            true_value = depth if parameter == "depth" else 100.0
            grid = (
                np.arange(100.0, 801.0, 25.0)
                if parameter == "depth"
                else np.arange(80.0, 401.0, 20.0)
            )

            def fields(value):
                if parameter == "depth":
                    return unit_prism_fields(value, 0.0, 50.0)
                left, right = (
                    unit_prism_fields(depth, -value / 2, 50.0),
                    unit_prism_fields(depth, value / 2, 50.0),
                )
                return {key: left[key] + right[key] for key in left}

            truth, candidates = fields(true_value), [fields(v) for v in grid]
            for kind in truth:
                amplitude, sigma, upper = (
                    (0.4, 0.002, 1.5) if kind == "gravity" else (0.025, 0.3, 0.1)
                )
                data = truth[kind] * amplitude + rng.normal(
                    0.0, sigma, truth[kind].shape
                )
                columns = np.array([v[kind] for v in candidates])
                fitted = np.clip(
                    (columns @ data) / np.sum(columns**2, axis=1), 0.0, upper
                )
                chi = np.sum(((columns * fitted[:, None] - data) / sigma) ** 2, axis=1)
                accepted = grid[chi <= chi.min() + 1.0]
                best = int(np.argmin(chi))
                result[f"{kind}_{parameter}_{int(depth)}m"] = dict(
                    truth_value_m=true_value,
                    best_value_m=float(grid[best]),
                    candidate_grid_m=grid.tolist(),
                    fitted_amplitudes=fitted.tolist(),
                    chi_squared=chi.tolist(),
                    delta_chi_squared_one_set_m=accepted.tolist(),
                    touches_grid_edge=bool(grid[0] in accepted or grid[-1] in accepted),
                    definition="Conditional equal-prism geometry, profiled amplitude, delta chi squared <=1; not a confidence interval",
                )
    (output / "geometry_profiles.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        "PASS: conditional depth/separation profiles with fitted amplitudes", flush=True
    )


def synthetic_sweep(output):
    from scripts.validate_inversion_campaign import direction, volume_reference, forward
    from terraworkbench_core.inversion import _mesh_from_data, run_inversion_workflow

    x, y = np.meshgrid(np.arange(-300.0, 301.0, 100.0), np.arange(-300.0, 301.0, 100.0))
    xyz = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 100.0)))
    hx, hy = np.meshgrid(
        np.arange(-250.0, 251.0, 100.0), np.arange(-250.0, 251.0, 100.0)
    )
    held = np.column_stack((hx.ravel(), hy.ravel(), np.full(hx.size, 120.0)))
    topo = np.array(
        [
            [-500.0, -500.0, 0.0],
            [-500.0, 500.0, 0.0],
            [500.0, -500.0, 0.0],
            [500.0, 500.0, 0.0],
        ]
    )
    mesh, active = _mesh_from_data(xyz, 100.0, 100.0, 400.0, 1, topography=topo)
    centers = mesh.cell_centers[active]
    body = (
        (abs(centers[:, 0]) < 100)
        & (abs(centers[:, 1]) < 100)
        & (centers[:, 2] > -300)
        & (centers[:, 2] < -100)
    )
    truth = 0.025 * body
    clean = volume_reference(xyz, direction(60.0, 25.0))[1]
    held_truth = volume_reference(held, direction(60.0, 25.0))[1]
    observed = clean + np.random.default_rng(82).normal(0.0, 0.3, clean.shape)
    cases = {
        "baseline": {},
        "two_iterations": {"iterations": 2},
        "start_zero": {"starting_model": 0.0},
        "start_high": {"starting_model": 0.005},
        "beta_low": {"beta0_ratio": 0.1},
        "beta_high": {"beta0_ratio": 10.0},
        "sigma_half": {"sigma_scale": 0.5},
        "sigma_double": {"sigma_scale": 2.0},
        "sparse_irls": {
            "regularization_norms": [1.0, 1.0, 1.0, 1.0],
            "irls_iterations": 3,
        },
    }
    result = {}
    for name, overrides in cases.items():
        options = dict(
            cell_xy=100.0,
            cell_z=100.0,
            depth=400.0,
            mesh=mesh,
            active_cells=active,
            iterations=40,
            starting_model=1e-4,
            reference_model=np.zeros(int(active.sum())),
            field_inclination=60.0,
            field_declination=25.0,
            cg_maxiter=200,
            cg_rtol=1e-4,
        )
        overrides = dict(overrides)
        scale = overrides.pop("sigma_scale", 1.0)
        options.update(overrides)
        started = time.perf_counter()
        inverted = run_inversion_workflow(
            "susceptibility",
            xyz,
            observed,
            np.full(len(xyz), 0.3 * scale),
            output_directory=output / ("synthetic_" + name),
            **options,
        )
        held_prediction = forward(mesh, active, held, inverted.model, "susceptibility")
        weights = np.maximum(inverted.model, 0)
        result[name] = dict(
            diagnostics=inverted.diagnostics,
            seconds=time.perf_counter() - started,
            holdout_wrms=float(
                np.sqrt(np.mean(((held_prediction - held_truth) / 0.3) ** 2))
            ),
            relative_model_error=float(
                np.linalg.norm(inverted.model - truth) / np.linalg.norm(truth)
            ),
            recovered_centroid_depth_m=float(
                np.sum(-centers[:, 2] * weights) / np.sum(weights)
            ),
            true_centroid_depth_m=200.0,
        )
        (output / "synthetic.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        print(json.dumps({"case": name, **result[name]}), flush=True)


def public_sweep(output, cache):
    import psutil

    cases = {
        "baseline10": (10, {}),
        "outer30": (30, {}),
        "inner300_double": (
            30,
            {"cg_maxiter": 300, "cg_rtol": 1e-4, "sensitivity_dtype": "float64"},
        ),
        "uncoupled": (
            30,
            {
                "cg_maxiter": 300,
                "cg_rtol": 1e-4,
                "sensitivity_dtype": "float64",
                "coupling_weight": 0.0,
            },
        ),
        "gauss_newton": (
            80,
            {
                "cg_maxiter": 600,
                "cg_rtol": 1e-5,
                "sensitivity_dtype": "float64",
                "cross_gradient_hessian": "gauss_newton",
            },
        ),
    }
    results = {}
    for name, (iterations, options) in cases.items():
        options.update(reference_density=1e-6, reference_susceptibility=1e-6)
        recipe = output / (name + ".json")
        recipe.write_text(json.dumps(options, indent=2) + "\n", encoding="utf-8")
        with (output / (name + ".log")).open("w", encoding="utf-8") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "scripts/benchmark_public_inversion.py"),
                    "--case",
                    "joint",
                    "--cache",
                    str(cache),
                    "--output",
                    str(output / name),
                    "--iterations",
                    str(iterations),
                    "--joint-options",
                    str(recipe),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            proc, peak, start = psutil.Process(child.pid), 0, time.perf_counter()
            while child.poll() is None:
                try:
                    peak = max(
                        peak,
                        sum(
                            p.memory_info().rss
                            for p in [proc, *proc.children(recursive=True)]
                            if p.is_running()
                        ),
                    )
                except psutil.NoSuchProcess:
                    pass
                if time.perf_counter() - start > 1800:
                    child.terminate()
                    child.wait()
                    raise RuntimeError(
                        "Public convergence case exceeded 30 minutes: " + name
                    )
                time.sleep(0.2)
        if child.returncode:
            raise RuntimeError("Public convergence case failed: " + name)
        report = json.loads((output / name / "report.json").read_text(encoding="utf-8"))
        if name == "gauss_newton" and (
            not report["diagnostics"]["outer_convergence_met"]
            or report["diagnostics"]["iteration_limit_reached"]
        ):
            raise RuntimeError(
                "Gauss-Newton benchmark did not converge before its budget."
            )
        report["sampled_peak_process_tree_rss_bytes"] = peak
        results[name] = report
        (output / "public.json").write_text(
            json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "case": name,
                    "diagnostics": report["diagnostics"],
                    "seconds": report["seconds"],
                }
            ),
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--cache",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--section", choices=("all", "resolution", "synthetic", "public"), default="all"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "versions": {
            name: version(name)
            for name in ("numpy", "scipy", "simpeg", "discretize", "harmonica")
        },
        "core_source_sha256": hashlib.sha256(
            (ROOT / "terraworkbench_core/inversion.py").read_bytes()
        ).hexdigest(),
        "diagnostics_source_sha256": hashlib.sha256(
            (ROOT / "terraworkbench_core/inversion_diagnostics.py").read_bytes()
        ).hexdigest(),
    }
    (args.output / "sources.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    if args.section in ("all", "resolution"):
        resolution_sweep(args.output)
        geometry_profiles(args.output)
    if args.section in ("all", "synthetic"):
        synthetic_sweep(args.output)
    if args.section in ("all", "public"):
        public_sweep(args.output, args.cache)


if __name__ == "__main__":
    main()
