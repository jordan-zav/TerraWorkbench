"""Regenerate synthetic prior references in a separate, pinned historical SDK.

Requires SimPEG 0.15.0 and Discretize 0.7.0. Never run this in the current Core
runtime or install the old stack over it. No survey data is used or downloaded.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert version("SimPEG") == "0.15.0" and version("discretize") == "0.7.0", (
        "Use the isolated historical reference environment"
    )
    import numpy as np
    from discretize import TensorMesh, TreeMesh
    from discretize.utils import refine_tree_xyz
    from SimPEG import maps, regularization
    from SimPEG.regularization import (
        sparse as sparse_module,
        regularization_mesh as mesh_module,
    )

    args.output.mkdir(parents=True, exist_ok=False)
    for name in ("uniform", "nonuniform", "tree"):
        if name == "uniform":
            mesh = TensorMesh(
                [[100.0] * 3, [100.0] * 3, [40.0] * 3], x0=[-150.0, -150.0, -120.0]
            )
        elif name == "nonuniform":
            mesh = TensorMesh(
                [[100.0, 200.0, 400.0], [100.0, 200.0, 400.0], [40.0, 80.0, 160.0]],
                x0=[-350.0, -350.0, -280.0],
            )
        else:
            mesh = TreeMesh(
                [[(100.0, 8)], [(100.0, 8)], [(40.0, 8)]], x0=[-400.0, -400.0, -320.0]
            )
            mesh = refine_tree_xyz(
                mesh,
                np.array([[0.0, 0.0, -80.0]]),
                octree_levels=[1, 1],
                method="radial",
                finalize=True,
            )
            mesh.write_UBC(str(args.output / "tree.msh"))
        xyz, vol = mesh.cell_centers, mesh.cell_volumes
        full_model = (
            0.02
            + 0.003 * np.sin(xyz[:, 0] / 300.0)
            + 0.002 * np.cos(xyz[:, 1] / 400.0)
            + 0.002 * xyz[:, 2] / 300.0
        )
        full_reference = 0.005 + 0.001 * np.cos(xyz[:, 1] / 500.0)
        full_sensitivity = (
            vol
            / (np.sum((xyz - np.array([0.0, 0.0, 200.0])) ** 2, axis=1) + 1e6) ** 1.5
        )
        for case in ("l2", "l1_active", "mixed_active"):
            active = (
                np.ones(mesh.nC, bool)
                if case == "l2"
                else xyz[:, 2] < np.quantile(xyz[:, 2], 0.9)
            )
            model, reference, sensitivity = (
                full_model[active],
                full_reference[active],
                full_sensitivity[active],
            )
            weights = sensitivity / sensitivity.max()
            reg = regularization.Sparse(
                mesh,
                indActive=active,
                mapping=maps.IdentityMap(nP=int(active.sum())),
                gradientType="total",
                alpha_s=1.0,
                alpha_x=1.0,
                alpha_y=1.0,
                alpha_z=1.0,
            )
            reg.norms = (
                np.array([[0.0, 1.0, 1.5, 2.0]])
                if case == "mixed_active"
                else np.full((1, 4), 2.0 if case == "l2" else 1.0)
            )
            reg.mref, reg.model, reg.cell_weights = reference, model, weights
            if case != "l2":
                reg.eps_p = reg.eps_q = 0.01
            for term in reg.objfcts:
                term.cell_weights = weights
            arrays = dict(
                xyz=xyz,
                vol=vol,
                model=model,
                reference=reference,
                sensitivity=sensitivity,
                hx=mesh.h[0],
                hy=mesh.h[1],
                hz=mesh.h[2],
                origin=mesh.x0,
            )
            if case != "l2":
                arrays["active"] = active
            for axis, term in zip("sxyz", reg.objfcts):
                arrays["H_" + axis] = term.deriv2(model).toarray()
                arrays["gradient_" + axis] = term.deriv(model)
                arrays["phi_" + axis] = np.asarray(term(model))
            np.savez_compressed(args.output / f"{name}_{case}.npz", **arrays)
    for mesh_file in args.output.glob("*.msh"):
        mesh_file.write_text(
            "\n".join(line.rstrip() for line in mesh_file.read_text().splitlines())
            + "\n"
        )
    files = {
        p.name: hashlib.sha256(
            p.read_bytes().replace(b"\r\n", b"\n")
            if p.suffix == ".msh"
            else p.read_bytes()
        ).hexdigest()
        for p in sorted(args.output.iterdir())
    }
    sources = {}
    for module in (sparse_module, mesh_module):
        path = Path(module.__file__)
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = dict(
        hash_convention="LF-normalized text for .msh; unchanged binary bytes for .npz",
        scope="Authored deterministic synthetic grids; no real survey or geological model",
        versions={
            name: version(name) for name in ("SimPEG", "discretize", "numpy", "scipy")
        },
        source_sha256=sources,
        files_sha256=files,
    )
    (args.output / "manifest.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(dict(output=str(args.output), files=len(files))))


if __name__ == "__main__":
    main()
