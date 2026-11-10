"""Bounded coarse-mesh prediction checks on pinned downloaded observations.

This is not exact replication of a tutorial inversion or a geological recovery gate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def reference_prediction(result, xyz, kind, field):
    from simpeg import maps
    from simpeg.potential_fields import gravity, magnetics

    common = dict(
        mesh=result.mesh,
        active_cells=result.active,
        engine="geoana",
        store_sensitivities="forward_only",
    )
    mapping = maps.IdentityMap(nP=len(result.model))
    if kind == "gravity":
        survey = gravity.survey.Survey(
            gravity.sources.SourceField(
                receiver_list=[gravity.receivers.Point(xyz, components="gz")]
            )
        )
        simulation = gravity.simulation.Simulation3DIntegral(
            survey=survey, rhoMap=mapping, **common
        )
    else:
        survey = magnetics.survey.Survey(
            magnetics.sources.UniformBackgroundField(
                receiver_list=[magnetics.receivers.Point(xyz, components="tmi")],
                amplitude=field["field_amplitude"],
                inclination=field["field_inclination"],
                declination=field["field_declination"],
            )
        )
        simulation = magnetics.simulation.Simulation3DIntegral(
            survey=survey, chiMap=mapping, model_type="scalar", **common
        )
    return np.asarray(simulation.dpred(result.model))


def run(cache, output):
    from terraworkbench_core.inversion import run_potential_field_inversion
    from scripts.fetch_acceptance_references import fetch

    paths, sources = fetch(cache)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protocol = dict(
        cases=["gravity", "susceptibility"],
        cell_xy_m=20,
        cell_z_m=20,
        depth_m=160,
        padding_cells=3,
        iterations=40,
        cg_maxiter=800,
        cg_rtol=1e-4,
        relative_peak_uncertainty=0.02,
        split="Every fifth station withheld in file order, before fitting",
        acceptance=dict(training_wrms_max=2, withheld_wrms_max=3),
        scope="Coarse-mesh predictive end-to-end test on downloaded observations, not exact tutorial replication or geological recovery",
        gravity_component="up",
        source_note="Gravity prose says 2.5 percent but executable tutorial code says 2 percent; follows the code explicitly",
    )
    protocol["field"] = dict(
        field_amplitude=50000, field_inclination=90, field_declination=0
    )
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    report = dict(
        state="running",
        protocol=protocol,
        cases=[],
        sources=sources,
        source_sha256={
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                *list((ROOT / "terraworkbench_core").glob("*.py")),
                Path(__file__).resolve(),
                ROOT / "scripts/fetch_acceptance_references.py",
                ROOT / "scripts/mvi_acceptance_sources.json",
            ]
        },
    )
    for kind in ["gravity", "susceptibility"]:
        folder = paths[kind]
        prefix = "gravity" if kind == "gravity" else "magnetics"
        data_path = folder / (prefix + "_data.obs")
        topo_path = folder / (prefix + "_topo.txt")
        data = np.loadtxt(data_path)
        topo = np.loadtxt(topo_path)
        xyz = data[:, :3]
        values = data[:, -1]
        sigma = float(0.02 * np.max(abs(values)))
        held = np.arange(len(xyz)) % 5 == 0
        fit = ~held
        result = run_potential_field_inversion(
            kind,
            xyz[fit],
            values[fit],
            np.full(fit.sum(), sigma),
            cell_xy=20,
            cell_z=20,
            depth=160,
            padding=3,
            topography=topo,
            iterations=40,
            cg_maxiter=800,
            cg_rtol=1e-4,
            gravity_component="up",
            sensitivity_dtype="float64",
            sensitivity_mode="ram",
            max_cells=20000,
            **protocol["field"],
        )
        predicted = reference_prediction(result, xyz[held], kind, protocol["field"])
        training_reference = reference_prediction(
            result, xyz[fit], kind, protocol["field"]
        )
        np.testing.assert_allclose(
            training_reference, result.predicted, rtol=1e-8, atol=1e-9
        )
        train = float(np.sqrt(np.mean(((result.predicted - values[fit]) / sigma) ** 2)))
        withheld = float(np.sqrt(np.mean(((predicted - values[held]) / sigma) ** 2)))
        raw = result.diagnostics.get("all_audited_cg_tolerances_met")
        row = dict(
            kind=kind,
            observations=len(values),
            training=int(fit.sum()),
            withheld=int(held.sum()),
            active_cells=int(result.active.sum()),
            uncertainty=sigma,
            training_wrms=train,
            withheld_wrms=withheld,
            prediction_passed=train <= 2 and withheld <= 3,
            all_audited_cg_tolerances_met=raw,
            data_sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),
            topography_sha256=hashlib.sha256(topo_path.read_bytes()).hexdigest(),
            diagnostics=result.diagnostics,
            history=result.history,
            geological_recovery="not_assessed_no_truth_model_array_in_download",
        )
        np.savez_compressed(
            output / (kind + ".npz"),
            xyz=xyz,
            observed=values,
            held_mask=held,
            predicted_train=result.predicted,
            predicted_held=predicted,
            model=result.model,
            centers=result.mesh.cell_centers[result.active],
            volumes=result.mesh.cell_volumes[result.active],
        )
        report["cases"].append(row)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(kind, train, withheld, raw, flush=True)
    report["state"] = "complete"
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PUBLIC_REPORT", output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.cache, args.output)
