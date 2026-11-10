"""Normalized cell-difference prior, with the SimPEG 0.15 weight convention.

The modern physical-gradient prior remains separate. This is a mathematical
compatibility definition, not a claim of identical IRLS/optimizer trajectories.

Definition reference: SimPEG 0.15.0 regularization/sparse.py and
regularization/regularization_mesh.py (MIT, SimPEG developers). The public
Discretize stencils are projected onto active cells/faces here; no legacy SDK
or private survey is required at runtime. Core allocation guards apply first.
"""

import numpy as np
from scipy import sparse


def _cell_difference_lp_weights(field, norms, epsilon, lengths, scaled):
    """Historical frozen-IRLS weight, with face-normalized epsilon if needed."""
    if len(field) == 0:
        return np.ones(0)
    norms = np.broadcast_to(norms, field.shape)
    maximum = float(np.max(np.abs(field)))
    eta = np.ones_like(field)
    if scaled:
        peak = np.full_like(field, maximum)
        small = norms < 1.0
        peak[small] = epsilon / np.sqrt(1.0 - norms[small])
        max_gradient = peak / (peak**2 + (epsilon * lengths) ** 2) ** (
            1.0 - norms / 2.0
        )
        np.divide(maximum, max_gradient, out=eta, where=max_gradient != 0.0)
    return eta / (field**2 + (epsilon * lengths) ** 2) ** (1.0 - norms / 2.0)


def _legacy_geometry(mesh, active):
    from discretize import TreeMesh

    tree = isinstance(mesh, TreeMesh)
    operators = {}
    for index, axis in enumerate("xyz"[: mesh.dim]):
        raw = getattr(mesh, "stencil_cell_gradient_" + axis).tocsr()
        if tree:
            average_full = getattr(mesh, "average_cell_to_total_face_" + axis)().tocsr()
            keep = np.asarray(average_full @ active.astype(float)).ravel() >= 1.0
        else:
            face_to_cell = getattr(mesh, "average_face_" + axis + "_to_cell").tocsr()
            keep = np.asarray(face_to_cell.T @ active.astype(float)).ravel() >= 1.0
            offset = sum(
                getattr(mesh, "n_faces_" + direction) for direction in "xyz"[:index]
            )
            count = getattr(mesh, "n_faces_" + axis)
            average_full = mesh.average_cell_to_face[offset : offset + count].tocsr()
        if raw.shape[0] != len(keep):
            raise ValueError("Unsupported discretize face-stencil convention")
        average = average_full[keep][:, active].tocsr()
        difference = raw[keep][:, active].tocsr()
        if tree:
            total = np.asarray(average.T.sum(axis=1)).ravel()
            inverse = np.divide(1.0, total, out=np.zeros_like(total), where=total > 0)
            back = (sparse.diags(inverse) @ average.T).tocsr()
        else:
            back = face_to_cell[active][:, keep].tocsr()
        widths = np.asarray(average @ mesh.h_gridded[active, index]).ravel()
        lengths = widths.min() / widths if len(widths) else widths
        operators[axis] = dict(
            average=average,
            back=back,
            raw=difference,
            gradient=(sparse.diags(lengths) @ difference).tocsr(),
            lengths=lengths,
        )
    return operators


def build_cell_difference_prior(
    mesh, active, reference, norms, alphas, reference_in_smooth=False
):
    """Build a scalar prior with dimensionless cell-stencil coefficients.

    Sensitivity weights replace volume weights, as in the historical Sparse
    convention. Face weights average cell-weight PRODUCTS before multiplying
    IRLS face weights. This differs from multiplying separately averaged
    volume/sensitivity arrays on an adaptive mesh. The complete objective is
    twice the historical half-quadratic objective, consistent with current
    SimPEG's data-misfit normalization. L2 and frozen L1 derivatives are checked
    against independently generated historical-library snapshots.
    """
    from discretize import TensorMesh, TreeMesh
    from simpeg import regularization, directives, maps
    from simpeg.regularization import RegularizationMesh

    if not isinstance(mesh, (TensorMesh, TreeMesh)) or mesh.dim != 3:
        raise ValueError("Cell-difference priors require a 3D TensorMesh or TreeMesh")

    class CellDifferenceSmallness(regularization.SparseSmallness):
        def get_lp_weights(self, field):
            return _cell_difference_lp_weights(
                field, self.norm, self.irls_threshold, 1.0, self.irls_scaled
            )

    class CellDifferenceMesh(RegularizationMesh):
        def __init__(self, *args, **kwargs):
            self._legacy = None
            super().__init__(*args, **kwargs)

        @property
        def operators(self):
            if self._legacy is None:
                self._legacy = _legacy_geometry(self.mesh, self.active_cells)
            return self._legacy

        @property
        def base_length(self):
            return 1.0

        @property
        def nFx(self):
            return self.operators["x"]["raw"].shape[0]

        @property
        def nFy(self):
            return self.operators["y"]["raw"].shape[0]

        @property
        def nFz(self):
            return self.operators["z"]["raw"].shape[0]

        @property
        def aveCC2Fx(self):
            return self.operators["x"]["average"]

        @property
        def aveCC2Fy(self):
            return self.operators["y"]["average"]

        @property
        def aveCC2Fz(self):
            return self.operators["z"]["average"]

        @property
        def aveFx2CC(self):
            return self.operators["x"]["back"]

        @property
        def aveFy2CC(self):
            return self.operators["y"]["back"]

        @property
        def aveFz2CC(self):
            return self.operators["z"]["back"]

    class CellDifferenceSmoothness(regularization.SparseSmoothness):
        @property
        def cell_gradient(self):
            return self.regularization_mesh.operators[self.orientation]["gradient"]

        @property
        def _legacy_n_faces(self):
            return self.cell_gradient.shape[0]

        @property
        def W(self):
            if getattr(self, "_W", None) is None:
                cell = np.ones(self.regularization_mesh.nC)
                face = np.ones(self._legacy_n_faces)
                for key, values in self._weights.items():
                    if (
                        key == "irls"
                        or values.shape == (self._legacy_n_faces,)
                        and values.shape != (self.regularization_mesh.nC,)
                    ):
                        face *= values
                    else:
                        cell *= values
                weight = (
                    self.regularization_mesh.operators[self.orientation]["average"]
                    @ cell
                ) * face
                self._W = sparse.diags(np.sqrt(weight), format="csr")
            return self._W

        def get_lp_weights(self, f_m):
            lengths = self.regularization_mesh.operators[self.orientation]["lengths"]
            return _cell_difference_lp_weights(
                f_m, self.norm, self.irls_threshold, lengths, self.irls_scaled
            )

        def update_weights(self, m):
            if self.gradient_type == "total" and self.parent is not None:
                field = np.zeros(self.regularization_mesh.nC)
                for term in self.parent.objfcts:
                    if isinstance(term, CellDifferenceSmoothness):
                        local = term.mapping * (
                            m - term.reference_model
                            if term.reference_model_in_smooth
                            else m
                        )
                        op = self.regularization_mesh.operators[term.orientation]
                        field += np.abs(op["back"] @ (op["raw"] @ local))
                field = (
                    self.regularization_mesh.operators[self.orientation]["average"]
                    @ field
                )
            else:
                field = self.f_m(m)
            self.set_weights(irls=self.get_lp_weights(field))

    regmesh = CellDifferenceMesh(mesh, active_cells=active)
    terms = [CellDifferenceSmallness(regmesh)]
    terms.extend(
        CellDifferenceSmoothness(regmesh, orientation=axis)
        for axis in "xyz"[: mesh.dim]
    )
    for term in terms:
        term.remove_weights("volume")
    reg = regularization.Sparse(
        regmesh,
        objfcts=terms,
        reference_model=reference,
        mapping=maps.IdentityMap(nP=int(np.count_nonzero(active))),
        norms=norms,
        gradient_type="total",
        alpha_s=float(alphas[0]),
        alpha_x=float(alphas[1]),
        alpha_y=float(alphas[2]),
        alpha_z=float(alphas[3]),
    )
    reg.reference_model_in_smooth = bool(reference_in_smooth)

    class CellSensitivity(directives.UpdateSensitivityWeights):
        def update(self):
            diagonal = np.zeros_like(self.invProb.model, dtype=float)
            for sim, misfit in zip(self.simulation, self.dmisfit.objfcts):
                diagonal += sim.getJtJdiag(self.invProb.model, W=misfit.W) + 1e-12
            weights = np.sqrt(diagonal)
            if not np.isfinite(weights).all() or not np.max(weights) > 0:
                raise ValueError("Invalid sensitivity weights")
            weights /= np.max(weights)
            for objective in self.reg.objfcts:
                objective.set_weights(sensitivity=objective.mapping * weights)

    return reg, CellSensitivity(every_iteration=False)
