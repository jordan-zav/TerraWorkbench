"""Pinned SimPEG public cross-gradient benchmark; no QGIS or private surveys.

The reference reproduces the documented objective with fixed seed and no unused
BFGS initialization. Raw tutorial source is cached for provenance, never executed.
Each inversion runs in a separate process; numerical differences are reported.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA_URL = "https://storage.googleapis.com/simpeg/doc-assets/cross_gradient_data.tar.gz"
SOURCE_URL = "https://docs.simpeg.xyz/v0.25.0/_downloads/97037fe4195e5357dafb188d05d3a4c3/plot_inv_3_cross_gradient_pf.py"
PINS = {
    "cross_gradient_data.tar.gz": (
        DATA_URL,
        "ace33b2a651b7326185a53cbc799179817430e72f0d50cfd952d9baed52cb8bb",
    ),
    "reference.py": (
        SOURCE_URL,
        "f38d03d22afe8476523420dc48f3696192ce00f85b78757a269c358ee54842da",
    ),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(cache):
    cache.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in PINS.items():
        target = cache / name
        if not target.exists():
            with urlopen(url, timeout=90) as response:
                data = response.read(50_000_001)
            if len(data) > 50_000_000 or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(
                    "Download does not match the pinned benchmark: " + name
                )
            with target.open("xb") as stream:
                stream.write(data)
        if sha(target) != expected:
            raise ValueError("Cached benchmark checksum mismatch: " + name)
    with tarfile.open(cache / "cross_gradient_data.tar.gz", "r:gz") as archive:
        if sum(m.size for m in archive.getmembers()) > 200_000_000:
            raise ValueError("Oversized benchmark archive")
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name:
                raise ValueError("Unsafe archive member")
            target = cache / "dataset" / Path(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("Only regular archive files are accepted")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.extractfile(member).read()
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError("Extracted benchmark changed: " + member.name)
            else:
                with target.open("xb") as stream:
                    stream.write(data)
    return cache / "dataset/cross_gradient_data"


def inputs(cache):
    from discretize import TensorMesh
    from discretize.utils import active_from_xyz

    folder = fetch(cache)
    grav = np.loadtxt(folder / "gravity_data.obs")
    mag = np.loadtxt(folder / "magnetic_data.obs")
    topo = np.loadtxt(folder / "topo.txt")
    np.testing.assert_array_equal(grav[:, :3], mag[:, :3])
    h = [(5.0, 5, -1.3), (5.0, 40), (5.0, 5, 1.3)]
    mesh = TensorMesh([h, h, [(5.0, 5, -1.3), (5.0, 15)]], "CCN")
    active = active_from_xyz(mesh, topo)
    uncertainties = [
        0.01 * np.max(abs(array[:, -1])) * np.ones(len(array)) for array in (grav, mag)
    ]
    truth = {
        name: np.loadtxt(folder / ("true_model_" + suffix + ".txt"))[active]
        for name, suffix in (("density", "dens"), ("susceptibility", "susc"))
    }
    return folder, mesh, active, grav, mag, uncertainties, truth


def reference(
    mesh,
    active,
    grav,
    mag,
    sigma,
    iterations,
    progress,
    folder,
    magnetic_engine="geoana",
    weighted_preconditioner=False,
):
    """Controlled reproduction of SimPEG 0.25 tutorial's joint recipe."""
    from simpeg import (
        data,
        data_misfit,
        directives,
        inverse_problem,
        inversion,
        maps,
        optimization,
        regularization,
    )
    from simpeg.potential_fields import gravity, magnetics

    n = int(active.sum())
    wires = maps.Wires(("density", n), ("susceptibility", n))
    gs = gravity.survey.Survey(
        gravity.sources.SourceField(
            receiver_list=[gravity.receivers.Point(grav[:, :3], components="gz")]
        )
    )
    ms = magnetics.survey.Survey(
        magnetics.sources.UniformBackgroundField(
            receiver_list=[magnetics.receivers.Point(mag[:, :3], components="tmi")],
            amplitude=50000.0,
            inclination=90.0,
            declination=0.0,
        )
    )
    sg = gravity.simulation.Simulation3DIntegral(
        mesh, survey=gs, active_cells=active, rhoMap=wires.density, engine="choclo"
    )
    sm = magnetics.simulation.Simulation3DIntegral(
        mesh,
        survey=ms,
        active_cells=active,
        chiMap=wires.susceptibility,
        model_type="scalar",
        engine=magnetic_engine,
        **({"n_processes": 1} if magnetic_engine == "geoana" else {}),
    )
    misfit = data_misfit.L2DataMisfit(
        data=data.Data(gs, dobs=grav[:, -1], standard_deviation=sigma[0]), simulation=sg
    )
    misfit += data_misfit.L2DataMisfit(
        data=data.Data(ms, dobs=mag[:, -1], standard_deviation=sigma[1]), simulation=sm
    )
    rg = regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=wires.density
    )
    rm = regularization.WeightedLeastSquares(
        mesh, active_cells=active, mapping=wires.susceptibility
    )
    reg = (
        rg + rm + 2e12 * regularization.CrossGradient(mesh, wires, active_cells=active)
    )
    opt = optimization.ProjectedGNCG(
        maxIter=iterations,
        lower=-2.0,
        upper=2.0,
        maxIterLS=20,
        cg_maxiter=100,
        cg_rtol=1e-3,
        cg_atol=0.0,
        tolX=1e-3,
    )
    problem = inverse_problem.BaseInvProblem(misfit, reg, opt, init_bfgs=False)
    baseline = {}
    for prefix in ("true_model", "single_model"):
        density = np.loadtxt(folder / (prefix + "_dens.txt"))[active]
        susceptibility = np.loadtxt(folder / (prefix + "_susc.txt"))[active]
        if not np.isfinite(density).all() or not np.isfinite(susceptibility).all():
            baseline[prefix] = {
                "state": "unavailable_nonfinite_active_cells",
                "nonfinite_density_cells": int(np.count_nonzero(~np.isfinite(density))),
                "nonfinite_susceptibility_cells": int(
                    np.count_nonzero(~np.isfinite(susceptibility))
                ),
            }
            continue
        vector = np.r_[density, susceptibility]
        baseline[prefix] = {
            "gravity_wrms": float(
                np.sqrt(np.mean(((sg.dpred(vector) - grav[:, -1]) / sigma[0]) ** 2))
            ),
            "magnetics_wrms": float(
                np.sqrt(np.mean(((sm.dpred(vector) - mag[:, -1]) / sigma[1]) ** 2))
            ),
        }
    if magnetic_engine == "choclo":
        alternate = magnetics.simulation.Simulation3DIntegral(
            mesh,
            survey=ms,
            active_cells=active,
            chiMap=wires.susceptibility,
            model_type="scalar",
            engine="geoana",
            n_processes=1,
        )
        difference = np.asarray(sm.G, float) - np.asarray(alternate.G, float)
        baseline["magnetic_kernel_relative_difference"] = float(
            np.linalg.norm(difference) / np.linalg.norm(alternate.G)
        )
        baseline["magnetic_kernel_max_abs_difference"] = float(np.max(abs(difference)))
    history = []

    class Progress(directives.InversionDirective):
        def endIter(self):
            history.append(
                dict(
                    iteration=int(self.opt.iter),
                    phi_d=float(self.invProb.phi_d),
                    phi_m=float(self.invProb.phi_m),
                )
            )
            progress(int(self.opt.iter))

    controls = [
        directives.SimilarityMeasureInversionDirective(),
        directives.UpdateSensitivityWeights(every_iteration=False),
        directives.MovingAndMultiTargetStopping(tol=1e-6),
        directives.PairedBetaEstimate_ByEig(beta0_ratio=1.0, seed=0),
        directives.PairedBetaSchedule(cooling_factor=5, cooling_rate=1),
        directives.UpdatePreconditioner(),
        Progress(),
    ]
    if weighted_preconditioner:
        # Independent reference construction: retain the tutorial cases above
        # and apply the corrected objective diagonal only in reference_weighted.
        from scipy.sparse import diags

        class ObjectiveDiagonal(directives.UpdatePreconditioner):
            def initialize(self):
                m = self.invProb.model
                diag = self.invProb.beta * self.invProb.reg.deriv2(m).diagonal()
                for weight, term in zip(self.dmisfit.multipliers, self.dmisfit.objfcts):
                    diag += 2 * weight * term.simulation.getJtJdiag(m, W=term.W)
                self.opt.approxHinv = diags(1 / diag, format="csr")

            def endIter(self):
                self.initialize()

        controls[-2] = ObjectiveDiagonal()
    model = inversion.BaseInversion(problem, controls).run(np.full(2 * n, 1e-6))
    return (
        dict(
            density=wires.density * model,
            susceptibility=wires.susceptibility * model,
            gravity=sg.dpred(model),
            magnetics=sm.dpred(model),
        ),
        history,
        baseline,
    )


def worker(cache, output, case, iterations, joint_options=None, sigma_scale=1.0):
    from terraworkbench_core.inversion import (
        full_model,
        joint_full_models,
        run_inversion_workflow,
        run_joint_cross_gradient_inversion,
        write_mesh_vtk,
    )

    output.mkdir(parents=True, exist_ok=False)
    folder, mesh, active, grav, mag, sigma, truth = inputs(cache)
    if not np.isfinite(sigma_scale) or sigma_scale <= 0:
        raise ValueError("Uncertainty scale must be finite and positive")
    sigma = [s * sigma_scale for s in sigma]
    report = dict(
        case=case,
        state="running",
        mesh_cells=mesh.nC,
        active_cells=int(active.sum()),
        observations=[len(grav), len(mag)],
        matrix_bytes_float32=(len(grav) + len(mag)) * int(active.sum()) * 4,
        versions={
            name: version(name)
            for name in ("simpeg", "discretize", "numpy", "scipy", "choclo")
        },
        core_source_sha256=sha(ROOT / "terraworkbench_core/inversion.py"),
        archive_sha256=sha(cache / "cross_gradient_data.tar.gz"),
        reference_source_sha256=sha(cache / "reference.py"),
        input_sha256={p.name: sha(p) for p in folder.iterdir() if p.is_file()},
        joint_options=joint_options or {},
        sigma_scale=sigma_scale,
    )

    def save(iteration=None):
        if iteration is not None:
            report["iteration"] = iteration
        (output / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save()
    started = time.perf_counter()
    try:
        if case.startswith("reference"):
            values, history, baseline = reference(
                mesh,
                active,
                grav,
                mag,
                sigma,
                iterations,
                save,
                folder,
                magnetic_engine="geoana" if case == "reference" else "choclo",
                weighted_preconditioner=case == "reference_weighted",
            )
            report["history"] = history
            report["published_model_baselines"] = baseline
        elif case == "joint":
            options = dict(
                cell_xy=5.0,
                cell_z=5.0,
                depth=100.0,
                mesh=mesh,
                active_cells=active,
                iterations=iterations,
                density_bounds=(-2.0, 2.0),
                susceptibility_bounds=(-2.0, 2.0),
                starting_density=1e-6,
                starting_susceptibility=1e-6,
                field_inclination=90.0,
                field_declination=0.0,
                coupling_weight=2e12,
                # Preserve the tutorial-reproduction trajectory. Pass
                # gauss_newton in joint_options to audit the current default.
                cross_gradient_hessian="simpeg",
                max_sensitivity_bytes=512 * 1024**2,
                progress_callback=save,
            )
            options.update(joint_options or {})
            result = run_joint_cross_gradient_inversion(
                grav[:, :3],
                grav[:, -1],
                sigma[0],
                mag[:, :3],
                mag[:, -1],
                sigma[1],
                **options,
            )
            values = dict(
                density=result.density,
                susceptibility=result.susceptibility,
                gravity=result.predicted_gravity,
                magnetics=result.predicted_magnetics,
            )
            report["diagnostics"] = result.diagnostics
            report["history"] = result.history
            write_mesh_vtk(output / "joint.vtk", mesh, joint_full_models(result))
        else:
            index = 0 if case == "gravity" else 1
            observed = (grav, mag)[index]
            result = run_inversion_workflow(
                case,
                observed[:, :3],
                observed[:, -1],
                sigma[index],
                output_directory=output / "workflow",
                cell_xy=5.0,
                cell_z=5.0,
                depth=100.0,
                mesh=mesh,
                active_cells=active,
                reference_value=1e-6,
                starting_model=1e-6,
                lower=-2.0,
                upper=2.0,
                field_inclination=90.0,
                field_declination=0.0,
                iterations=iterations,
                max_sensitivity_bytes=512 * 1024**2,
                progress_callback=save,
            )
            key = "density" if case == "gravity" else "susceptibility"
            values = {
                key: result.model,
                "gravity" if index == 0 else "magnetics": result.predicted,
            }
            report["diagnostics"] = result.diagnostics
            assert full_model(result)
        if not all(np.isfinite(v).all() for v in values.values()):
            raise ValueError("Nonfinite benchmark result")
        for key in ("gravity", "magnetics"):
            if key in values:
                index = ("gravity", "magnetics").index(key)
                report[key + "_wrms"] = float(
                    np.sqrt(
                        np.mean(
                            ((values[key] - (grav, mag)[index][:, -1]) / sigma[index])
                            ** 2
                        )
                    )
                )
        for key in truth:
            if key in values:
                report[key + "_relative_model_error"] = float(
                    np.linalg.norm(values[key] - truth[key])
                    / np.linalg.norm(truth[key])
                )
        np.savez_compressed(output / "result.npz", **values)
        report["state"] = "complete"
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        report["seconds"] = time.perf_counter() - started
        save()
        print(json.dumps(report, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--case",
        choices=(
            "all",
            "reference",
            "reference_choclo",
            "reference_weighted",
            "joint",
            "gravity",
            "susceptibility",
        ),
        default="all",
    )
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--joint-options", type=Path)
    parser.add_argument("--sigma-scale", type=float, default=1.0)
    args = parser.parse_args()
    if args.case != "all":
        if args.joint_options and args.case != "joint":
            parser.error("--joint-options requires --case joint")
        overrides = (
            json.loads(args.joint_options.read_text(encoding="utf-8"))
            if args.joint_options
            else None
        )
        worker(
            args.cache,
            args.output,
            args.case,
            args.iterations,
            overrides,
            args.sigma_scale,
        )
        return
    if args.joint_options or args.sigma_scale != 1.0:
        parser.error(
            "Overrides require a single --case joint to preserve the reference comparison"
        )
    import psutil

    args.output.mkdir(parents=True, exist_ok=False)
    summary = {}
    for case in (
        "reference",
        "reference_choclo",
        "reference_weighted",
        "joint",
        "gravity",
        "susceptibility",
    ):
        with (args.output / (case + ".log")).open("w", encoding="utf-8") as stream:
            child = subprocess.Popen(
                [
                    sys.executable,
                    __file__,
                    "--cache",
                    str(args.cache),
                    "--output",
                    str(args.output / case),
                    "--case",
                    case,
                    "--iterations",
                    str(args.iterations),
                ],
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            process, peak, start = psutil.Process(child.pid), 0, time.perf_counter()
            while child.poll() is None:
                try:
                    # Windows venv python.exe can be a small redirector process;
                    # include its actual interpreter descendants in the sample.
                    tree = [process, *process.children(recursive=True)]
                    peak = max(
                        peak, sum(p.memory_info().rss for p in tree if p.is_running())
                    )
                except psutil.NoSuchProcess:
                    pass
                if time.perf_counter() - start > 1800:
                    child.terminate()
                    child.wait()
                    raise RuntimeError(
                        "Benchmark case exceeded its 30-minute budget: " + case
                    )
                time.sleep(0.1)
        if child.returncode:
            raise RuntimeError("Benchmark failed: " + case + "; see its retained log")
        report = json.loads(
            (args.output / case / "report.json").read_text(encoding="utf-8")
        )
        report["sampled_peak_rss_bytes"] = peak
        summary[case] = report
        (args.output / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k.endswith("wrms")
                    or k in ("case", "seconds", "sampled_peak_rss_bytes")
                }
            ),
            flush=True,
        )
    differences = {}
    for reference_case in ("reference", "reference_choclo", "reference_weighted"):
        with (
            np.load(args.output / reference_case / "result.npz") as ref,
            np.load(args.output / "joint/result.npz") as core,
        ):
            differences[reference_case] = {
                key: float(
                    np.linalg.norm(core[key] - ref[key])
                    / max(np.linalg.norm(ref[key]), 1e-30)
                )
                for key in ref.files
            }
    summary["reference_core_relative_differences"] = differences
    summary["same_engine_relative_tolerance"] = 1e-6
    summary["same_engine_reference"] = "reference_weighted"
    summary["same_engine_check_passed"] = (
        max(differences["reference_weighted"].values()) <= 1e-6
    )
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    if not summary["same_engine_check_passed"]:
        raise AssertionError("Same-engine reproduction exceeds the declared tolerance")
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(differences), flush=True)


if __name__ == "__main__":
    main()
