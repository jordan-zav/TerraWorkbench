"""Thin-SVD error audit; never constructs model-by-model resolution matrices."""

import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.diagnose_mvi import simulation, write, runtime_record, source_record  # noqa: E402


def run(output, campaigns):
    from scripts.benchmark_mvi_reference import fixture
    from terraworkbench_core.inversion_diagnostics import linear_error_partition

    output.mkdir(parents=True, exist_ok=False)
    mesh, active, xyz, _, sigma, truth, _, clean = fixture("published")
    true = truth.ravel(order="F")
    labels, errors, input_hashes = [], [], {}
    for label, folder in campaigns:
        folder = Path(folder)
        with np.load(folder / "input.npz") as source:
            np.testing.assert_allclose(source["truth"], truth, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(source["clean"], clean, rtol=1e-12, atol=1e-12)
        for path in sorted(folder.glob("*.npz")):
            if path.name == "input.npz":
                continue
            with np.load(path) as case:
                if "model" not in case.files:
                    continue
                model = case["model"]
                if model.shape != true.shape:
                    raise ValueError(
                        "All models must use the frozen Cartesian ENU mesh"
                    )
                labels.append(label + "/" + path.stem)
                errors.append(model - true)
                input_hashes[labels[-1]] = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(errors) < 1:
        raise ValueError("Require at least one recorded campaign")
    write(
        output / "protocol.json",
        dict(
            runtime=runtime_record(),
            provenance=source_record(),
            labels=labels,
            parameters=len(true),
            observations=len(xyz),
            max_float64_elements=250_000_000,
            scope="Numerical row/null decomposition, not nonlinear posterior or acceptable geology",
            model_artifact_sha256=input_hashes,
        ),
    )
    matrix = np.asarray(simulation(mesh, active, xyz).G)
    forward_error = float(np.max(abs(matrix @ true - clean)))
    if forward_error > 1e-5:
        raise AssertionError("Independent physical response check failed")
    error = np.column_stack(errors)
    result = linear_error_partition(
        matrix,
        np.full(len(xyz), sigma),
        error,
        np.tile(mesh.cell_volumes[active], 3),
        max_elements=250_000_000,
    )
    row, null = result.pop("row_error"), result.pop("null_error")
    records = []
    for i, label in enumerate(labels):
        data = matrix @ error[:, i] / sigma
        invisible = matrix @ null[:, i] / sigma
        numerical_leakage = float(
            np.linalg.norm(invisible) / max(np.linalg.norm(data), 1e-20)
        )
        records.append(
            dict(
                label=label,
                row_error_energy_fraction=float(result["row_energy_fraction"][i]),
                numerical_null_error_energy_fraction=float(
                    result["null_energy_fraction"][i]
                ),
                null_data_leakage_relative=numerical_leakage,
                decomposition_verified=numerical_leakage <= 1e-6,
            )
        )
        print(records[-1], flush=True)
    result.pop("row_energy_fraction")
    result.pop("null_energy_fraction")
    write(
        output / "results.json",
        dict(
            forward_max_nt=forward_error,
            subspace=result,
            cases=records,
            limitation="Numerical null space is not all weakly resolved modes; this does not validate a chosen prior",
        ),
    )
    np.savez_compressed(
        output / "decomposition.npz",
        row_error=row,
        null_error=null,
        singular_values=result["singular_values"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--campaign",
        nargs=2,
        action="append",
        metavar=("LABEL", "DIRECTORY"),
        required=True,
    )
    args = parser.parse_args()
    run(args.output, args.campaign)
