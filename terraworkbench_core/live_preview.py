"""Screen-resolution raster windows and cooperative latest-request cancellation.

Preview windows include real observations around the viewport before the FFT
engine adds reflection and taper. They approximate a full-grid calculation;
long wavelength operators still depend on observations outside this window.
"""

from dataclasses import dataclass
from math import ceil, floor
from threading import Event


@dataclass(frozen=True)
class PreviewWindow:
    """GDAL source rectangle and bounded screen-resolution output dimensions."""

    xoff: int
    yoff: int
    width: int
    height: int
    columns: int
    rows: int
    transform: tuple


def preview_window(transform, shape, extent, screen, margin=0.5, max_side=768):
    """Clip a north-up viewport plus margin to the source, without upsampling.

    Extent is xmin, ymin, xmax, ymax in source coordinates. Margin is a fraction
    of each visible dimension on each side. Output spacing follows screen
    pixels, capped at max_side for the visible portion, including on huge files.
    """
    x, dx, rx, y, ry, dy = transform
    if dx <= 0 or dy >= 0 or rx or ry:
        raise ValueError("Preview requires a north-up raster.")
    xmin, ymin, xmax, ymax = extent
    if xmax <= xmin or ymax <= ymin or min(screen) <= 0:
        raise ValueError("Invalid viewport.")
    if margin < 0 or max_side < 2:
        raise ValueError("Invalid preview budget.")
    mx, my = (xmax - xmin) * margin, (ymax - ymin) * margin
    x0 = max(0, floor((xmin - mx - x) / dx))
    x1 = min(shape[1], ceil((xmax + mx - x) / dx))
    y0 = max(0, floor((ymax + my - y) / dy))
    y1 = min(shape[0], ceil((ymin - my - y) / dy))
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ValueError("Viewport does not intersect the raster.")
    spacing = max(
        dx,
        -dy,
        (xmax - xmin) / min(screen[0], max_side),
        (ymax - ymin) / min(screen[1], max_side),
    )
    columns = max(2, ceil((x1 - x0) * dx / spacing))
    rows = max(2, ceil((y1 - y0) * -dy / spacing))
    return PreviewWindow(
        x0,
        y0,
        x1 - x0,
        y1 - y0,
        columns,
        rows,
        (
            x + x0 * dx,
            (x1 - x0) * dx / columns,
            0,
            y + y0 * dy,
            0,
            (y1 - y0) * dy / rows,
        ),
    )


class LatestRequest:
    """Invalidate stale results and signal cancellation before the debounce ends."""

    def __init__(self):
        """Start with no pending request."""
        self.generation = 0
        self.cancelled = Event()

    def replace(self):
        """Cancel the previous token and return a new generation and event."""
        self.cancelled.set()
        self.generation += 1
        self.cancelled = Event()
        return self.generation, self.cancelled

    def accepts(self, generation):
        """Return whether a result still belongs to the latest live request."""
        return generation == self.generation and not self.cancelled.is_set()


def product_palette(algorithm_id):
    """Choose GeoRamp's magnetic palette or a zero-centred signed palette."""
    name = algorithm_id.lower()
    signed = ("derivative", "tilt", "laplacian", "high_pass", "highpass", "residual")
    tokens = set(name.split(":")[-1].split("_"))
    divergent = any(key in name for key in signed) or bool(
        tokens & {"dx", "dy", "dz", "dz2"}
    )
    return "blue_white_red" if divergent else "classic_geophysics"
