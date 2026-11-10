"""Single native tree-walk implementation; Numba is imported only on execution."""

import math

import numpy as np

_compiled = None
_builder = None


def get_builder():
    global _builder
    if _builder is None:
        from numba import njit

        _builder = njit(cache=False)(_build)
    return _builder


def _build(x, y, z, dx, dy, crust, water, leaf_cells, max_nodes):
    capacity = min(max_nodes, 2 * z.size - 1)
    rectangles = np.empty((capacity, 4), np.int64)
    children = np.empty((capacity, 4), np.int64)
    masses = np.empty((capacity, 2), np.float64)
    centres = np.empty((capacity, 2, 3), np.float64)
    lower = np.empty((capacity, 2, 3), np.float64)
    upper = np.empty((capacity, 2, 3), np.float64)
    moments = np.empty((capacity, 2), np.float64)
    radii = np.empty((capacity, 2), np.float64)
    counts = np.empty(capacity, np.int64)
    offsets = np.empty(capacity, np.int64)
    sources = np.empty(z.size, np.int64)
    rectangles[0, 0], rectangles[0, 1], rectangles[0, 2], rectangles[0, 3] = (
        0,
        len(y),
        0,
        len(x),
    )
    created, used, node, status = 1, 0, 0, 0
    while node < created:
        children[node, :] = -1
        masses[node, :], centres[node, :, :], moments[node, :], radii[node, :] = (
            0.0,
            0.0,
            0.0,
            0.0,
        )
        lower[node, :, :], upper[node, :, :] = np.inf, -np.inf
        counts[node], offsets[node] = 0, used
        r0, r1, c0, c1 = rectangles[node]
        active = False
        for r in range(r0, r1):
            for c in range(c0, c1):
                if z[r, c] != 0:
                    active = True
                    break
            if active:
                break
        if active and (r1 - r0) * (c1 - c0) > leaf_cells:
            nr, nc = min(2, r1 - r0), min(2, c1 - c0)
            rm, cm = (r0 + r1) // 2, (c0 + c1) // 2
            for ir in range(nr):
                a, b = (r0, r1) if nr == 1 else (r0, rm) if ir == 0 else (rm, r1)
                for ic in range(nc):
                    c, d = (c0, c1) if nc == 1 else (c0, cm) if ic == 0 else (cm, c1)
                    if created >= capacity:
                        status = 1
                        break
                    children[node, ir * nc + ic] = created
                    (
                        rectangles[created, 0],
                        rectangles[created, 1],
                        rectangles[created, 2],
                        rectangles[created, 3],
                    ) = a, b, c, d
                    created += 1
                if status:
                    break
            if status:
                break
        elif active:
            for r in range(r0, r1):
                for c in range(c0, c1):
                    height = z[r, c]
                    if height == 0:
                        continue
                    group = 0 if height > 0 else 1
                    mass = (
                        abs(height) * (crust if group == 0 else crust - water) * dx * dy
                    )
                    previous = masses[node, group]
                    total = previous + mass
                    if not np.isfinite(total) or not mass > 0:
                        status = 2
                        break
                    delta_x = x[c] - centres[node, group, 0]
                    delta_y = y[r] - centres[node, group, 1]
                    delta_z = height / 2 - centres[node, group, 2]
                    # Weighted Welford avoids subtracting large raw moments.
                    moments[node, group] += mass * (
                        dx * dx + dy * dy + height * height
                    ) / 12 + (previous / total) * mass * (
                        delta_x * delta_x + delta_y * delta_y + delta_z * delta_z
                    )
                    centres[node, group, 0] += (mass / total) * delta_x
                    centres[node, group, 1] += (mass / total) * delta_y
                    centres[node, group, 2] += (mass / total) * delta_z
                    masses[node, group] = total
                    lower[node, group, 0] = min(lower[node, group, 0], x[c] - dx / 2)
                    lower[node, group, 1] = min(lower[node, group, 1], y[r] - dy / 2)
                    lower[node, group, 2] = min(lower[node, group, 2], min(height, 0.0))
                    upper[node, group, 0] = max(upper[node, group, 0], x[c] + dx / 2)
                    upper[node, group, 1] = max(upper[node, group, 1], y[r] + dy / 2)
                    upper[node, group, 2] = max(upper[node, group, 2], max(height, 0.0))
                    sources[used] = r * z.shape[1] + c
                    used += 1
                    counts[node] += 1
                if status:
                    break
            if status:
                break
        node += 1
    if not status:
        for node in range(created - 1, -1, -1):
            for group in range(2):
                if children[node, 0] >= 0:
                    for child in children[node]:
                        if child < 0 or masses[child, group] == 0:
                            continue
                        mass = masses[child, group]
                        previous = masses[node, group]
                        total = previous + mass
                        if not np.isfinite(total):
                            status = 2
                            break
                        distance2 = 0.0
                        for coordinate in range(3):
                            delta = (
                                centres[child, group, coordinate]
                                - centres[node, group, coordinate]
                            )
                            distance2 += delta * delta
                            centres[node, group, coordinate] += (mass / total) * delta
                            lower[node, group, coordinate] = min(
                                lower[node, group, coordinate],
                                lower[child, group, coordinate],
                            )
                            upper[node, group, coordinate] = max(
                                upper[node, group, coordinate],
                                upper[child, group, coordinate],
                            )
                        moments[node, group] += (
                            moments[child, group]
                            + (previous / total) * mass * distance2
                        )
                        masses[node, group] = total
                if masses[node, group] != 0:
                    radius = 0.0
                    for coordinate in range(3):
                        distance = max(
                            abs(
                                lower[node, group, coordinate]
                                - centres[node, group, coordinate]
                            ),
                            abs(
                                upper[node, group, coordinate]
                                - centres[node, group, coordinate]
                            ),
                        )
                        radius = math.hypot(radius, distance)
                    radii[node, group] = radius
                    if not np.isfinite(radius) or not np.isfinite(moments[node, group]):
                        status = 2
            if status:
                break
        # Keep magnitudes positive until all parent summaries have been assembled.
        masses[:created, 1] *= -1.0
    return (
        children,
        masses,
        centres,
        radii,
        moments,
        counts,
        offsets,
        sources,
        created,
        used,
        status,
    )


def get_walker():
    global _compiled
    if _compiled is None:
        from numba import njit

        # No on-disk cache outside the calling development/runtime environment.
        _compiled = njit(cache=False)(_walk)
    return _compiled


def _walk(
    station,
    children,
    masses,
    centres,
    radii,
    moments,
    source_counts,
    tolerance,
    max_visits,
    max_sources,
    coefficient,
):
    count = len(children)
    stack = np.empty(count, np.int64)
    leaves = np.empty(count, np.int64)
    ids = np.empty(count, np.int64)
    errors = np.empty(count, np.float64)
    fields = np.empty(count, np.float64)
    stack[0] = 0
    pending, heap_size, leaf_count, visits, exact, status = 1, 0, 0, 0, 0, 0
    remaining = 0.0
    while pending or heap_size:
        if pending:
            pending -= 1
            node = stack[pending]
            visits += 1
            if visits > max_visits:
                status = 1
                break
            if masses[node, 0] == 0 and masses[node, 1] == 0:
                continue
            bound, field = 0.0, 0.0
            if tolerance > 0:
                for group in range(2):
                    mass = masses[node, group]
                    if mass == 0:
                        continue
                    dx = station[0] - centres[node, group, 0]
                    dy = station[1] - centres[node, group, 1]
                    dz = station[2] - centres[node, group, 2]
                    distance = math.hypot(math.hypot(dx, dy), dz)
                    if not np.isfinite(distance):
                        status = 3
                        break
                    gap = distance - radii[node, group]
                    if gap <= 0:
                        bound = np.inf
                        break
                    error = (
                        12 * coefficient * moments[node, group] / gap / gap / gap / gap
                    )
                    bound += np.nextafter(error, np.inf)
                    field += ((coefficient * mass / distance) / distance) * (
                        dz / distance
                    )
                if status:
                    break
            else:
                bound = np.inf
            if np.isfinite(bound) and np.isfinite(field):
                # Max heap; node ID breaks ties deterministically.
                position = heap_size
                heap_size += 1
                while position:
                    parent = (position - 1) // 2
                    if (
                        errors[parent] > bound
                        or errors[parent] == bound
                        and ids[parent] < node
                    ):
                        break
                    ids[position], errors[position], fields[position] = (
                        ids[parent],
                        errors[parent],
                        fields[parent],
                    )
                    position = parent
                ids[position], errors[position], fields[position] = node, bound, field
                remaining += bound
                continue
        else:
            if remaining <= tolerance * (1.0 - 1e-8):
                # Recompute when close to the threshold to avoid subtractive drift.
                total, carry = 0.0, 0.0
                for i in range(heap_size):
                    adjusted = errors[i] - carry
                    updated = total + adjusted
                    carry = (updated - total) - adjusted
                    total = updated
                remaining = total
                if remaining <= tolerance * (1.0 - 1e-8):
                    break
            node = ids[0]
            remaining = max(0.0, remaining - errors[0])
            heap_size -= 1
            if heap_size:
                last_id, last_error, last_field = (
                    ids[heap_size],
                    errors[heap_size],
                    fields[heap_size],
                )
                position = 0
                while 2 * position + 1 < heap_size:
                    child = 2 * position + 1
                    other = child + 1
                    if other < heap_size and (
                        errors[other] > errors[child]
                        or errors[other] == errors[child]
                        and ids[other] < ids[child]
                    ):
                        child = other
                    if (
                        last_error > errors[child]
                        or last_error == errors[child]
                        and last_id < ids[child]
                    ):
                        break
                    ids[position], errors[position], fields[position] = (
                        ids[child],
                        errors[child],
                        fields[child],
                    )
                    position = child
                ids[position], errors[position], fields[position] = (
                    last_id,
                    last_error,
                    last_field,
                )
        if children[node, 0] >= 0:
            for child in children[node]:
                if child >= 0:
                    stack[pending] = child
                    pending += 1
        else:
            exact += source_counts[node]
            if exact > max_sources:
                status = 2
                break
            leaves[leaf_count] = node
            leaf_count += 1
    monopoles = 0
    for i in range(heap_size):
        for group in range(2):
            monopoles += masses[ids[i], group] != 0
    return (
        fields[:heap_size].copy(),
        errors[:heap_size].copy(),
        leaves[:leaf_count].copy(),
        visits,
        exact,
        monopoles,
        status,
    )
