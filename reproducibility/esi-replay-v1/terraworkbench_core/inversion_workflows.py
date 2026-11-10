"""Standalone joint inversion artifacts and reusable input provenance.

Completion certifies the artifact transaction, not geological uniqueness.
Failed/strictly rejected runs retain their evidence and cannot overwrite a run.
"""

import hashlib
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np

from .operations import _input_digest
from ._array_contract import as_array


def input_provenance(inputs, options):
    """Hash typed data, numerical options and supplied physical mesh geometry."""
    values = dict(inputs)
    excluded = []
    for name, value in options.items():
        if callable(value):
            excluded.append(name)
        elif isinstance(value, Path):
            values["option_" + name] = str(value)
        elif name == "mesh":
            if value is not None:
                values["mesh_geometry"] = dict(
                    centers=np.asarray(value.cell_centers),
                    widths=np.asarray(value.h_gridded),
                    origin=np.asarray(value.origin),
                    kind=type(value).__name__,
                )
        else:
            values["option_" + name] = (
                np.asarray(value) if isinstance(value, (list, tuple)) else value
            )
    return dict(
        input_sha256=_input_digest(values),
        input_hash_scheme="typed-tree-sha256-v2",
        hash_scope="Explicit numerical inputs/options and mesh cell geometry; callback state, mesh topology and transitive dependencies excluded",
        excluded_callbacks=excluded,
        core_sources_sha256={
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in ("inversion.py", "inversion_workflows.py", "operations.py", "regularization_profiles.py", "spherical_mvi.py")
        },
    )


def save_manifest(path, manifest):
    target = Path(path)
    staged = target.with_name(target.name + ".tmp")
    staged.write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    staged.replace(target)


def run_joint_inversion_workflow(
    gravity_xyz,
    gravity_data,
    gravity_std,
    magnetic_xyz,
    magnetic_data,
    magnetic_std,
    *,
    output_directory,
    regional_gravity=None,
    regional_magnetics=None,
    require_convergence=False,
    **options,
):
    """Run joint gravity/TMI and retain models, residuals, VTK and provenance.

    Gravity mGal follows gravity_component; density is g/cm3 and susceptibility
    SI. Coordinates are projected metres, positive-up z. Regional predictions
    are DATA-space backgrounds, distinct from property reference models.
    require_convergence rejects a finite but unconverged solve after retaining
    its diagnostics/artifacts with a failed manifest. Exact existing outputs
    are never reused. Native compression/VTK writes are not interruptible.
    """
    from .inversion import (
        run_joint_cross_gradient_inversion,
        joint_full_models,
        write_mesh_vtk,
    )

    if type(require_convergence) is not bool:
        raise ValueError("require_convergence must be boolean")
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(
        state="running", kind="joint_gravity_susceptibility", schema_version=2
    )
    path = output / "run.json"
    save_manifest(path, manifest)
    try:
        arrays = dict(
            zip(
                (
                    "gravity_xyz",
                    "gravity_data",
                    "gravity_std",
                    "magnetic_xyz",
                    "magnetic_data",
                    "magnetic_std",
                ),
                [
                    as_array(value, float)
                    for value in (
                        gravity_xyz,
                        gravity_data,
                        gravity_std,
                        magnetic_xyz,
                        magnetic_data,
                        magnetic_std,
                    )
                ],
            )
        )
        for label, supplied in (
            ("gravity", regional_gravity),
            ("magnetics", regional_magnetics),
        ):
            data_name = "gravity_data" if label == "gravity" else "magnetic_data"
            regional = (
                np.zeros_like(arrays[data_name])
                if supplied is None
                else as_array(supplied, float)
            )
            if (
                regional.shape != arrays[data_name].shape
                or not np.isfinite(regional).all()
            ):
                raise ValueError(
                    "Regional predictions must be finite and match each dataset"
                )
            arrays["regional_" + label] = regional
        manifest.update(input_provenance(arrays, options))
        manifest.update(
            versions={
                name: version(name)
                for name in ("simpeg", "discretize", "numpy", "scipy", "choclo")
            },
            units=dict(
                coordinates="projected metres, upward z",
                gravity="mGal, declared up/down",
                density="g/cm3",
                magnetics="nT",
                susceptibility="SI",
            ),
            require_convergence=require_convergence,
        )
        save_manifest(path, manifest)
        result = run_joint_cross_gradient_inversion(
            arrays["gravity_xyz"],
            arrays["gravity_data"] - arrays["regional_gravity"],
            arrays["gravity_std"],
            arrays["magnetic_xyz"],
            arrays["magnetic_data"] - arrays["regional_magnetics"],
            arrays["magnetic_std"],
            **options,
        )
        cancel = options.get("cancel_callback")
        if cancel is not None and cancel():
            raise RuntimeError("Joint inversion export canceled")
        models = joint_full_models(result)
        np.savez_compressed(
            output / "model.npz",
            active=result.active,
            density_active=result.density,
            susceptibility_active=result.susceptibility,
            cell_centers=result.mesh.cell_centers,
            cell_widths=result.mesh.h_gridded,
            predicted_gravity_residual=result.predicted_gravity,
            predicted_magnetics_residual=result.predicted_magnetics,
            **arrays,
            **models,
        )
        write_mesh_vtk(output / "model.vtk", result.mesh, models)
        for label, predicted in (
            ("gravity", result.predicted_gravity),
            ("magnetics", result.predicted_magnetics),
        ):
            prefix = "gravity" if label == "gravity" else "magnetic"
            observed = arrays[prefix + "_data"]
            regional = arrays["regional_" + label]
            np.savetxt(
                output / (label + ".csv"),
                np.column_stack(
                    [
                        arrays[prefix + "_xyz"],
                        observed,
                        arrays[prefix + "_std"],
                        regional,
                        predicted,
                        regional + predicted,
                        observed - regional - predicted,
                    ]
                ),
                delimiter=",",
                header="x,y,z,observed,sigma,regional,predicted_residual,predicted_total,residual",
                comments="",
            )
        manifest.update(
            diagnostics=result.diagnostics,
            history=result.history,
            numerical_status="converged"
            if result.diagnostics["outer_convergence_met"]
            else "not_converged",
            artifacts=[
                "model.npz",
                "model.vtk",
                "gravity.csv",
                "magnetics.csv",
                "run.json",
            ],
            model_field_units={
                "density": "g/cm3",
                "susceptibility": "SI",
                "density_contrast_g_cm3": "g/cm3",
                "density_contrast_kg_m3": "kg/m3",
                "susceptibility_si": "SI",
            },
        )
        if require_convergence and not result.diagnostics["outer_convergence_met"]:
            raise RuntimeError(
                "Joint inversion did not meet inner and outer convergence criteria"
            )
        if cancel is not None and cancel():
            raise RuntimeError("Joint inversion export canceled")
        manifest["state"] = "complete"
        save_manifest(path, manifest)
        return result
    except Exception as error:
        manifest.update(state="failed", error=f"{type(error).__name__}: {error}")
        save_manifest(path, manifest)
        raise
