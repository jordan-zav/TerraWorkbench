"""Independent gridders used by TerraWorkbench survey processing.

Minimum curvature defaults to multilevel finite-difference collocation with
second-order Taylor constraints at spatially averaged observations. A direct
variational solver remains available for explicit comparisons. Neither solver
is a certified replica of RANGRID.

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


def _multilevel_surface(points, values, x_axis, y_axis, cell_size, *,
                        coarse_grid, search_radius, weighting_power, tension,
                        tolerance, pass_tolerance, max_iterations,
                        canceled=None, progress=None):
    """Collocate the biharmonic equation and off-node Taylor constraints.

    A datum replaces the equation at its nearest node. In particular it does
    not exert the distributed adjoint forces of the variational KKT solver.
    The public RANGRID workflow motivates coarse-to-fine iteration and limits;
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
    nx = int(np.ceil((max(x_axis[-1], points[:, 0].max())-x0)/(h*coarse_grid)))*coarse_grid
    ny = int(np.ceil((max(y_axis[-1], points[:, 1].max())-y0)/(h*coarse_grid)))*coarse_grid
    if (nx+3)*(ny+3) > 250000:
        raise ValueError("Minimum curvature is limited to 250000 working nodes; increase cell size.")
    factors = []
    factor = coarse_grid
    while factor >= 1:
        factors.append(factor)
        factor //= 2
    tree = cKDTree(points)
    radius = search_radius or 4*coarse_grid*h
    previous = None
    previous_x = previous_y = None
    reports = []
    for level, factor in enumerate(factors):
        check_cancel()
        ax = x0+np.arange(-factor, nx+factor+1, factor)*h
        ay = y0+np.arange(-factor, ny+factor+1, factor)*h
        a, z = _offnode_constraints(points, values, ax, ay)
        q = _bending_energy(len(ax), len(ay), tension)
        # Taylor's central coefficient is >= 1/2 and larger than all others.
        anchors = np.asarray(a.argmax(axis=1)).ravel()
        free = np.ones(q.shape[0], dtype=bool)
        free[anchors] = False
        qc, ac = q.tocoo(), a.tocoo()
        keep = free[qc.row]
        matrix = coo_matrix((np.r_[qc.data[keep], ac.data],
                            (np.r_[qc.row[keep], anchors[ac.row]],
                             np.r_[qc.col[keep], ac.col])), shape=q.shape).tocsr()
        rhs = np.zeros(q.shape[0])
        rhs[anchors] = z
        lower, upper = tril(matrix, format="csc"), triu(matrix, 1, format="csr")
        if previous is None:
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
        else:
            u = _prolongate(previous, previous_x, previous_y, ax, ay).ravel()
        converged = False
        for iteration in range(max(1, max_iterations//factor)):
            check_cancel()
            updated = spsolve_triangular(lower, rhs-upper@u, lower=True)
            if not np.isfinite(updated).all():
                raise ValueError("Minimum-curvature iteration produced non-finite values.")
            change = abs(updated-u)
            u = updated
            data_error = abs(a@u-z)
            equation_error = abs(matrix@u-rhs)/abs(matrix.diagonal())
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

    Taylor interpolation is exact for quadratic surfaces but is approximate
    for general fields. Natural discrete energy boundaries and grid-unit
    tension are independently defined, not certified RANGRID equivalents.
    Multilevel iteration uses the seed, refinement and pass controls. The
    optional variational solver records the controls it does not use.
    """

    VALID_COARSE = (16, 8, 4, 2, 1)

    def __init__(self, coordinates, values, cell_size, *, blanking_distance=0.0,
                 desample_factor=1, search_radius=0.0, weighting_power=2.0,
                 weighting_slope=0.0, tolerance=0.01258,
                 pass_tolerance=99.0, max_iterations=100, tension=0.0,
                 coarse_grid=16, solver="multilevel"):
        self.points, self.values = _finite_points(coordinates, values)
        if solver not in ("multilevel", "variational"):
            raise ValueError("Minimum-curvature solver must be multilevel or variational.")
        self.solver = solver
        if not np.isfinite(cell_size) or cell_size <= 0.0:
            raise ValueError("Cell size must be finite and positive.")
        if blanking_distance < 0.0 or not np.isfinite(blanking_distance):
            raise ValueError("Blanking distance must be finite and non-negative.")
        if int(desample_factor) != desample_factor or desample_factor < 1:
            raise ValueError("Desample factor must be a positive integer.")
        if search_radius < 0.0 or not np.isfinite(search_radius):
            raise ValueError("Search radius must be finite and non-negative.")
        if weighting_power <= 0.0 or not np.isfinite(weighting_power):
            raise ValueError("Weighting power must be finite and positive.")
        if weighting_slope != 0.0 or not np.isfinite(weighting_slope):
            raise ValueError("Nonzero RANGRID weighting slope is not implemented; use zero.")
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
        self.metadata = {}

    def _desample(self, origin=None):
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

    def grid(self, x_axis, y_axis, canceled=None, progress=None):
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
        design = np.column_stack((np.ones(len(points)), (points-trend_origin)/trend_scale))
        if np.linalg.matrix_rank(design) < 3:
            raise ValueError("Minimum curvature requires non-collinear working points.")
        trend = np.linalg.lstsq(design, values, rcond=None)[0]
        values = values - design @ trend
        if self.solver == "multilevel":
            result, iteration_metadata, working_nodes = _multilevel_surface(
                points, values, x_axis, y_axis, self.cell_size,
                coarse_grid=self.coarse_grid, search_radius=self.search_radius,
                weighting_power=self.weighting_power, tension=self.tension,
                tolerance=self.tolerance, pass_tolerance=self.pass_tolerance,
                max_iterations=self.max_iterations, canceled=canceled, progress=progress)
        else:
            result, iteration_metadata, working_nodes = self._variational_grid(
                points, values, x_axis, y_axis, canceled, progress)
        gx, gy = np.meshgrid(x_axis, y_axis)
        result += trend[0] + trend[1]*(gx-trend_origin[0])/trend_scale + trend[2]*(gy-trend_origin[1])/trend_scale
        if not np.isfinite(result).all():
            raise ValueError("Minimum-curvature solve produced non-finite values.")
        if self.blanking_distance > 0.0:
            from scipy.spatial import cKDTree

            distances, _ = cKDTree(self.points).query(
                np.column_stack((gx.ravel(), gy.ravel())), k=1
            )
            result.ravel()[distances > self.blanking_distance] = np.nan
        self.metadata = {
            "algorithm": "minimum_curvature_"+self.solver,
            "cell_size": self.cell_size,
            "desample_factor": self.desample_factor,
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
            "required_pass_percent": self.pass_tolerance if self.solver == "multilevel" else 100.,
            "desample_origin": [float(requested_x[0]), float(requested_y[0])],
            "proprietary_equivalence": False,
            "converged": bool(iteration_metadata[-1]["converged"]),
            "boundary": "natural variational boundary of discrete Hessian energy",
            "constraints": "second-order Taylor constraints at actual observation coordinates",
            "solver": "multilevel Gauss-Seidel collocation" if self.solver == "multilevel" else "sparse KKT LU with iterative refinement",
            "blanking_distance": self.blanking_distance,
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
