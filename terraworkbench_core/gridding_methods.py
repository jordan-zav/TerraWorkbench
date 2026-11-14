# Shared scientific implementation; independent of the QGIS host.
"""Independent gridders used by TerraWorkbench survey processing.

Minimum curvature defaults to multilevel finite-difference collocation with
Briggs curvature constraints at spatially averaged observations. A direct
variational solver remains available.

The sinc implementation is an interpolator, not a raster filter.  It uses a
separable windowed cardinal sinc kernel on a regular sample lattice.
Scattered GPS samples must be gridded before sinc expansion.
"""

from __future__ import annotations


import numpy as np


def _finite_points(coordinates, values):
    xy = np.asarray(coordinates, dtype=float)
    z = np.asarray(values, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or z.shape != (len(xy),):
        raise ValueError("Expected N x 2 coordinates and N values.")
    valid = np.isfinite(xy).all(axis=1) & np.isfinite(z)
    if valid.sum() < 3:
        raise ValueError("At least three finite observations are required.")
    if not valid.all():
        xy = xy[valid]
        z = z[valid]
    if np.ptp(xy, axis=0).min() <= 0.0:
        raise ValueError("Observations must span a two-dimensional area.")
    return xy, z


def _nearest_axis_indices(values, axis):
    right = np.searchsorted(axis, values, side="left")
    right = np.clip(right, 0, len(axis) - 1)
    left = np.clip(right - 1, 0, len(axis) - 1)
    choose_left = np.abs(values - axis[left]) <= np.abs(values - axis[right])
    return np.where(choose_left, left, right)


def _offnode_constraints(points, values, x_axis, y_axis):
    """Retain one datum per nearest node, but constrain its actual XY location."""
    from scipy.sparse import coo_matrix

    nx, ny = len(x_axis), len(y_axis)
    h = x_axis[1]-x_axis[0]
    ix = _nearest_axis_indices(points[:, 0], x_axis)
    iy = _nearest_axis_indices(points[:, 1], y_axis)
    node = iy*nx+ix
    distance = (points[:,0]-x_axis[ix])**2+(points[:,1]-y_axis[iy])**2
    order = np.lexsort((values, points[:,1], points[:,0], distance, node))
    selected = order[np.r_[True, np.diff(node[order]) != 0]]
    xy = points[selected]
    tx = (xy[:,0]-x_axis[0])/h
    ty = (xy[:,1]-y_axis[0])/h
    if np.any(tx < -1e-6) or np.any(ty < -1e-6) or np.any(tx > nx-1+1e-6) or np.any(ty > ny-1+1e-6):
        raise ValueError("Solver domain does not enclose its observations.")
    # A second-order Taylor expansion about the nearest node includes
    # centred first derivatives, axial second derivatives and the mixed term.
    cx, cy = ix[selected], iy[selected]
    if np.any(cx < 1) or np.any(cy < 1) or np.any(cx >= nx-1) or np.any(cy >= ny-1):
        raise ValueError("Off-node constraints require a one-node domain margin.")
    u, v = tx-cx, ty-cy
    columns = np.column_stack((cy*nx+cx, cy*nx+cx+1, cy*nx+cx-1,
                               (cy+1)*nx+cx, (cy-1)*nx+cx))
    weights = np.column_stack((1-u*u-v*v, (u*u+u)/2, (u*u-u)/2,
                               (v*v+v)/2, (v*v-v)/2))
    columns = np.column_stack((columns, (cy+1)*nx+cx+1, (cy+1)*nx+cx-1,
                               (cy-1)*nx+cx+1, (cy-1)*nx+cx-1))
    weights = np.column_stack((weights, u*v/4, -u*v/4, -u*v/4, u*v/4))
    matrix = coo_matrix((weights.ravel(), (np.repeat(np.arange(len(selected)),9), columns.ravel())), shape=(len(selected),nx*ny)).tocsr()
    matrix.eliminate_zeros()
    return matrix, values[selected]


def _bending_energy(nx, ny, tension):
    """Discrete thin-plate Hessian with variational free edges (no ghosts)."""
    from scipy.sparse import diags, eye, kron

    dx = diags([-np.ones(nx-1), np.ones(nx-1)], [0,1], shape=(nx-1,nx))
    dy = diags([-np.ones(ny-1), np.ones(ny-1)], [0,1], shape=(ny-1,ny))
    dxx = diags([np.ones(nx-2), -2*np.ones(nx-2), np.ones(nx-2)], [0,1,2], shape=(nx-2,nx))
    dyy = diags([np.ones(ny-2), -2*np.ones(ny-2), np.ones(ny-2)], [0,1,2], shape=(ny-2,ny))
    xx, yy, xy = kron(eye(ny),dxx), kron(dyy,eye(nx)), kron(dy,dx)
    q = (1-tension)*(xx.T@xx + yy.T@yy + 2*(xy.T@xy))
    if tension:
        gx, gy = kron(eye(ny),dx), kron(dy,eye(nx))
        q += tension*(gx.T@gx+gy.T@gy)
    return q.tocsr()


def _linear_ghost_boundary(q, nx, ny):
    """Experimental zero normal curvature on the two outer ghost rings.

    Replace boundary equations only; retain the interior biharmonic stencil.
    This is an independent boundary approximation.
    """
    q = q.tolil()
    for row in range(ny):
        for col in range(nx):
            if min(row, col, ny-1-row, nx-1-col) >= 2:
                continue
            node = row*nx+col
            entries = {}
            if col < 2 or col >= nx-2:
                sign = 1 if col < 2 else -1
                for offset, value in ((0, 1.), (1, -2.), (2, 1.)):
                    other = node+offset*sign
                    entries[other] = entries.get(other, 0.)+value
            if row < 2 or row >= ny-2:
                sign = 1 if row < 2 else -1
                for offset, value in ((0, 1.), (1, -2.), (2, 1.)):
                    other = node+offset*sign*nx
                    entries[other] = entries.get(other, 0.)+value
            q.rows[node] = list(entries)
            q.data[node] = list(entries.values())
    return q.tocsr()


def _solve_surface(points, values, x_axis, y_axis, tension, tolerance,
                   max_iterations, canceled):
    """Solve constrained minimum energy; verify KKT and data residuals."""
    from scipy.sparse import bmat
    from scipy.sparse.linalg import splu

    a, z = _offnode_constraints(points, values, x_axis, y_axis)
    q = _bending_energy(len(x_axis),len(y_axis),tension)
    matrix = bmat([[q,a.T],[a,None]], format="csc")
    rhs = np.r_[np.zeros(q.shape[0]),z]
    if canceled and canceled():
        raise InterruptedError("Processing canceled.")
    try:
        factorization = splu(matrix)
    except RuntimeError as error:
        raise ValueError("Minimum-curvature constraints are singular; adjust cell size or input sampling.") from error
    solution = factorization.solve(rhs)
    converged = False
    for iteration in range(max_iterations):
        if canceled and canceled():
            raise InterruptedError("Processing canceled.")
        residual = rhs-matrix@solution
        scale = np.asarray(abs(matrix)@abs(solution)).ravel()+abs(rhs)
        backward_error = float(np.max(abs(residual)/np.maximum(scale,1.)))
        data_error = float(np.max(abs(residual[q.shape[0]:])))
        converged = data_error <= tolerance and backward_error <= 1e-10
        if converged or iteration+1 == max_iterations:
            break
        solution += factorization.solve(residual)
    if not np.isfinite(solution).all():
        raise ValueError("Minimum-curvature solution is non-finite.")
    report = {"iterations": iteration+1, "converged": bool(converged),
              "stop_reason": "verified_residual" if converged else "refinement_limit",
              "constraint_count": a.shape[0], "max_constraint_error": data_error,
              "kkt_backward_error": backward_error,
              "pass_percent": float(np.mean(abs(residual[q.shape[0]:]) <= tolerance)*100)}
    return solution[:q.shape[0]].reshape(len(y_axis),len(x_axis)), report


def _prolongate(coarse, coarse_x, coarse_y, x_axis, y_axis):
    """Bilinearly prolongate a coarse grid to a target regular grid."""
    along_x = np.empty((len(coarse_y), len(x_axis)), dtype=float)
    for row in range(len(coarse_y)):
        along_x[row] = np.interp(x_axis, coarse_x, coarse[row])
    result = np.empty((len(y_axis), len(x_axis)), dtype=float)
    for column in range(len(x_axis)):
        result[:, column] = np.interp(y_axis, coarse_y, along_x[:, column])
    return result


def _nearest_observations(points, values, x_axis, y_axis, canceled=None):
    """Select the same lexicographic winner per node using bounded sort blocks."""
    nx = len(x_axis)
    winners = np.full(nx*len(y_axis), -1, dtype=np.intp)
    best = np.full(winners.size, np.inf)
    for start in range(0, len(points), 131072):
        if canceled and canceled():
            raise InterruptedError("Processing canceled.")
        xy = points[start:start+131072]
        z = values[start:start+131072]
        ix = _nearest_axis_indices(xy[:, 0], x_axis)
        iy = _nearest_axis_indices(xy[:, 1], y_axis)
        node = iy*nx+ix
        distance = (xy[:, 0]-x_axis[ix])**2+(xy[:, 1]-y_axis[iy])**2
        eligible = np.flatnonzero(distance <= best[node])
        order = eligible[np.lexsort((z[eligible], xy[eligible, 1], xy[eligible, 0],
                                     distance[eligible], node[eligible]))]
        selected = order[np.r_[True, np.diff(node[order]) != 0]] if order.size else order
        anchors = node[selected]
        prior = winners[anchors]
        ties = distance[selected] == best[anchors]
        candidate = selected[ties]
        old = prior[ties]
        if len(old):
            x, y = xy[candidate].T
            px, py = points[old].T
            preferred = (x < px) | ((x == px) & ((y < py) |
                        ((y == py) & (z[candidate] < values[old]))))
            ties[ties] = ~preferred
        anchors, selected = anchors[~ties], selected[~ties]
        best[anchors] = distance[selected]
        winners[anchors] = start+selected
    anchors = np.flatnonzero(winners >= 0)
    return winners[anchors], anchors


def _briggs_constraints(points, values, x_axis, y_axis, tension=0.0, canceled=None):
    """Couple off-node data to the local curvature equation.

    Moment fitting at four neighbouring nodes and the observation estimates
    the Laplacian exactly for quadratic polynomials. Substitute that estimate
    into (1-t)*Laplacian**2(u)-t*Laplacian(u)=0, then normalize by the
    observation coefficient. Two surrounding nodes are needed in each axis.
    Return anchors explicitly; they must not depend on coefficient ordering.
    """
    from scipy.sparse import coo_matrix

    nx, ny = len(x_axis), len(y_axis)
    h = x_axis[1]-x_axis[0]
    selected, anchors = _nearest_observations(points, values, x_axis, y_axis, canceled)
    iy, ix = np.divmod(anchors, nx)
    if np.any(ix < 2) or np.any(iy < 2) or np.any(ix >= nx-2) or np.any(iy >= ny-2):
        raise ValueError("Briggs constraints require a two-node margin.")
    uv = np.column_stack(((points[selected, 0]-x_axis[ix])/h,
                          (points[selected, 1]-y_axis[iy])/h))
    # Only exactly coincident coordinates use a fixed node, with no snap radius.
    exact = np.all(uv == 0, axis=1)
    active = np.flatnonzero(~exact)
    offset = uv[active]
    fixed = np.array([[-1., 1.], [-1., 0.], [0., -1.], [1., -1.]])
    neighbours = fixed[None, :, :]*np.where(offset[:, None, :] >= 0, 1., -1.)
    locations = np.concatenate((neighbours, offset[:, None, :]), axis=1)
    x, y = locations[:, :, 0], locations[:, :, 1]
    moments = np.stack((x, y, x*x, y*y, x*y), axis=1)
    rhs = np.broadcast_to([0., 0., 2., 2., 0.], (len(active), 5))
    weights = np.linalg.solve(moments, rhs[..., None])[..., 0]
    bend = 1.-tension
    coupling = 4.*bend+tension
    denominator = coupling*weights[:, 4]
    rows, cols, data = [], [], []

    def put(r, c, v):
        rows.extend(np.asarray(r).tolist())
        cols.extend(np.asarray(c).tolist())
        data.extend(np.asarray(v).tolist())

    put(np.flatnonzero(exact), anchors[exact], np.ones(exact.sum()))
    central = anchors[active]
    put(active, central, (4.*bend+coupling*weights.sum(axis=1))/denominator)
    stencil = [(1, 0, -4), (-1, 0, -4), (0, 1, -4), (0, -1, -4),
               (1, 1, 2), (-1, 1, 2), (1, -1, 2), (-1, -1, 2),
               (2, 0, 1), (-2, 0, 1), (0, 2, 1), (0, -2, 1)]
    for dx, dy, coefficient in stencil:
        put(active, central+dy*nx+dx, np.full(len(active), bend*coefficient)/denominator)
    for k in range(4):
        neighbour = central+neighbours[:, k, 1].astype(int)*nx+neighbours[:, k, 0].astype(int)
        put(active, neighbour, -coupling*weights[:, k]/denominator)
    a = coo_matrix((data, (rows, cols)), shape=(len(selected), nx*ny)).tocsr()
    a.eliminate_zeros()
    return a, values[selected], anchors


_MULTILEVEL_NODE_LIMIT = 500_000


class MinimumCurvatureNodeLimitError(ValueError):
    """The working domain exceeds the default multilevel budget."""

    def __init__(self, nodes, suggested_cell_size):
        """Record the working node count and the suggested cell size in CRS units."""
        self.nodes = nodes
        self.suggested_cell_size = suggested_cell_size
        super().__init__(
            f"Minimum curvature needs {nodes:,} working nodes; the limit is "
            f"{_MULTILEVEL_NODE_LIMIT:,}. Try a cell size of at least "
            f"{suggested_cell_size:.3g} in CRS units, or reduce the extent."
        )


def minimum_curvature_cell_size(width, height):
    """Suggest a square cell size that fits the multilevel working-node budget.

    Width and height are the combined spans of the requested cell centers and
    observations. Reserve an extra node for alignment to the requested grid.
    """
    if not np.isfinite([width, height]).all() or min(width, height) <= 0:
        raise ValueError("Expected positive finite gridding spans.")
    low = 0.
    high = max(width, height)
    for _ in range(64):
        step = (low + high)/2
        if (np.ceil(width/step)+7)*(np.ceil(height/step)+7) <= _MULTILEVEL_NODE_LIMIT:
            high = step
        else:
            low = step
    # Round upwards to three significant digits so the displayed value is usable.
    magnitude = 10.**(np.floor(np.log10(high))-2)
    return float(np.ceil(high/magnitude)*magnitude)


def _multilevel_surface(points, values, x_axis, y_axis, cell_size, *,
                        coarse_grid, search_radius, weighting_power, tension,
                        tolerance, pass_tolerance, max_iterations,
                        canceled=None, progress=None, boundary_mode="natural",
                        allow_large_grid=False):
    """Collocate the biharmonic equation and off-node Briggs constraints.

    A datum replaces the equation at its nearest node. In particular it does
    not exert the distributed adjoint forces of the variational KKT solver.
    The solver uses coarse-to-fine iteration and limits;
    our stencils, natural boundaries and stopping tests remain independent.
    """
    from scipy.sparse import coo_matrix, tril, triu
    from scipy.sparse.linalg import spsolve_triangular
    from scipy.spatial import cKDTree

    def check_cancel():
        if canceled and canceled():
            raise InterruptedError("Processing canceled.")

    check_cancel()
    h = cell_size
    x0 = min(x_axis[0], x_axis[0]+np.floor((points[:, 0].min()-x_axis[0])/h)*h)
    y0 = min(y_axis[0], y_axis[0]+np.floor((points[:, 1].min()-y_axis[0])/h)*h)
    # Coarse-grid rounding is temporary. Keeping it in the final domain adds
    # an east/north-only extension and changes the converged boundary problem.
    nx = int(np.ceil((max(x_axis[-1], points[:, 0].max())-x0)/h))
    ny = int(np.ceil((max(y_axis[-1], points[:, 1].max())-y0)/h))
    working_nodes = (nx+5)*(ny+5)
    if working_nodes > _MULTILEVEL_NODE_LIMIT and not allow_large_grid:
        raise MinimumCurvatureNodeLimitError(
            working_nodes, minimum_curvature_cell_size(nx*h, ny*h)
        )
    factors = []
    factor = coarse_grid
    while factor >= 1:
        factors.append(factor)
        factor //= 2
    radius = search_radius or 4*coarse_grid*h
    previous = None
    previous_x = previous_y = None
    reports = []
    for level, factor in enumerate(factors):
        check_cancel()
        level_nx = int(np.ceil(nx/factor))*factor
        level_ny = int(np.ceil(ny/factor))*factor
        ax = x0+np.arange(-2*factor, level_nx+2*factor+1, factor)*h
        ay = y0+np.arange(-2*factor, level_ny+2*factor+1, factor)*h
        a, z, anchors = _briggs_constraints(points, values, ax, ay, tension, canceled)
        q = _bending_energy(len(ax), len(ay), tension)
        if boundary_mode == "linear_ghost":
            q = _linear_ghost_boundary(q, len(ax), len(ay))
        free = np.ones(q.shape[0], dtype=bool)
        free[anchors] = False
        qc, ac = q.tocoo(), a.tocoo()
        keep = free[qc.row]
        matrix = coo_matrix((np.r_[qc.data[keep], ac.data],
                            (np.r_[qc.row[keep], anchors[ac.row]],
                             np.r_[qc.col[keep], ac.col])), shape=q.shape).tocsr()
        rhs = np.zeros(q.shape[0])
        rhs[anchors] = z
        diagonal = matrix.diagonal()
        normalized = matrix.multiply((1/diagonal)[:, None]).tocsr()
        lower = tril(normalized, -1, format="csc")
        upper = triu(normalized, 1, format="csr")
        scaled_rhs = rhs/diagonal
        if previous is None:
            tree = cKDTree(points)
            gx, gy = np.meshgrid(ax, ay)
            nodes = np.column_stack((gx.ravel(), gy.ravel()))
            u = np.full(len(nodes), np.mean(values))
            for i, node in enumerate(nodes):
                check_cancel()
                neighbors = tree.query_ball_point(node, radius)
                if not neighbors:
                    continue
                distances = np.linalg.norm(points[neighbors]-node, axis=1)
                exact = distances <= h*1e-10
                if exact.any():
                    u[i] = np.mean(values[np.asarray(neighbors)[exact]])
                else:
                    weights = (distances.min()/distances)**weighting_power
                    u[i] = np.dot(weights, values[neighbors])/weights.sum()
            del tree
        else:
            u = _prolongate(previous, previous_x, previous_y, ax, ay).ravel()
        converged = False
        for iteration in range(max(1, max_iterations//factor)):
            check_cancel()
            updated = spsolve_triangular(lower, scaled_rhs-upper@u, lower=True, unit_diagonal=True)
            if not np.isfinite(updated).all():
                raise ValueError("Minimum-curvature iteration produced non-finite values.")
            change = abs(updated-u)
            u = updated
            data_error = abs(a@u-z)
            equation_error = abs(matrix@u-rhs)/abs(diagonal)
            pass_percent = float(np.mean(change <= tolerance)*100)
            equation_pass = float(np.mean(equation_error <= tolerance)*100)
            data_pass = float(np.mean(data_error <= tolerance)*100)
            converged = min(pass_percent, equation_pass, data_pass) >= pass_tolerance
            if converged:
                break
        reports.append(dict(factor=factor, iterations=iteration+1,
                            converged=bool(converged),
                            stop_reason="verified_residual" if converged else "iteration_limit",
                            pass_percent=pass_percent, equation_pass_percent=equation_pass,
                            data_pass_percent=data_pass, max_change=float(change.max()),
                            max_constraint_error=float(data_error.max()),
                            max_diagonal_scaled_residual=float(equation_error.max()),
                            constraint_count=a.shape[0]))
        previous = u.reshape(len(ay), len(ax))
        previous_x, previous_y = ax, ay
        if progress:
            progress((level+1)/len(factors))
    return _prolongate(previous, ax, ay, x_axis, y_axis), reports, previous.size


class MinimumCurvatureGridder:
    """Independent finite-difference minimum-curvature interpolation.

    Briggs constraints couple off-node observations to curvature. Natural
    discrete energy boundaries and grid-unit
    tension are defined by this solver.
    boundary_mode="linear_ghost" optionally applies experimental zero normal
    curvature at the two outer ghost rings (multilevel, zero tension only).
    Multilevel iteration uses the seed, refinement and pass controls. The
    optional variational solver records the controls it does not use.

    ``blanking_metric='cell_manhattan'`` is a cell-based blanking mode. It rounds each input location
    to the nearest output cell and measures Manhattan distance between cell
    indices.  The regular ``euclidean`` and ``manhattan`` modes retain their
    continuous-coordinate semantics.
    """

    VALID_COARSE = (16, 8, 4, 2, 1)

    def __init__(self, coordinates, values, cell_size, *, blanking_distance=0.0,
                 desample_factor=1, search_radius=0.0, weighting_power=2.0,
                 weighting_slope=0.0, tolerance=0.01258,
                 pass_tolerance=99.0, max_iterations=100, tension=0.0,
                 coarse_grid=16, solver="multilevel", blanking_metric="euclidean",
                 boundary_mode="natural", average_cells=True, allow_large_grid=False):
        self.average_cells = average_cells
        self.allow_large_grid = allow_large_grid
        self.points, self.values = _finite_points(coordinates, values)
        if solver not in ("multilevel", "variational"):
            raise ValueError("Minimum-curvature solver must be multilevel or variational.")
        if boundary_mode not in ("natural", "linear_ghost"):
            raise ValueError("Boundary mode must be natural or linear_ghost.")
        if boundary_mode == "linear_ghost" and (solver != "multilevel" or tension != 0.):
            raise ValueError("linear_ghost boundary requires multilevel solver and zero tension.")
        self.boundary_mode = boundary_mode
        self.solver = solver
        if blanking_metric not in ("euclidean", "manhattan", "cell_manhattan"):
            raise ValueError("Blanking metric must be euclidean, manhattan, or cell_manhattan.")
        if not np.isfinite(cell_size) or cell_size <= 0.0:
            raise ValueError("Cell size must be finite and positive.")
        if blanking_distance < 0.0 or not np.isfinite(blanking_distance):
            raise ValueError("Blanking distance must be finite and non-negative.")
        if int(desample_factor) != desample_factor or desample_factor < 1:
            raise ValueError("Desample factor must be a positive integer.")
        if blanking_metric == "cell_manhattan" and int(desample_factor) != 1:
            raise ValueError("cell_manhattan blanking requires desample_factor=1.")
        if search_radius < 0.0 or not np.isfinite(search_radius):
            raise ValueError("Search radius must be finite and non-negative.")
        if weighting_power <= 0.0 or not np.isfinite(weighting_power):
            raise ValueError("Weighting power must be finite and positive.")
        if weighting_slope != 0.0 or not np.isfinite(weighting_slope):
            raise ValueError("Nonzero minimum-curvature weighting slope is not implemented; use zero.")
        if tolerance <= 0.0 or not np.isfinite(tolerance):
            raise ValueError("Tolerance must be finite and positive.")
        if not 0.0 < pass_tolerance <= 100.0 or not np.isfinite(pass_tolerance):
            raise ValueError("Pass tolerance must be in (0, 100].")
        if int(max_iterations) != max_iterations or max_iterations < 1:
            raise ValueError("Maximum iterations must be a positive integer.")
        if not 0.0 <= tension <= 1.0 or not np.isfinite(tension):
            raise ValueError("Tension must be in [0, 1].")
        if int(coarse_grid) != coarse_grid or coarse_grid not in self.VALID_COARSE:
            raise ValueError("Coarse grid must be one of 16, 8, 4, 2, or 1.")
        self.cell_size = float(cell_size)
        self.blanking_distance = float(blanking_distance)
        self.desample_factor = int(desample_factor)
        self.search_radius = float(search_radius)
        self.weighting_power = float(weighting_power)
        self.weighting_slope = float(weighting_slope)
        self.tolerance = float(tolerance)
        self.pass_tolerance = float(pass_tolerance)
        self.max_iterations = int(max_iterations)
        self.tension = float(tension)
        self.coarse_grid = int(coarse_grid)
        self.blanking_metric = blanking_metric
        self.metadata = {}

    def _desample(self, origin=None):
        if self.desample_factor == 1 and not self.average_cells:
            return self.points, self.values
        spacing = self.cell_size * self.desample_factor
        origin = self.points.min(axis=0) if origin is None else np.asarray(origin)
        indices = np.floor((self.points - origin) / spacing + 0.5).astype(np.int64)
        indices -= indices.min(axis=0)
        width = int(indices[:, 0].max()) + 1
        key = indices[:, 1] * width + indices[:, 0]
        _unique, inverse = np.unique(key, return_inverse=True)
        counts = np.bincount(inverse).astype(float)
        x = np.bincount(inverse, weights=self.points[:, 0]) / counts
        y = np.bincount(inverse, weights=self.points[:, 1]) / counts
        z = np.bincount(inverse, weights=self.values) / counts
        return np.column_stack((x, y)), z

    def grid(self, x_axis, y_axis, canceled=None, progress=None, *, boundary=None):
        """Return a float grid indexed as rows by y and columns by x."""
        x_axis = np.asarray(x_axis, dtype=float)
        y_axis = np.asarray(y_axis, dtype=float)
        if x_axis.ndim != 1 or y_axis.ndim != 1 or len(x_axis) < 2 or len(y_axis) < 2:
            raise ValueError("Grid axes must be one-dimensional with at least two cells.")
        if not np.all(np.diff(x_axis) > 0.0) or not np.all(np.diff(y_axis) > 0.0):
            raise ValueError("Grid axes must be strictly increasing.")
        for axis in (x_axis, y_axis):
            if not np.isfinite(axis).all() or not np.allclose(np.diff(axis), self.cell_size, rtol=1e-7, atol=1e-9):
                raise ValueError("Minimum curvature requires uniform axes at the declared cell size.")
        requested_x, requested_y = x_axis.copy(), y_axis.copy()
        points, values = self._desample((requested_x[0], requested_y[0]))
        trend_origin = points.mean(axis=0)
        trend_scale = np.ptp(points, axis=0).max()
        trend, values = _remove_plane(points, values, trend_origin, trend_scale, canceled)
        if self.solver == "multilevel":
            result, iteration_metadata, working_nodes = _multilevel_surface(
                points, values, x_axis, y_axis, self.cell_size,
                coarse_grid=self.coarse_grid, search_radius=self.search_radius,
                weighting_power=self.weighting_power, tension=self.tension,
                tolerance=self.tolerance, pass_tolerance=self.pass_tolerance,
                max_iterations=self.max_iterations, canceled=canceled, progress=progress,
                boundary_mode=self.boundary_mode, allow_large_grid=self.allow_large_grid)
        else:
            result, iteration_metadata, working_nodes = self._variational_grid(
                points, values, x_axis, y_axis, canceled, progress)
        result += (trend[0] + trend[1]*(x_axis[None, :]-trend_origin[0])/trend_scale
                   + trend[2]*(y_axis[:, None]-trend_origin[1])/trend_scale)
        if not np.isfinite(result).all():
            raise ValueError("Minimum-curvature solve produced non-finite values.")
        _blank_grid(result, x_axis, y_axis, self.points, self.blanking_distance,
                    self.blanking_metric, self.cell_size, boundary, canceled)
        self.metadata = {
            "algorithm": "minimum_curvature_"+self.solver,
            "cell_size": self.cell_size,
            "desample_factor": self.desample_factor,
            "average_cells": self.average_cells,
            "search_radius": self.search_radius,
            "weighting_power": self.weighting_power,
            "weighting_slope": self.weighting_slope,
            "tolerance": self.tolerance,
            "pass_tolerance": self.pass_tolerance,
            "max_iterations": self.max_iterations,
            "tension": self.tension,
            "coarse_grid": self.coarse_grid,
            "legacy_controls_not_used": [] if self.solver == "multilevel" else ["coarse_grid", "search_radius", "weighting_power", "pass_tolerance"],
            "levels": iteration_metadata,
            "input_points": int(len(self.points)),
            "working_points": int(len(points)),
            "working_nodes": int(working_nodes),
            "allow_large_grid": self.allow_large_grid,
            "required_pass_percent": self.pass_tolerance if self.solver == "multilevel" else 100.,
            "desample_origin": [float(requested_x[0]), float(requested_y[0])],
            "proprietary_equivalence": False,
            "converged": bool(iteration_metadata[-1]["converged"]),
            "boundary_mode": self.boundary_mode,
            "boundary": ("experimental zero normal curvature on two outer ghost rings"
                         if self.boundary_mode == "linear_ghost" else
                         "natural variational boundary of discrete Hessian energy"),
            "constraints": ("Briggs curvature constraints at actual observation coordinates"
                            if self.solver == "multilevel" else
                            "second-order Taylor constraints at actual observation coordinates"),
            "solver": "multilevel Gauss-Seidel collocation" if self.solver == "multilevel" else "sparse KKT LU with iterative refinement",
            "blanking_distance": self.blanking_distance,
            "blanking_metric": self.blanking_metric,
        }
        return result

    def _variational_grid(self, points, values, x_axis, y_axis, canceled, progress):
        requested_x, requested_y = x_axis.copy(), y_axis.copy()
        # Include all observations in the solve, then crop. Never clamp external
        # data to edge nodes of a requested output subset.
        h = self.cell_size
        x0 = min(x_axis[0], x_axis[0]+np.floor((self.points[:,0].min()-x_axis[0])/h)*h)
        y0 = min(y_axis[0], y_axis[0]+np.floor((self.points[:,1].min()-y_axis[0])/h)*h)
        x0 -= 2*h
        y0 -= 2*h
        x_axis = x0+np.arange(max(3,int(np.ceil((max(x_axis[-1],self.points[:,0].max())+2*h-x0)/h))+1))*h
        y_axis = y0+np.arange(max(3,int(np.ceil((max(y_axis[-1],self.points[:,1].max())+2*h-y0)/h))+1))*h
        if len(x_axis)*len(y_axis) > 250000:
            raise ValueError("Sparse minimum curvature is limited to 250000 working nodes; increase cell size.")
        current, report = _solve_surface(
            points, values, x_axis, y_axis, self.tension,
            self.tolerance, self.max_iterations, canceled)
        iteration_metadata = [dict(report, factor=1)]
        if progress is not None:
            progress(1.0)
        result = _prolongate(current, x_axis, y_axis, requested_x, requested_y)
        return result, iteration_metadata, current.size


def _remove_plane(points, values, origin, scale, canceled):
    """Fit a normalized affine plane using bounded blocks."""
    gram = np.zeros((3, 3))
    rhs = np.zeros(3)
    residuals = np.empty_like(values)
    for start in range(0, len(points), 131072):
        if canceled and canceled():
            raise InterruptedError("Processing canceled.")
        block = slice(start, start+131072)
        design = np.column_stack((np.ones(len(points[block])), (points[block]-origin)/scale))
        gram += design.T @ design
        rhs += design.T @ values[block]
    if np.linalg.matrix_rank(gram) < 3:
        raise ValueError("Gridding requires non-collinear working points.")
    trend = np.linalg.solve(gram, rhs)
    for start in range(0, len(points), 131072):
        block = slice(start, start+131072)
        residuals[block] = values[block]-trend[0]-((points[block]-origin)/scale) @ trend[1:]
    return trend, residuals


def _blank_grid(result, x_axis, y_axis, points, distance, metric, cell_size,
                boundary, canceled):
    """Mask raster centers in blocks, including polygon holes."""
    if not distance and boundary is None:
        return
    from scipy.spatial import cKDTree

    origin = np.array([x_axis[0], y_axis[0]])
    grid_metric = metric == "cell_manhattan"
    tree = None
    if distance:
        support = np.floor((points-origin)/cell_size + 0.5) if grid_metric else points
        tree = cKDTree(support)
    if boundary is not None:
        from shapely import intersects_xy, prepare
        prepare(boundary)
    nx = len(x_axis)
    for start in range(0, result.size, 65536):
        if canceled and canceled():
            raise InterruptedError("Processing canceled.")
        block = slice(start, start+65536)
        rows, cols = np.divmod(np.arange(start, min(start+65536, result.size)), nx)
        query = np.column_stack((x_axis[cols], y_axis[rows]))
        valid = np.ones(len(query), dtype=bool)
        if boundary is not None:
            valid &= intersects_xy(boundary, query[:, 0], query[:, 1])
        if tree is not None:
            support = np.column_stack((cols, rows)) if grid_metric else query
            radius = distance/cell_size if grid_metric else distance
            d, _ = tree.query(support[valid], p=2 if metric == "euclidean" else 1,
                              distance_upper_bound=np.nextafter(radius, np.inf))
            valid[valid] = d <= radius
        result.flat[block] = np.where(valid, result.flat[block], np.nan)


def _line_groups(line_ids):
    """Group observations by line while preserving acquisition order."""
    labels = np.asarray(line_ids)
    if labels.ndim != 1:
        raise ValueError("Line IDs must be a one-dimensional array.")
    if labels.dtype.kind in "fc" and not np.isfinite(labels).all():
        raise ValueError("Flight-line IDs must be finite.")
    order = np.argsort(labels, kind="stable")
    cuts = np.flatnonzero(labels[order[1:]] != labels[order[:-1]])+1
    return np.split(order, cuts)


def _flight_frame(points, groups):
    vectors = []
    for group in groups:
        if len(group) < 2:
            continue
        centered = points[group]-points[group].mean(axis=0)
        eigenvalues, axes = np.linalg.eigh(centered.T @ centered)
        if eigenvalues[-1] > 0:
            vectors.append((eigenvalues, axes[:, -1]))
    if len(vectors) < 2:
        raise ValueError("At least two flight lines with distinct points are required.")
    directions = np.array([axis for _, axis in vectors])
    _, axes = np.linalg.eigh(directions.T @ directions)
    along = axes[:, -1]
    if (np.any(abs(directions @ along) < np.cos(np.deg2rad(20))) or
            any(eigenvalues[0] > 0.12*eigenvalues[1] for eigenvalues, _ in vectors)):
        raise ValueError("Select roughly parallel flight lines and exclude tie lines.")
    return np.column_stack((along, [-along[1], along[0]]))


def _line_spacing(points, groups, frame):
    offsets = sorted(np.median(points[group] @ frame[:, 1])
                     for group in groups if len(group) > 1)
    spacing = np.diff(offsets)
    spacing = spacing[spacing > 0]
    if not len(spacing):
        raise ValueError("Unable to estimate spacing between distinct flight lines.")
    return float(np.median(spacing))


def suggest_flight_cell_size(coordinates, line_ids, divisor=4):
    """Return median projected flight-line spacing divided by 4 or 5."""
    points = np.asarray(coordinates, dtype=float)
    if (points.ndim != 2 or points.shape[1] != 2 or
            np.shape(line_ids) != (len(points),) or not np.isfinite(points).all()):
        raise ValueError("Expected finite N x 2 coordinates and N line IDs.")
    if divisor not in (4, 5):
        raise ValueError("Flight-line spacing divisor must be 4 or 5.")
    groups = _line_groups(line_ids)
    return _line_spacing(points, groups, _flight_frame(points, groups))/divisor


def _collapse_profile(abscissa, values):
    order = np.argsort(abscissa, kind="stable")
    x = abscissa[order]
    starts = np.r_[0, np.flatnonzero(np.diff(x))+1]
    z = np.add.reduceat(values[order], starts)/np.diff(np.r_[starts, len(x)])
    return x[starts], z


class BidirectionalGridder:
    """Grid approximately parallel profiles in two passes on a flight-aligned grid.

    Linear interpolation follows each flight's projected track. Cross-track
    interpolation is linear or shape-preserving cubic (PCHIP). The resulting
    aligned grid is sampled bilinearly at the requested output centers.
    """

    def __init__(self, coordinates, values, line_ids, *, trend=False,
                 cross_method="linear", blanking_distance=0., max_line_gap=0.,
                 max_sample_gap=0.):
        """Configure flight profiles, cross-line interpolation and support limits."""
        xy = np.asarray(coordinates, dtype=float)
        z = np.asarray(values, dtype=float)
        labels = np.asarray(line_ids)
        if xy.ndim != 2 or xy.shape[1] != 2 or z.shape != (len(xy),) or labels.shape != z.shape:
            raise ValueError("Expected N x 2 coordinates, N values and N line IDs.")
        valid = np.isfinite(xy).all(axis=1) & np.isfinite(z)
        if not valid.all():
            xy, z, labels = xy[valid], z[valid], labels[valid]
        if cross_method not in ("linear", "pchip"):
            raise ValueError("Cross-line interpolation must be linear or pchip.")
        limits = [blanking_distance, max_line_gap, max_sample_gap]
        if not np.isfinite(limits).all() or min(limits) < 0.:
            raise ValueError("Distance controls must be finite and non-negative.")
        self.groups = _line_groups(labels)
        self.frame = _flight_frame(xy, self.groups)
        self.origin = xy.mean(axis=0)
        self.points, self.values = xy, z
        self.line_spacing = _line_spacing(xy, self.groups, self.frame)
        self.trend = trend
        self.cross_method = cross_method
        self.blanking_distance = blanking_distance
        self.max_line_gap = max_line_gap
        self.max_sample_gap = max_sample_gap

    def grid(self, x_axis, y_axis, canceled=None, *, boundary=None):
        """Return rows by ascending y and columns by ascending x, with NaN gaps."""
        from scipy.interpolate import PchipInterpolator
        from scipy.ndimage import map_coordinates

        x_axis, y_axis = np.asarray(x_axis, dtype=float), np.asarray(y_axis, dtype=float)
        if any(axis.ndim != 1 or len(axis) < 2 or not np.isfinite(axis).all()
               for axis in (x_axis, y_axis)):
            raise ValueError("Grid axes must have at least two finite coordinates.")
        step = x_axis[1]-x_axis[0]
        if step <= 0 or any(not np.allclose(np.diff(axis), step, rtol=1e-7, atol=1e-9)
                            for axis in (x_axis, y_axis)):
            raise ValueError("Bidirectional gridding requires uniform square cells.")
        corners = np.array([[x, y] for x in x_axis[[0, -1]] for y in y_axis[[0, -1]]])
        flight_corners = (corners-self.origin) @ self.frame
        start = flight_corners.min(axis=0)
        sizes = np.ceil((flight_corners.max(axis=0)-start)/step).astype(int)+1
        if np.prod(sizes, dtype=float) > 10_000_000 or sizes[0]*len(self.groups) > 10_000_000:
            raise ValueError("Bidirectional working grid is too large; increase cell size.")
        u, v = (start[i]+step*np.arange(sizes[i]) for i in range(2))
        def check_cancel():
            if canceled and canceled():
                raise InterruptedError("Processing canceled.")

        values = self.values
        scale = np.ptp(self.points, axis=0).max()
        if self.trend:
            plane, values = _remove_plane(self.points, values, self.origin, scale, canceled)

        epsilon = step*1e-8
        offsets = np.full((len(self.groups), len(u)), np.nan)
        profiles = np.full_like(offsets, np.nan)
        for i, group in enumerate(self.groups):
            check_cancel()
            xy = (self.points[group]-self.origin) @ self.frame
            order = np.argsort(xy[:, 0], kind="stable")
            ordered_u = xy[order, 0]
            starts = np.r_[0, np.flatnonzero(np.diff(ordered_u))+1]
            axis = ordered_u[starts]
            if len(axis) < 2:
                continue
            counts = np.diff(np.r_[starts, len(order)])
            offset = np.add.reduceat(xy[order, 1], starts)/counts
            z = np.add.reduceat(values[group[order]], starts)/counts
            supported = (u >= axis[0]-epsilon) & (u <= axis[-1]+epsilon)
            if self.max_sample_gap:
                right = np.clip(np.searchsorted(axis, u), 1, len(axis)-1)
                left = right-1
                supported &= ((axis[right]-axis[left] <= self.max_sample_gap) |
                              (abs(u-axis[right]) <= epsilon) | (abs(u-axis[left]) <= epsilon))
            offsets[i, supported] = np.interp(u[supported], axis, offset)
            profiles[i, supported] = np.interp(u[supported], axis, z)

        aligned = np.full((len(v), len(u)), np.nan)
        for i, column in enumerate(profiles.T):
            check_cancel()
            valid = np.isfinite(column)
            if not valid.any():
                continue
            axis, z = _collapse_profile(offsets[valid, i], column[valid])
            splits = np.flatnonzero(np.diff(axis) > self.max_line_gap)+1 if self.max_line_gap else []
            for indices in np.split(np.arange(len(axis)), splits):
                if len(indices) < 2:
                    continue
                x = axis[indices]
                targets = (v >= x[0]-epsilon) & (v <= x[-1]+epsilon)
                query = np.clip(v[targets], x[0], x[-1])
                aligned[targets, i] = (np.interp(query, x, z[indices]) if self.cross_method == "linear"
                                       else PchipInterpolator(x, z[indices])(query))

        # Use a support raster to avoid interpolating across the footprint edge.
        supported = np.isfinite(aligned)
        aligned[~supported] = 0.
        result = np.empty((len(y_axis), len(x_axis)))
        for start_index in range(0, result.size, 65536):
            check_cancel()
            block = slice(start_index, start_index+65536)
            rows, cols = np.divmod(np.arange(start_index, min(start_index+65536, result.size)), len(x_axis))
            points = np.column_stack((x_axis[cols], y_axis[rows]))-self.origin
            indices = np.clip(((points @ self.frame-start)/step).T, 0, (sizes-1)[:, None])
            coordinates = indices[::-1]
            data = map_coordinates(aligned, coordinates, order=1, prefilter=False)
            weight = map_coordinates(supported, coordinates, order=1, prefilter=False, output=float)
            if self.trend:
                data += plane[0]+points @ plane[1:]/scale
            result.flat[block] = np.where(weight >= 1.-1e-8, data, np.nan)
        _blank_grid(result, x_axis, y_axis, self.points, self.blanking_distance,
                    "euclidean", step, boundary, canceled)
        return result


class SincGridder:
    """Separable Lanczos-windowed cardinal sinc on a regular sample lattice.

    sinc(t) = sin(pi*t)/(pi*t); spacing is the ORIGINAL sample interval,
    independent of the output cell size. Missing samples are not synthesized.
    Coordinates can be offset but the lattice is axis-aligned. This is an
    independently specified windowed interpolator, not Geoplot parity.
    """

    def __init__(self, coordinates, values, spacing, *, radius=4,
                 blanking_distance=0.0, fallback="nodata"):
        from scipy.spatial import cKDTree

        self.points, self.values = _finite_points(coordinates, values)
        spacing = np.broadcast_to(np.asarray(spacing, dtype=float), (2,)).copy()
        if not np.isfinite(spacing).all() or np.any(spacing <= 0):
            raise ValueError("Sinc spacing must contain two positive finite values.")
        if not np.isfinite(radius) or int(radius) != radius or not 1 <= radius <= 32:
            raise ValueError("Sinc radius must be an integer from 1 to 32.")
        if not np.isfinite(blanking_distance) or blanking_distance < 0:
            raise ValueError("Sinc blanking distance must be finite and non-negative.")
        if fallback != "nodata":
            raise ValueError("Sinc requires nodata fallback; nearest would change the interpolation.")
        self.spacing = spacing
        self.radius = int(radius)
        self.blanking_distance = float(blanking_distance)
        self.origin = self.points.min(axis=0)
        lattice = (self.points - self.origin) / spacing
        if not np.allclose(lattice, np.rint(lattice), rtol=0, atol=1e-6):
            raise ValueError("Sinc requires a regular sample lattice at the declared X/Y spacing; grid irregular GPS points first.")
        self.indices = np.rint(lattice).astype(np.int64)
        self.shape = self.indices.max(axis=0) + 1
        keys = self.indices[:, 1] * self.shape[0] + self.indices[:, 0]
        unique, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
        self.keys = unique
        self.samples = np.bincount(inverse, weights=self.values) / counts
        self._tree = cKDTree(self.points)
        self.metadata = {"algorithm": "regular_lattice_windowed_sinc",
                         "kernel": "sinc(t)*sinc(t/radius), separable Lanczos",
                         "spacing_x": float(spacing[0]), "spacing_y": float(spacing[1]),
                         "radius": self.radius, "missing_policy": "strict support; no extrapolation",
                         "fallback": "nodata", "geoplot_equivalence": False}

    def evaluate(self, query, canceled=None):
        query = np.asarray(query, dtype=float)
        if query.ndim != 2 or query.shape[1] != 2 or not np.isfinite(query).all():
            raise ValueError("Sinc query must contain finite N x 2 coordinates.")
        result = np.full(len(query), np.nan)
        for start in range(0, len(query), 512):
            if canceled is not None and canceled():
                raise InterruptedError("Processing canceled.")
            q = query[start:start + 512]
            t = (q - self.origin) / self.spacing
            numerator = np.zeros(len(q))
            denominator = np.zeros(len(q))
            missing = np.any((t < -1e-6) | (t > self.shape - 1 + 1e-6), axis=1)
            base = np.floor(t).astype(np.int64)
            for oy in range(1-self.radius, self.radius+1):
                for ox in range(1-self.radius, self.radius+1):
                    ix, iy = base[:, 0]+ox, base[:, 1]+oy
                    dx, dy = t[:, 0]-ix, t[:, 1]-iy
                    w = np.sinc(dx)*np.sinc(dx/self.radius)*np.sinc(dy)*np.sinc(dy/self.radius)
                    active = (np.abs(w) > 1e-12) & (ix >= 0) & (iy >= 0) & (ix < self.shape[0]) & (iy < self.shape[1])
                    keys = iy*self.shape[0]+ix
                    pos = np.searchsorted(self.keys, keys)
                    safe = np.minimum(pos, len(self.keys)-1)
                    found = (pos < len(self.keys)) & (self.keys[safe] == keys)
                    missing |= active & ~found
                    use = active & found
                    numerator[use] += w[use]*self.samples[safe[use]]
                    denominator[use] += w[use]
            valid = ~missing & (np.abs(denominator) > 1e-10)
            block = np.full(len(q), np.nan)
            block[valid] = numerator[valid]/denominator[valid]
            if self.blanking_distance > 0:
                distance, _ = self._tree.query(q)
                block[distance > self.blanking_distance] = np.nan
            result[start:start+len(q)] = block
        return result

    def grid(self, x_axis, y_axis, canceled=None, progress=None):
        xx, yy = np.meshgrid(x_axis, y_axis)
        result = self.evaluate(np.column_stack((xx.ravel(), yy.ravel())), canceled)
        if progress is not None:
            progress(1.0)
        return result.reshape(xx.shape)
