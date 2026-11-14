"""Exact sample editing and catalogue publication for line profiles."""

import numpy as np

from .channel_filters import ChannelFilterOptions, filter_segment


def _runs(mask):
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    return zip(edges[::2], edges[1::2])


class ProfileEdits:
    """Keep reversible, sparse edits to a channel in acquisition order."""

    def __init__(self, values):
        """Copy a vector of source samples into an independent draft."""
        self._original = np.asarray(values, dtype=float).copy()
        self.values = self._original.copy()
        self._past = []
        self._future = []

    @property
    def operations(self):
        """Return the applied operations in chronological order."""
        return [entry[3] for entry in self._past]

    def _apply(self, indices, values, operation):
        before = self.values[indices]
        after = np.broadcast_to(values, before.shape)
        changed = (before != after) & ~(np.isnan(before) & np.isnan(after))
        if changed.any():
            rows = indices[changed]
            self._past.append((rows, before[changed], after[changed], operation))
            self.values[rows] = after[changed]
            self._future.clear()

    def dummy(self, first, last):
        """Set the inclusive sample interval to dummy."""
        self._apply(
            np.arange(first, last + 1),
            np.nan,
            {"method": "dummy", "range": [first, last]},
        )

    def undo(self):
        """Reverse the most recent applied edit."""
        if self._past:
            entry = self._past.pop()
            self.values[entry[0]] = entry[1]
            self._future.append(entry)

    def redo(self):
        """Reapply the most recently undone edit."""
        if self._future:
            entry = self._future.pop()
            self.values[entry[0]] = entry[2]
            self._past.append(entry)

    def interpolate(self, axis, first, last, method, *, axis_name=None):
        """Fill bounded gaps in the selection by linear or Akima interpolation."""
        from scipy.interpolate import Akima1DInterpolator

        if method not in ("linear", "akima"):
            raise ValueError("Unknown interpolation method")
        axis = np.asarray(axis, dtype=float)
        indices = np.arange(first, last + 1)
        result = self.values[indices].copy()
        for start, stop in _runs(np.isfinite(axis)):
            left, right = max(start, first), min(stop, last + 1)
            if left >= right:
                continue
            target = np.flatnonzero(np.isnan(self.values[left:right])) + left
            if not target.size:
                continue
            x = axis[start:stop]
            direction = -1 if x[-1] < x[0] else 1
            if np.any(np.diff(x) * direction < 0):
                raise ValueError("Interpolation requires a monotonic axis")
            x = x * direction
            known = np.isfinite(self.values[start:stop])
            xp, anchor = np.unique(x[known], return_index=True)
            if len(xp) < (5 if method == "akima" else 2):
                continue
            yp = self.values[start:stop][known][anchor]
            query = axis[target] * direction
            inside = (query > xp[0]) & (query < xp[-1])
            query = query[inside]
            result[target[inside] - first] = (
                Akima1DInterpolator(xp, yp)(query)
                if method == "akima"
                else np.interp(query, xp, yp)
            )
        self._apply(
            indices,
            result,
            {"method": method, "range": [first, last], "axis": axis_name},
        )

    def spike_candidates(self, threshold, *, relative=True):
        """Find local outliers with Hampel or an absolute median residual limit."""
        options = ChannelFilterOptions(
            method="despike" if relative else "median",
            threshold=threshold,
        )
        options.validate()
        mask = np.zeros(self.values.size, dtype=bool)
        for start, stop in _runs(np.isfinite(self.values)):
            if stop - start >= options.window:
                values = self.values[start:stop]
                filtered, _ = filter_segment(np.arange(len(values)), values, options)
                mask[start:stop] = np.abs(values - filtered) > (
                    0 if relative else threshold
                )
        return np.flatnonzero(mask)

    def apply_spikes(self, indices, threshold, *, relative=True):
        """Mark the previewed samples dummy and retain detector parameters."""
        indices = np.asarray(indices, dtype=int)
        self._apply(
            indices,
            np.nan,
            {
                "method": "hampel" if relative else "median_residual",
                "threshold": threshold,
                "window": 5,
                "samples": indices.tolist(),
            },
        )

    def fourth_difference(self):
        """Return centered fourth sample differences, propagating dummies."""
        result = np.full(self.values.shape, np.nan)
        if result.size >= 5:
            result[2:-2] = np.diff(self.values, n=4)
        return result

    def statistics(self, first, last):
        """Return valid count, dummy count, min, max, mean and population SD."""
        values = self.values[first : last + 1]
        valid = values[np.isfinite(values)]
        summary = (
            (valid.min(), valid.max(), valid.mean(), valid.std())
            if valid.size
            else (np.nan,) * 4
        )
        return (valid.size, values.size - valid.size, *summary)

    def changes(self):
        """Return sample indices and values that differ from the source."""
        same = (self.values == self._original) | (
            np.isnan(self.values) & np.isnan(self._original)
        )
        indices = np.flatnonzero(~same)
        return indices, self.values[indices].copy()


def publish_profile_edits(store, database, source, output, inputs, unit, edits):
    """Publish a row-aligned derivative from pinned catalogue versions.

    Edit records contain physical row positions, changed values and recipes.
    Other rows retain their source values.
    """
    from .survey_store import _verify_input_versions

    snapshot = store._snapshot(database, list(inputs))
    _verify_input_versions(snapshot, inputs)
    channel = [row for row in snapshot if row["name"] == source]
    size = next(row["rows"] for row in store.databases() if row["id"] == database)
    if size * 8 > 256 * 1024**2:
        raise ValueError("Computed channels exceed the declared array byte budget")
    result = np.empty(size)
    offset = 0
    for batch in store._batches(channel):
        end = offset + len(batch)
        result[offset:end] = batch.column(source).to_numpy(zero_copy_only=False)
        offset = end
    if offset != size:
        raise ValueError("Source row count differs from the catalogue")
    for positions, values, _ in edits:
        result[positions] = values
    return store.publish_channels(
        database,
        {output: result},
        units={output: unit},
        inputs=inputs,
        provenance={
            "operation": "profile_edit",
            "source": source,
            "lines": [recipe for _, _, recipe in edits],
        },
    )
