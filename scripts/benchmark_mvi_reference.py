"""MVI recovery against independent volume integration and native SimPEG.

The published setup adapts the SimPEG 0.25 VectorAmplitude example (MIT).
The quick setup is authored here. Neither benchmark is a field validation.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np
from scipy.constants import mu_0

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402

SOURCE = "https://github.com/simpeg/simpeg/blob/v0.25.0/examples/03-magnetics/plot_inv_mag_MVI_VectorAmplitude.py"


def mesh_edges(mesh, active):
    """Two-cell total-face stencils retain coarse/fine TreeMesh adjacency."""
    pairs = []
    for axis in "xyz":
        stencil = getattr(mesh, "stencil_cell_gradient_" + axis).tocsr()
        count = np.diff(stencil.indptr)
        if np.any(count > 2):
            raise ValueError(
                "Unsupported multi-cell face stencil; do not guess adjacency"
            )
        pair = stencil[count == 2].indices.reshape((-1, 2))
        pairs.append(pair[active[pair].all(axis=1)])
    mapping = np.cumsum(active) - 1
    return np.unique(np.sort(mapping[np.vstack(pairs)], axis=1), axis=0)


def fixture(scale):
    from scripts.benchmark_voxel_recovery import integrated_fields, direction
    from discretize import TensorMesh
    from discretize.utils import mesh_builder_xyz, refine_tree_xyz, active_from_xyz

    if scale == "published":
        axis = np.linspace(-200, 200, 50)
        tx, ty = np.meshgrid(axis, axis)
        topo = np.c_[
            tx.ravel(), ty.ravel(), 50 * np.exp(-(tx**2 + ty**2).ravel() / 20000)
        ]
        x, y = np.meshgrid(np.linspace(-100, 100, 20), np.linspace(-100, 100, 20))
        xyz = np.c_[
            x.ravel(), y.ravel(), (50 * np.exp(-(x**2 + y**2) / 20000) + 5).ravel()
        ]
        mesh = mesh_builder_xyz(
            xyz,
            [5, 5, 5],
            padding_distance=np.full((3, 2), 100),
            depth_core=100,
            mesh_type="tree",
        )
        mesh = refine_tree_xyz(
            mesh, topo, method="surface", octree_levels=[2, 6], finalize=True
        )
        active = active_from_xyz(mesh, topo)
        low, high = np.array([-30, -20, -10]), np.array([30, 20, 25])
        sigma = 10.0
        inc, dec = 45.0, 90.0
    else:
        mesh = TensorMesh(
            [[(100.0, 5)], [(100.0, 5)], [(100.0, 4)]], origin=[-250, -250, -400]
        )
        active = np.ones(mesh.nC, bool)
        x, y = np.meshgrid(np.linspace(-400, 400, 11), np.linspace(-400, 400, 11))
        xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
        low, high = np.array([-50, -50, -300]), np.array([50, 50, -200])
        sigma = 0.05
        inc, dec = 25.0, -35.0
    centers = mesh.cell_centers[active]
    support = np.all((centers > low) & (centers < high), axis=1)
    widths = mesh.h_gridded[active][support]
    body_centers = centers[support]
    west = np.min(body_centers - widths / 2, axis=0)
    east = np.max(body_centers + widths / 2, axis=0)
    prism = np.column_stack([west, east]).ravel()
    np.testing.assert_allclose(
        mesh.cell_volumes[active][support].sum(), np.prod(east - west), rtol=1e-12
    )
    truth = np.zeros((len(centers), 3))
    truth[support] = 0.05 * direction(inc, dec)
    field = direction(90.0, 0.0)
    mag = np.array([0.05 * 50000e-9 / mu_0 * direction(inc, dec)])
    _, vector = integrated_fields(xyz, [prism], [0.0], mag, order=20)
    clean = vector @ field
    # Independent quadrature must itself be converged before it is an oracle.
    _, vector2 = integrated_fields(xyz, [prism], [0.0], mag, order=24)
    np.testing.assert_allclose(clean, vector2 @ field, rtol=1e-7, atol=1e-7)
    observed = clean + sigma * np.random.default_rng(7112).normal(size=len(clean))
    return mesh, active, xyz, observed, sigma, truth, support, clean


def native_reference(mesh, active, xyz, observed, sigma, options):
    """Native SDK assembly; no Core optimizer or preconditioner is called."""
    from simpeg import (
        maps,
        regularization,
        optimization,
        data,
        data_misfit,
        inverse_problem,
        directives,
        inversion,
    )
    from simpeg.potential_fields import magnetics

    n = int(active.sum())
    survey = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(
            receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
            amplitude=50000.0,
            inclination=90.0,
            declination=0.0,
        )
    )
    sim = magnetics.simulation.Simulation3DIntegral(
        mesh,
        active_cells=active,
        survey=survey,
        chiMap=maps.IdentityMap(nP=3 * n),
        model_type="vector",
        engine="geoana",
        sensitivity_dtype=np.float64,
    )
    reg = regularization.VectorAmplitude(
        mesh,
        active_cells=active,
        mapping=maps.IdentityMap(nP=3 * n),
        reference_model=np.zeros(3 * n),
        reference_model_in_smooth=True,
        norms=[0, 2, 2, 2],
    )
    misfit = data_misfit.L2DataMisfit(
        simulation=sim,
        data=data.Data(
            survey, dobs=observed, standard_deviation=np.full(len(xyz), sigma)
        ),
    )
    opt = optimization.ProjectedGNCG(
        maxIter=options["iterations"],
        lower=-10.0,
        upper=10.0,
        maxIterLS=20,
        cg_maxiter=options["cg_maxiter"],
        cg_rtol=options["cg_rtol"],
        tolF=1e-6,
        tolX=1e-8,
        tolG=1e-6,
    )
    problem = inverse_problem.BaseInvProblem(misfit, reg, opt, init_bfgs=False)
    inversion_ = inversion.BaseInversion(
        problem,
        directiveList=[
            directives.UpdateSensitivityWeights(every_iteration=False),
            directives.BetaEstimate_ByEig(beta0_ratio=10.0, random_seed=0),
            directives.UpdateIRLS(
                max_irls_iterations=10,
                chifact_start=1.0,
                chifact_target=1.0,
                cooling_factor=2.0,
                cooling_rate=1,
            ),
            directives.UpdatePreconditioner(),
        ],
    )
    recovered = inversion_.run(np.full(3 * n, 1e-4))
    return (
        recovered,
        sim.dpred(recovered),
        np.asarray(sim.dpred(np.asarray(options["truth"]).ravel(order="F"))),
    )


def run(output, scale):
    from scripts.benchmark_voxel_recovery import CRITERIA
    from terraworkbench_core.inversion import run_potential_field_inversion
    from terraworkbench_core.recovery_metrics import model_recovery_metrics

    output.mkdir(parents=True, exist_ok=False)
    protocol = dict(
        source=SOURCE,
        source_license="SimPEG MIT",
        source_snapshot_sha256="703c1254a9e6a0b44a17cbbdf4fbb75b524695ad66fe761c0575bedef0c2570a",
        scale=scale,
        seed=7112,
        field=[50000.0, 90.0, 0.0],
        criteria=CRITERIA,
        numerical_changes_from_example="Pinned seed; independent data integration; 50 outer / 200 CG iterations and explicit zero reference; no plotting",
        variants=[
            "native_simpeg",
            "core",
            "core_known_support_control",
            "uniform_geometry_control",
        ],
        control_warning="Exact support is an oracle and excluded from claims about unconstrained recovery",
    )
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    mesh, active, xyz, observed, sigma, truth, support, clean = fixture(scale)
    n = int(active.sum())
    edges = mesh_edges(mesh, active)
    options = dict(
        cell_xy=5.0 if scale == "published" else 100.0,
        cell_z=5.0 if scale == "published" else 100.0,
        depth=100.0 if scale == "published" else 400.0,
        mesh=mesh,
        active_cells=active,
        max_cells=250000,
        iterations=50,
        cg_maxiter=200,
        cg_rtol=1e-4,
        regularization_norms=[0.0, 2.0, 2.0, 2.0],
        irls_iterations=10,
        beta0_ratio=10.0,
        field_inclination=90.0,
        field_declination=0.0,
        reference_model=np.zeros((n, 3)),
        reference_in_smooth=True,
        starting_model=np.full((n, 3), 1e-4),
        lower=-10.0,
        upper=10.0,
        sensitivity_dtype="float64",
    )
    # Preserve independent inputs and the truth, separately from production priors.
    np.savez_compressed(
        output / "input.npz",
        xyz=xyz,
        observed=observed,
        sigma=sigma,
        truth=truth,
        centers=mesh.cell_centers[active],
        volumes=mesh.cell_volumes[active],
        connectivity_edges=edges,
    )
    records = []
    for variant in protocol["variants"]:
        if variant == "uniform_geometry_control":
            from terraworkbench_core.prism_inversion import fit_prism_magnetization

            centers, widths = (
                mesh.cell_centers[active][support],
                mesh.h_gridded[active][support],
            )
            low, high = (
                (centers - widths / 2).min(axis=0),
                (centers + widths / 2).max(axis=0),
            )
            prism = np.column_stack([low, high]).ravel()
            fit = fit_prism_magnetization(
                xyz,
                [prism],
                observed,
                np.full(len(xyz), sigma),
                component="total",
                inclination=90.0,
                declination=0.0,
            )
            shaped = np.zeros((n, 3))
            shaped[support] = fit["magnetization_a_m"][0] / (50000e-9 / mu_0)
            model, predicted = shaped.ravel(order="F"), fit["predicted_nt"]
            diagnostics = dict(
                fit["diagnostics"],
                free_parameters=3,
                prior="Exact prism and uniform magnetization; truth in fitting",
            )
        elif variant == "native_simpeg":
            model, predicted, check = native_reference(
                mesh, active, xyz, observed, sigma, dict(options, truth=truth)
            )
            discrepancy = float(np.max(abs(check - clean)))
            if discrepancy > sigma * 1e-4:
                raise ValueError(
                    f"Independent quadrature/native-kernel mismatch: {discrepancy}"
                )
            diagnostics = dict(independent_forward_max_nt=discrepancy)
        else:
            chosen = dict(options)
            if variant.endswith("control"):
                chosen.update(
                    lower=np.where(support, -10.0, 0.0),
                    upper=np.where(support, 10.0, 0.0),
                    starting_model=np.where(support[:, None], 1e-4, 0.0)
                    * np.ones((n, 3)),
                )
            result = run_potential_field_inversion(
                "mvi", xyz, observed, np.full(len(xyz), sigma), **chosen
            )
            model, predicted, diagnostics = (
                result.model,
                result.predicted,
                result.diagnostics,
            )
        np.savez_compressed(
            output / (variant + ".npz"), model=model, predicted=predicted
        )
        recovery = model_recovery_metrics(
            mesh.cell_centers[active],
            mesh.cell_volumes[active],
            model.reshape((n, 3), order="F"),
            truth,
            criteria=CRITERIA,
            connectivity_edges=edges,
            vector=True,
            max_cells=250000,
            max_links=2000000,
        )
        item = dict(
            variant=variant,
            exact_support_in_fit=variant.endswith("control"),
            weighted_rms=float(np.sqrt(np.mean(((predicted - observed) / sigma) ** 2))),
            recovery=recovery,
            diagnostics=diagnostics,
        )
        records.append(item)
        (output / "results.partial.json").write_text(json.dumps(records, indent=2))
        print(
            json.dumps(
                dict(
                    variant=variant,
                    wrms=item["weighted_rms"],
                    model_error=recovery["model_relative_error"],
                    direction_errors=[
                        body["direction_error_deg"] for body in recovery["body_metrics"]
                    ],
                    passed=recovery["recovery_passed"],
                )
            ),
            flush=True,
        )
    report = dict(
        state="complete",
        utc=datetime.now(timezone.utc).isoformat(),
        commit=repository_provenance(ROOT)["commit"],
        source_provenance=repository_provenance(ROOT),
        protocol=protocol,
        versions={
            p: version(p)
            for p in [
                "numpy",
                "scipy",
                "simpeg",
                "discretize",
                "choclo",
                "geoana",
                "harmonica",
            ]
        },
        mesh_cells=mesh.nC,
        active_cells=n,
        observations=len(xyz),
        cases=records,
        input_sha256=hashlib.sha256((output / "input.npz").read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        core_source_sha256=hashlib.sha256(
            (ROOT / "terraworkbench_core/inversion.py").read_bytes()
        ).hexdigest(),
        supporting_sources_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in [
                "terraworkbench_core/recovery_metrics.py",
                "scripts/benchmark_voxel_recovery.py",
            ]
        },
        repository_dirty=repository_provenance(ROOT)["dirty"],
    )
    with np.load(output / "native_simpeg.npz") as a, np.load(output / "core.npz") as b:
        report["core_vs_native_model_relative_l2"] = float(
            np.linalg.norm(b["model"] - a["model"]) / np.linalg.norm(a["model"])
        )
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", choices=["quick", "published"], default="quick")
    args = parser.parse_args()
    preexisting = args.output.exists()
    try:
        run(args.output, args.scale)
    except Exception as error:
        if not preexisting and args.output.is_dir():
            (args.output / "failure.json").write_text(
                json.dumps(dict(state="failed", error=repr(error)), indent=2)
            )
        raise
