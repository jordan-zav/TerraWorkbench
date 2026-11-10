"""Skeleton graph paths from explicit Boolean features; no geological labels."""

from importlib.metadata import version
import numpy as np

from ._array_contract import as_array
from ._calibration import integer_budget


def skeleton_paths(
    feature_mask,
    spacing,
    origin_xy,
    *,
    connectivity=8,
    minimum_length_m=0.0,
    max_cells=1_000_000,
    max_skeleton_pixels=200_000,
    max_paths=50_000,
    canceled=None,
):
    """Thin then trace centre-to-centre pixel graph paths in projected metres.

    Rows increase north, columns east; origin_xy is the centre of pixel (0,0).
    Features must be explicitly thresholded Boolean values. scikit-image's
    Zhang thinning is optional through the structure extra. Branch/end pixels
    split paths; cycles close explicitly. With 8-connectivity, diagonal
    shortcuts next to an occupied orthogonal neighbour are excluded to avoid
    artificial pixel-corner triangles. Connectivity 4 deliberately splits
    diagonals. Isolated pixels and short-path omissions are counted. No line
    smoothing, gap bridging, geological interpretation or CRS transformation.
    """
    for value, name in (
        (max_cells, "Maximum cells"),
        (max_skeleton_pixels, "Maximum skeleton pixels"),
        (max_paths, "Maximum paths"),
    ):
        integer_budget(value, name)
    mask, spacing, origin = (
        as_array(feature_mask),
        as_array(spacing, float),
        as_array(origin_xy, float),
    )
    minimum = float(minimum_length_m)
    if (
        mask.ndim != 2
        or not mask.size
        or mask.dtype.kind != "b"
        or mask.size > max_cells
    ):
        raise ValueError(
            "Explicit nonempty Boolean feature grid within the cell budget is required"
        )
    if (
        spacing.shape != (2,)
        or origin.shape != (2,)
        or not np.isfinite(spacing).all()
        or np.any(spacing <= 0)
        or not np.isfinite(origin).all()
        or not np.isfinite(minimum)
        or minimum < 0
        or connectivity not in (4, 8)
    ):
        raise ValueError(
            "Positive north/east spacing, finite centre origin, connectivity 4/8 and nonnegative length required"
        )

    def check():
        if canceled is not None and canceled():
            raise RuntimeError("Skeleton tracing canceled")

    check()
    from skimage.morphology import skeletonize

    skeleton = skeletonize(mask, method="zhang")
    pixels = np.flatnonzero(skeleton)
    if pixels.size > max_skeleton_pixels:
        raise ValueError("Skeleton graph exceeds the explicit vertex budget")
    rows, columns = skeleton.shape
    adjacency = {int(pixel): [] for pixel in pixels}
    directions = ((-1, 0), (1, 0), (0, -1), (0, 1)) + (
        ((-1, -1), (-1, 1), (1, -1), (1, 1)) if connectivity == 8 else ()
    )
    for index, pixel in enumerate(pixels):
        if index % 1024 == 0:
            check()
        r, c = divmod(int(pixel), columns)
        for dr, dc in directions:
            rr, cc = r + dr, c + dc
            if not 0 <= rr < rows or not 0 <= cc < columns or not skeleton[rr, cc]:
                continue
            other = rr * columns + cc
            if other <= pixel:
                continue
            if dr and dc and (skeleton[r, cc] or skeleton[rr, c]):
                continue
            adjacency[int(pixel)].append(other)
            adjacency[other].append(int(pixel))
    visited = set()
    paths = []
    omitted = 0

    def edge(a, b):
        return (a, b) if a < b else (b, a)

    def trace(start, second):
        nonlocal omitted
        check()
        sequence = [start, second]
        visited.add(edge(start, second))
        previous, current = start, second
        while current != start and len(adjacency[current]) == 2:
            next_pixel = next(n for n in adjacency[current] if n != previous)
            if edge(current, next_pixel) in visited:
                break
            visited.add(edge(current, next_pixel))
            sequence.append(next_pixel)
            previous, current = current, next_pixel
            if len(sequence) % 1024 == 0:
                check()
        indices = np.array([divmod(p, columns) for p in sequence])
        xy = np.column_stack(
            (
                origin[0] + indices[:, 1] * spacing[1],
                origin[1] + indices[:, 0] * spacing[0],
            )
        )
        if not np.isfinite(xy).all():
            raise ValueError("Path coordinates exceed finite range")
        delta = np.diff(indices, axis=0) * spacing
        length = float(np.hypot(delta[:, 0], delta[:, 1]).sum())
        if length < minimum:
            omitted += 1
            return
        if len(paths) >= max_paths:
            raise ValueError("Skeleton path count exceeds the explicit budget")
        azimuth = np.mod(np.rad2deg(np.arctan2(delta[:, 1], delta[:, 0])), 180.0)
        paths.append(
            dict(
                xy=xy,
                length_m=length,
                closed=sequence[0] == sequence[-1],
                segment_azimuth_degrees_axial=azimuth,
            )
        )

    for pixel, neighbours in adjacency.items():
        if len(neighbours) != 2:
            for other in neighbours:
                if edge(pixel, other) not in visited:
                    trace(pixel, other)
    for pixel, neighbours in adjacency.items():
        for other in neighbours:
            if edge(pixel, other) not in visited:
                trace(pixel, other)
    isolated = [divmod(p, columns) for p, n in adjacency.items() if not n]
    isolated_xy = np.array(
        [[origin[0] + c * spacing[1], origin[1] + r * spacing[0]] for r, c in isolated],
        dtype=float,
    ).reshape(-1, 2)
    if not np.isfinite(isolated_xy).all():
        raise ValueError("Isolated pixel coordinates exceed finite range")
    check()
    return dict(
        skeleton=skeleton,
        paths=paths,
        isolated_xy=isolated_xy,
        recipe=dict(
            spacing_m=spacing.tolist(),
            origin_cell_centre_xy=origin.tolist(),
            connectivity=connectivity,
            minimum_length_m=minimum,
            omitted_short_paths=omitted,
            skeleton_pixels=int(pixels.size),
            traced_edges=len(visited),
            engine="scikit-image",
            engine_version=version("scikit-image"),
            axes="east,north; rows increasing north",
            scope="Pixel graph paths only; no geological fault labels",
        ),
    )
