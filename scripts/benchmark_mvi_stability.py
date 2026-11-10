"""Physical one-prism counterexamples for spherical chart and step failures."""

import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.diagnose_mvi import (  # noqa: E402
    fixed_solve,
    simulation,
    runtime_record,
    source_record,
    write,
)


def fixture():
    from discretize import TensorMesh

    mesh = TensorMesh([[100.0]] * 3, origin=[-50.0, -50.0, -150.0])
    active = np.ones(mesh.nC, bool)
    x, y = np.meshgrid(np.linspace(-200.0, 200.0, 7), np.linspace(-200.0, 200.0, 7))
    xyz = np.c_[x.ravel(), y.ravel(), np.full(x.size, 100.0)]
    sim = simulation(mesh, active, xyz)
    matrix = np.asarray(sim.G)
    vector = np.array([0.0, 0.025, 0.02])
    # Orthogonal data make the old radial derivative vanish at the x chart.
    vector[0] = -(matrix[:, 0] @ (matrix @ vector)) / (matrix[:, 0] @ matrix[:, 0])
    return mesh, active, xyz, matrix, vector, np.full(len(xyz), 0.1)


def case(name, method, sensitivity_mode="ram"):
    from simpeg import maps, regularization
    from terraworkbench_core.inversion_diagnostics import fixed_l2_reference
    from terraworkbench_core.spherical_mvi import (
        spherical_optimizer,
        spherical_chart_recovery,
        cartesian_from_spherical,
    )

    mesh, active, xyz, matrix, vector, sigma = fixture()
    if name == "opposite":
        vector = np.array([-0.03, 0.0, 0.0])
        start = np.array([0.005, 0.0, 0.0])
    elif name == "zero":
        start = np.zeros(3)
    elif name == "tiny":
        start = np.array([1e-12, 0.0, 0.0])
    else:
        start = np.array([0.01, 0.2, 0.2])
    observed = matrix @ vector
    beta = 1e-8
    reference = fixed_l2_reference(
        matrix, observed, sigma, np.eye(3) * np.sqrt(mesh.cell_volumes[0]), beta=beta
    )
    sim = simulation(mesh, active, xyz, spherical=True)
    sim.store_sensitivities = sensitivity_mode
    reg = regularization.WeightedLeastSquares(
        mesh,
        mapping=maps.Projection(nP=3, index=np.array([0])),
        reference_model=np.zeros(3),
        alpha_s=1.0,
        alpha_x=0.0,
        alpha_y=0.0,
        alpha_z=0.0,
    )
    controls = []
    recovery = None
    if method == "guarded":
        # The helper builds its DataMisfit internally. Build the equivalent one
        # only for the recovery directive, with identical data and weights.
        from simpeg import data, data_misfit

        misfit = data_misfit.L2DataMisfit(
            simulation=sim,
            data=data.Data(sim.survey, dobs=observed, standard_deviation=sigma),
        )
        recovery = spherical_chart_recovery(sim, misfit, reg, np.ones(1), 0.0)
        controls.append(recovery)
    factory = (
        (
            lambda **kwargs: spherical_optimizer(
                1, scaled_cg=method == "guarded", **kwargs
            )
        )
        if method in ("guarded", "step_only")
        else None
    )
    solved = fixed_solve(
        sim,
        observed,
        sigma,
        reg,
        start,
        beta,
        lower=np.array([0.0, -np.pi / 2, -np.inf]),
        upper=np.array([1.0, np.pi / 2, np.inf]),
        iterations=50,
        strict=method == "tight_only",
        controls=controls,
        optimizer_factory=factory,
        line_search_iterations=20,
    )
    physical = cartesian_from_spherical(solved["model"])
    wrms = float(np.sqrt(np.mean(((matrix @ physical - observed) / sigma) ** 2)))
    error = float(
        np.linalg.norm(physical - reference["model"])
        / np.linalg.norm(reference["model"])
    )
    physical_gradient = 2 * matrix.T @ ((matrix @ physical - observed) / sigma**2)
    physical_gradient += 2 * beta * mesh.cell_volumes[0] * physical
    physical_optimality = float(
        np.linalg.norm(physical_gradient)
        / max(np.linalg.norm(2 * matrix.T @ (observed / sigma**2)), 1.0)
    )
    return dict(
        case=name,
        method=method,
        weighted_rms=wrms,
        relative_reference_error=error,
        cartesian_scaled_optimality=physical_optimality,
        physical_model=physical,
        chart_reorientations=0 if recovery is None else recovery.reorientations,
        pole_reorientations=0 if recovery is None else recovery.pole_reorientations,
        recovery_events=[] if recovery is None else recovery.events,
        passed=wrms <= 1.0 and error <= 1e-5,
        **solved,
    )


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            runtime=runtime_record(),
            provenance=source_record(),
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            scope="Known one-prism geometry; solver counterexamples, not free geological recovery",
            beta=1e-8,
            sigma_nt=0.1,
            amplitude_cap=1.0,
            iterations=50,
            methods=["legacy", "tight_only", "step_only", "guarded"],
            optimizer_metrics=dict(
                step_only="raw_legacy_ablation", guarded="raw_and_Jacobi_energy"
            ),
            cases=["zero", "tiny", "opposite", "regular"],
            criteria=dict(data_wrms_max=1.0, relative_reference_error_max=1e-5),
        ),
    )
    rows = []
    for name in ("zero", "tiny", "opposite", "regular"):
        for method in ("legacy", "tight_only", "step_only", "guarded"):
            result = case(name, method)
            rows.append(result)
            write(output / "results.partial.json", rows)
            print(
                {
                    key: result[key]
                    for key in (
                        "case",
                        "method",
                        "weighted_rms",
                        "relative_reference_error",
                        "chart_reorientations",
                        "passed",
                    )
                },
                flush=True,
            )
    write(output / "results.json", dict(cases=rows))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
