"""Tiled survey gridding and directional crosshatch fusion."""

import math
import numpy as np
from .gridding_methods import MinimumCurvatureGridder
from .basic_processing import circular_median


def grid_survey(
    data,
    x,
    y,
    options,
    *,
    core,
    halo,
    radius,
    check,
    emit,
    canceled=None,
    stage_callback=None,
    tile_cache=None,
):
    cell = options.cell_size
    Gridder = MinimumCurvatureGridder
    median = circular_median
    directional = len(data) == 2 and options.crosshatch_lattice == "directional"

    def plan(points):
        if directional:
            origin = points[:, :2].min(axis=0)
            span = (points[:, :2].max(axis=0) - origin) / cell
            count = np.ceil(span).astype(int) + 1
            axes = [origin[axis] + np.arange(count[axis]) * cell for axis in (0, 1)]
        else:
            axes = [x, y]
        ax, ay = axes
        if len(ax) * len(ay) > 4_000_000:
            raise ValueError(
                "A directional grid exceeds four million nodes; increase cell size."
            )
        full_domain_low = np.minimum(
            [ax[0], ay[0]],
            np.array([ax[0], ay[0]])
            + np.floor((points[:, :2].min(axis=0) - [ax[0], ay[0]]) / cell) * cell,
        )
        full_intervals = np.ceil(
            (np.maximum([ax[-1], ay[-1]], points[:, :2].max(axis=0)) - full_domain_low)
            / cell
        ).astype(int)
        full_fits = int(np.prod(full_intervals + 5)) <= 250_000
        auto_full = (
            directional and max(len(ax), len(ay)) <= options.tile_cells and full_fits
        )

        def partitions(size):
            count = int(math.ceil(size / core))
            bounds = np.rint(np.linspace(0, size, count + 1)).astype(int)
            return list(zip(bounds[:-1].tolist(), bounds[1:].tolist()))

        tiles = (
            [(0, len(ay), 0, len(ax))]
            if auto_full
            else [
                (r0, r1, c0, c1)
                for r0, r1 in partitions(len(ay))
                for c0, c1 in partitions(len(ax))
            ]
        )
        return dict(x=ax, y=ay, tiles=tiles, auto_full=auto_full)

    plans = [plan(points) for points in data]
    total = sum(len(p["tiles"]) for p in plans)
    completed = 0
    tile_records = []

    def grid_direction(points, direction, plan):
        nonlocal completed
        x, y = plan["x"], plan["y"]
        nx, ny = len(x), len(y)
        low = np.array([x[0], y[0]])
        tiles = plan["tiles"]
        surface = np.full((ny, nx), np.nan)
        before_background = (
            np.full((ny, nx), np.nan) if stage_callback is not None else None
        )
        support_tree = None
        if options.blanking > 0:
            from scipy.spatial import cKDTree

            support_points = (
                np.floor((points[:, :2] - low) / cell + 0.5)
                if options.blanking_metric == "cell_manhattan"
                else points[:, :2]
            )
            support_tree = cKDTree(support_points)
        for tile_id, (r0, r1, c0, c1) in enumerate(tiles):
            check()
            wr0, wr1 = max(0, r0 - halo), min(ny, r1 + halo)
            wc0, wc1 = max(0, c0 - halo), min(nx, c1 + halo)
            # All tiles share exactly the same global node lattice.
            if wr1 - wr0 < 2:
                wr0 = max(0, wr1 - 2)
            if wc1 - wc0 < 2:
                wc0 = max(0, wc1 - 2)
            tx, ty = x[wc0:wc1], y[wr0:wr1]
            selection = (
                (points[:, 0] >= tx[0] - cell / 2)
                & (points[:, 0] <= tx[-1] + cell / 2)
                & (points[:, 1] >= ty[0] - cell / 2)
                & (points[:, 1] <= ty[-1] + cell / 2)
            )
            selected = points[selection]
            if support_tree is not None:
                qx, qy = np.meshgrid(x[c0:c1], y[r0:r1])
                query = np.column_stack((qx.ravel(), qy.ravel()))
                if options.blanking_metric == "cell_manhattan":
                    query = np.floor((query - low) / cell + 0.5)
                distances, _ = support_tree.query(
                    query,
                    k=1,
                    p=1
                    if options.blanking_metric in ("cell_manhattan", "manhattan")
                    else 2,
                )
                if options.blanking_metric == "cell_manhattan":
                    distances *= cell
                if not np.any(distances <= options.blanking):
                    tile_records.append(
                        dict(
                            input=direction,
                            tile=tile_id,
                            status="no_support",
                            core=[r0, r1, c0, c1],
                            working=[wr0, wr1, wc0, wc1],
                            input_rows=len(selected),
                            metadata={
                                "converged": None,
                                "algorithm": "support_mask_only",
                            },
                            reason="No core node passes the full-input blanking mask; interpolation skipped.",
                        )
                    )
                    completed += 1
                    emit("tiles", completed / total, input=direction, tile=tile_id)
                    continue
            if len(selected) < 3:
                raise ValueError(
                    "Tile has fewer than three observations; reduce tiling or enlarge halo/search radius."
                )
            retained_low = selected[:, :2].min(axis=0)
            retained_high = selected[:, :2].max(axis=0)
            solver_low = np.minimum(
                [tx[0], ty[0]],
                np.array([tx[0], ty[0]])
                + np.floor((retained_low - [tx[0], ty[0]]) / cell) * cell,
            )
            solver_intervals = np.ceil(
                (np.maximum([tx[-1], ty[-1]], retained_high) - solver_low) / cell
            ).astype(int)
            preflight_nodes = int(np.prod(solver_intervals + 5))
            if preflight_nodes > 250_000:
                raise ValueError(
                    "Selected observation extent exceeds 250k padded solver nodes; reduce tile cells or halo."
                )
            identity = dict(
                direction=direction,
                tile=tile_id,
                working=[wr0, wr1, wc0, wc1],
                x=[float(tx[0]), float(tx[-1]), len(tx)],
                y=[float(ty[0]), float(ty[-1]), len(ty)],
            )
            cached = tile_cache.get(identity) if tile_cache is not None else None
            if cached is None:
                gridder = Gridder(
                    selected[:, :2],
                    selected[:, 2],
                    cell,
                    blanking_distance=options.blanking,
                    blanking_metric=options.blanking_metric,
                    search_radius=options.search_radius,
                    max_iterations=options.max_iterations,
                    tolerance=options.tolerance,
                    pass_tolerance=options.pass_tolerance,
                    boundary_mode="natural",
                )
                raw = gridder.grid(
                    tx,
                    ty,
                    canceled=canceled,
                    progress=lambda f: emit(
                        "gridding",
                        (completed + float(f)) / total,
                        input=direction,
                        tile=tile_id,
                    ),
                )
                metadata = gridder.metadata
                if tile_cache is not None:
                    tile_cache.put(identity, [raw, metadata])
            else:
                raw, metadata = cached
            check()
            if metadata["working_nodes"] > 250_000:
                raise RuntimeError("Solver exceeded working node limit")
            if raw.shape != (len(ty), len(tx)):
                raise RuntimeError("Unexpected tile shape")
            if before_background is not None:
                before_background[r0:r1, c0:c1] = raw[
                    r0 - wr0 : r1 - wr0, c0 - wc0 : c1 - wc0
                ]
            if radius:
                raw = raw - median(raw, radius=radius)
            surface[r0:r1, c0:c1] = raw[r0 - wr0 : r1 - wr0, c0 - wc0 : c1 - wc0]
            tile_records.append(
                dict(
                    input=direction,
                    tile=tile_id,
                    status="computed",
                    core=[r0, r1, c0, c1],
                    working=[wr0, wr1, wc0, wc1],
                    input_rows=len(selected),
                    retained_bounds=[*retained_low.tolist(), *retained_high.tolist()],
                    preflight_padded_nodes=preflight_nodes,
                    metadata=metadata,
                )
            )
            completed += 1
            emit("tiles", completed / total, input=direction, tile=tile_id)
        if stage_callback is not None:
            stage_callback(
                "grid_" + str(direction), before_background, plan["x"], plan["y"], "nT"
            )
            if radius:
                stage_callback(
                    "median_" + str(direction), surface, plan["x"], plan["y"], "nT"
                )
        return surface

    surfaces = [
        grid_direction(points, direction, p)
        for direction, (points, p) in enumerate(zip(data, plans))
    ]

    def strict_bilinear(surface, plan):
        gx, gy = np.meshgrid(x, y)
        fx = (gx - plan["x"][0]) / cell
        fy = (gy - plan["y"][0]) / cell
        inside = (
            (fx >= 0)
            & (fy >= 0)
            & (fx <= surface.shape[1] - 1)
            & (fy <= surface.shape[0] - 1)
        )
        ix = np.clip(np.floor(fx).astype(int), 0, surface.shape[1] - 2)
        iy = np.clip(np.floor(fy).astype(int), 0, surface.shape[0] - 2)
        wx, wy = fx - ix, fy - iy
        result = np.full(gx.shape, np.nan)
        rows, cols = np.nonzero(inside)
        cx, cy = ix[inside], iy[inside]
        corners = [
            surface[cy, cx],
            surface[cy, cx + 1],
            surface[cy + 1, cx],
            surface[cy + 1, cx + 1],
        ]
        valid = np.isfinite(corners).all(axis=0)
        vx, vy = wx[inside], wy[inside]
        values = (
            corners[0] * (1 - vx) * (1 - vy)
            + corners[1] * vx * (1 - vy)
            + corners[2] * (1 - vx) * vy
            + corners[3] * vx * vy
        )
        result[rows[valid], cols[valid]] = values[valid]
        return result

    aligned = (
        [strict_bilinear(a, p) for a, p in zip(surfaces, plans)]
        if directional
        else surfaces
    )
    if stage_callback is not None and directional:
        for i, a in enumerate(aligned):
            stage_callback("alignment_" + str(i), a, x, y, "nT")
    fused = aligned[0] if len(aligned) == 1 else (aligned[0] + aligned[1]) / 2
    if not np.isfinite(fused).any():
        raise ValueError("No common finite support; no output published.")
    if stage_callback is not None:
        stage_callback("magnetogram", fused, x, y, "nT")
    return surfaces, plans, aligned, fused, tile_records, directional
