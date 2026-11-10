"""Bounded three-geometry MVI acceptance campaign with independent fields.

Reuses authored recovery fixtures; downloaded public observations are a separate
reference and are never represented as known geological truth for these cases.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402


def stationarity(problem):
    """Final frozen objective, measured relative to the spherical start."""
    from scripts.benchmark_mvi_outer import prior_digest

    opt = problem.opt
    final = problem.model.copy()
    start = opt.x0.copy()
    sim = problem.dmisfit.objfcts[0].simulation
    before = prior_digest(problem.reg)
    diagonal = 2 * sim.getJtJdiag(start, W=problem.dmisfit.objfcts[0].W)
    diagonal += problem.beta * problem.reg.deriv2(start).diagonal()
    diagonal = np.maximum(
        diagonal, np.finfo(float).eps * max(float(diagonal.max()), 1.0)
    )
    measures = []
    for value in [start, final]:
        _, gradient = problem.evalFunction(value, return_g=True, return_H=False)
        step = opt.projection(value - gradient / diagonal) - value
        measures.append(float(np.linalg.norm(np.sqrt(diagonal) * step)))
    assert prior_digest(problem.reg) == before, (
        "Stationarity evaluation changed weights"
    )
    threshold = max(measures[0] * 1e-3, 1e-12)
    return dict(
        initial_projected_gradient=measures[0],
        final_projected_gradient=measures[1],
        relative_projected_gradient=measures[1] / max(measures[0], 1e-300),
        threshold=threshold,
        passed=measures[1] <= threshold,
        definition="Final objective with frozen weights; fixed Jacobi metric at spherical initial model; local coordinate test only",
    )


def depth_errors(centers, volumes, predicted, truth, threshold, shape):
    """Independent cell-grid component centroids; ENU z, six-face adjacency."""
    from scipy.ndimage import label
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial.distance import cdist

    def centroids(values):
        groups, count = label(
            (np.linalg.norm(values, axis=1) >= threshold).reshape(shape, order="F")
        )
        groups = groups.ravel(order="F")
        return np.array(
            [
                np.average(centers[groups == i], axis=0, weights=volumes[groups == i])
                for i in range(1, count + 1)
            ]
        ).reshape((-1, 3))

    actual, recovered = centroids(truth), centroids(predicted)
    if len(actual) == 0 or len(actual) != len(recovered):
        return dict(maximum_depth_error_m=None, component_counts_match=False)
    a, b = linear_sum_assignment(cdist(actual, recovered))
    return dict(
        maximum_depth_error_m=float(np.max(abs(actual[a, 2] - recovered[b, 2]))),
        component_counts_match=True,
        matched_true_centers=actual[a].tolist(),
        matched_recovered_centers=recovered[b].tolist(),
    )


def run(output):
    from discretize import TensorMesh
    from scipy.constants import mu_0
    from scripts.benchmark_voxel_recovery import (
        FIXTURES,
        CRITERIA,
        direction,
        integrated_fields,
    )
    from scripts.validate_inversion_campaign import forward
    from terraworkbench_core.inversion import run_potential_field_inversion
    from terraworkbench_core.recovery_metrics import model_recovery_metrics
    from terraworkbench_core import spherical_mvi

    output.mkdir(parents=True, exist_ok=False)
    protocol = dict(
        schema_version=1,
        fixtures=["shallow_cube", "deep_cube", "two_bodies"],
        mesh=dict(shape=[8, 8, 6], cell_width_m=100, origin=[-400, -400, -600]),
        field=dict(amplitude_nt=50000, inclination_deg=60, declination_deg=25),
        magnetization_directions_deg=[[25, -35], [-35, 135]],
        amplitude_si=0.025,
        noise_nt=0.3,
        seeds=[6417, 6517, 6617],
        solver=dict(
            spherical_iterations=80,
            cartesian_iterations=20,
            irls_iterations=20,
            cg_maxiter=800,
            cg_rtol=1e-4,
            amplitude_max=0.1,
        ),
        legacy_recovery_criteria=CRITERIA,
        depth_tolerance_m=100,
        data_fit=dict(training_wrms_max=2, withheld_clean_wrms_max=3),
        body_checks=["location", "volume", "contrast", "support", "direction", "depth"],
        policy="Predeclared before fitting; all outcomes retained; no oracle or ROI; voxel-L2 gate retained separately, not substituted or relaxed",
        readiness_policy="Body checks, prediction, all inner tolerances and demonstrated outer stationarity are separate necessary conditions",
        stationarity=dict(
            relative_projected_gradient_max=1e-3,
            absolute_floor=1e-12,
            objective="final frozen objective",
            metric="fixed initial Jacobi",
        ),
        reference_type="Authored prisms with independent Gauss volume quadrature; not downloaded field data",
    )
    blob = (json.dumps(protocol, sort_keys=True, indent=2) + "\n").encode()
    (output / "protocol.json").write_bytes(blob)
    report = dict(
        state="running",
        protocol=protocol,
        protocol_sha256=hashlib.sha256(blob).hexdigest(),
        utc=datetime.now(timezone.utc).isoformat(),
        cases=[],
        commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        repository_dirty=repository_provenance(ROOT)["dirty"],
        versions={
            p: version(p)
            for p in ["numpy", "scipy", "simpeg", "discretize", "geoana", "choclo"]
        },
        source_sha256={
            str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in [
                *list((ROOT / "terraworkbench_core").glob("*.py")),
                Path(__file__).resolve(),
                ROOT / "scripts/benchmark_voxel_recovery.py",
                ROOT / "scripts/validate_inversion_campaign.py",
            ]
        },
    )

    def save():
        temporary = output / "report.json.part"
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        temporary.replace(output / "report.json")

    save()
    mesh = TensorMesh(
        [[(100.0, 8)], [(100.0, 8)], [(100.0, 6)]], origin=[-400, -400, -600]
    )
    active = np.ones(mesh.nC, dtype=bool)
    x, y = np.meshgrid(np.arange(-400.0, 401.0, 100.0), np.arange(-400.0, 401.0, 100.0))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    x, y = np.meshgrid(np.arange(-350.0, 351.0, 100.0), np.arange(-350.0, 351.0, 100.0))
    held = np.c_[x.ravel(), y.ravel(), np.full(x.size, 120.0)]
    field = direction(60, 25)
    for index, name in enumerate(protocol["fixtures"]):
        folder = output / name
        folder.mkdir()
        prisms = np.asarray(FIXTURES[name], dtype=float)
        dirs = np.array(
            [
                direction(*(protocol["magnetization_directions_deg"][i % 2]))
                for i in range(len(prisms))
            ]
        )
        mags = 0.025 * 50000e-9 / mu_0 * dirs
        truth = np.zeros((mesh.nC, 3))
        for prism, d in zip(prisms, dirs):
            mask = np.all(
                (mesh.cell_centers > prism[::2]) & (mesh.cell_centers < prism[1::2]),
                axis=1,
            )
            truth[mask] = 0.025 * d
        _, b = integrated_fields(xyz, prisms, np.zeros(len(prisms)), mags, order=12)
        _, b2 = integrated_fields(xyz, prisms, np.zeros(len(prisms)), mags, order=16)
        clean = b @ field
        np.testing.assert_allclose(clean, b2 @ field, atol=1e-7, rtol=1e-7)
        _, hb = integrated_fields(held, prisms, np.zeros(len(prisms)), mags, order=16)
        held_clean = hb @ field
        predicted_truth = forward(mesh, active, xyz, truth.ravel(order="F"), "mvi")
        discrepancy = float(np.max(abs(predicted_truth - clean)))
        assert discrepancy <= 1e-5 * protocol["noise_nt"], (
            "Independent forward consistency failed"
        )
        observed = clean + protocol["noise_nt"] * np.random.default_rng(
            protocol["seeds"][index]
        ).normal(size=len(clean))
        np.savez_compressed(
            folder / "input.npz",
            xyz=xyz,
            observed=observed,
            clean=clean,
            held_xyz=held,
            held_clean=held_clean,
            truth=truth,
            centers=mesh.cell_centers,
            volumes=mesh.cell_volumes,
        )
        # No truth/support/centroid information is supplied to the production call.
        captured = []
        factory = spherical_mvi.safeguarded_irls_type

        def capture():
            class Capture(factory()):
                def initialize(self):
                    super().initialize()
                    captured.append(self)

            return Capture

        with patch.object(spherical_mvi, "safeguarded_irls_type", capture):
            result = run_potential_field_inversion(
                "mvi",
                xyz,
                observed,
                np.full(len(xyz), protocol["noise_nt"]),
                mesh=mesh,
                active_cells=active,
                cell_xy=100.0,
                cell_z=100.0,
                depth=600.0,
                iterations=80,
                irls_iterations=20,
                cg_maxiter=800,
                cg_rtol=1e-4,
                mvi_parameterization="spherical",
                mvi_irls_update="adaptive",
                mvi_cartesian_iterations=20,
                mvi_amplitude_max=0.1,
                regularization_norms=[0.0, 1.0, 1.0, 1.0],
                mvi_angle_norms=[1.0, 1.0, 1.0],
                field_amplitude=50000.0,
                field_inclination=60.0,
                field_declination=25.0,
                sensitivity_dtype="float64",
                sensitivity_mode="ram",
            )
        assert len(captured) == 1
        optimality = stationarity(captured[0].invProb)
        recovered = result.model.reshape((mesh.nC, 3), order="F")
        hold_pred = forward(mesh, active, held, result.model, "mvi")
        recovery = model_recovery_metrics(
            mesh.cell_centers,
            mesh.cell_volumes,
            recovered,
            truth,
            criteria=CRITERIA,
            connectivity_radius_m=101.0,
            vector=True,
        )
        depths = depth_errors(
            mesh.cell_centers,
            mesh.cell_volumes,
            recovered,
            truth,
            recovery["support_threshold"],
            (8, 8, 6),
        )
        body_checks = {
            k: recovery["checks"][k]
            for k in ["location", "volume", "contrast", "support", "direction"]
        }
        body_checks["depth"] = (
            depths["maximum_depth_error_m"] is not None
            and depths["maximum_depth_error_m"] <= 100
        )
        train = float(
            np.sqrt(
                np.mean(((result.predicted - observed) / protocol["noise_nt"]) ** 2)
            )
        )
        withheld = float(
            np.sqrt(np.mean(((hold_pred - held_clean) / protocol["noise_nt"]) ** 2))
        )
        audited = [
            r for r in result.history if r.get("cg_true_tolerance_met") is not None
        ]
        spherical = [r for r in audited if r.get("stage") == "spherical"]
        precision = bool(
            audited
            and spherical
            and all(r["cg_true_tolerance_met"] for r in audited)
            and all(r.get("cg_scaled_tolerance_met") for r in spherical)
        )
        stationary = optimality["passed"]
        fit = train <= 2 and withheld <= 3
        item = dict(
            fixture=name,
            execution_status="complete",
            weighted_rms=train,
            withheld_clean_wrms=withheld,
            independent_forward_max_error_nt=discrepancy,
            recovery=recovery,
            depth=depths,
            body_checks=body_checks,
            body_characterization_passed=all(body_checks.values()),
            prediction_passed=fit,
            all_inner_tolerances_met=precision,
            outer_stationarity_demonstrated=stationary,
            stationarity=optimality,
            readiness_passed=all(body_checks.values())
            and fit
            and precision
            and stationary,
            diagnostics=result.diagnostics,
            history=result.history,
            input_sha256=hashlib.sha256(
                (folder / "input.npz").read_bytes()
            ).hexdigest(),
        )
        np.savez_compressed(
            folder / "recovered.npz",
            model=recovered,
            predicted=result.predicted,
            held_predicted=hold_pred,
        )
        report["cases"].append(item)
        save()
        print(
            json.dumps(
                {
                    k: item[k]
                    for k in [
                        "fixture",
                        "weighted_rms",
                        "withheld_clean_wrms",
                        "body_checks",
                        "all_inner_tolerances_met",
                        "readiness_passed",
                    ]
                }
            ),
            flush=True,
        )
    report["state"] = "complete"
    report["readiness_passed"] = all(r["readiness_passed"] for r in report["cases"])
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
