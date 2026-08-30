"""Small real-QGIS smoke test for the optional SimPEG inversion stack."""

from pathlib import Path
import os
import site
import sys
import numpy as np

PROJECT_PARENT = Path(
    os.environ.get(
        "TERRAWORKBENCH_PLUGIN_PARENT", str(Path(__file__).resolve().parents[2])
    )
)
sys.path.insert(0, str(PROJECT_PARENT))

TEST_DEPENDENCY_PATH = os.environ.get("TERRAWORKBENCH_TEST_DEPENDENCY_PATH", "")
if TEST_DEPENDENCY_PATH:
    site.addsitedir(TEST_DEPENDENCY_PATH)
    if TEST_DEPENDENCY_PATH not in sys.path:
        sys.path.insert(0, TEST_DEPENDENCY_PATH)

from TerraWorkbench.dependencies import import_simpeg_stack  # noqa: E402
from TerraWorkbench.inversion_core import (  # noqa: E402
    full_model,
    joint_full_models,
    run_joint_cross_gradient_inversion,
    run_potential_field_inversion,
)


def main():
    simpeg, discretize = import_simpeg_stack()
    xyz = np.array(
        [
            [0, 0, 100],
            [100, 0, 100],
            [200, 0, 100],
            [0, 100, 100],
            [100, 100, 100],
            [200, 100, 100],
            [0, 200, 100],
            [100, 200, 100],
            [200, 200, 100],
        ],
        dtype=float,
    )
    observed = np.array([0, 1, 0, 1, 2, 1, 0, 1, 0], dtype=float)
    sigma = np.ones(observed.size)
    for kind in ("gravity", "susceptibility", "mvi"):
        progress = []
        result = run_potential_field_inversion(
            kind,
            xyz,
            observed,
            sigma,
            cell_xy=100,
            cell_z=100,
            depth=200,
            padding=0,
            max_cells=1000,
            iterations=1,
            mesh_type="tree" if kind == "gravity" else "tensor",
            refinement_levels=2,
            cancel_callback=lambda: False,
            progress_callback=progress.append,
        )
        if (
            result.predicted.shape != observed.shape
            or not full_model(result)
            or not progress
        ):
            raise AssertionError(f"Invalid {kind} inversion outputs")
        print(f"OK: {kind} inversion ({result.model.size} parameters)", flush=True)
    joint = run_joint_cross_gradient_inversion(
        xyz,
        observed / 10.0,
        sigma / 10.0,
        xyz,
        observed,
        sigma,
        cell_xy=100,
        cell_z=100,
        depth=200,
        padding=1,
        max_cells=1000,
        iterations=1,
        coupling_weight=1e4,
        mesh_type="tree",
        refinement_levels=2,
    )
    if joint.predicted_gravity.shape != observed.shape or not joint_full_models(joint):
        raise AssertionError("Invalid joint inversion outputs")
    print(
        f"OK: joint cross-gradient inversion ({joint.mesh.nC} TreeMesh cells)",
        flush=True,
    )
    print(
        f"OK: SimPEG {simpeg.__version__}; discretize {discretize.__version__}",
        flush=True,
    )


if __name__ == "__main__":
    main()
