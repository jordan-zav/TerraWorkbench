"""Fast Qt rendering for stacked line profiles."""

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from qgis.PyQt.QtWidgets import QWidget

from ..qgis_plugin.qgis_compat import qt_enum
from .profile_ticks import profile_ticks
from .survey_profile_widget import SurveyProfileWidget


class ProfileCanvas(QWidget):
    """Draw independent channel axes and select original sample positions."""

    hovered = pyqtSignal(int)
    selected = pyqtSignal(int, int)
    navigate = pyqtSignal(int)
    channelClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 310)
        self.setMouseTracking(True)
        self.setFocusPolicy(qt_enum(Qt, "FocusPolicy", "StrongFocus"))
        self.axis = np.empty(0)
        self.series = {}
        self.preview = np.empty(0, dtype=int)
        self.active = ""
        self.axis_label = ""
        self.selection = None
        self.cursor = None
        self._drag = None
        self._image = None
        self._view = None

    def set_data(self, axis, series, label, active, preview, *, reset=False):
        """Install full-resolution samples and invalidate the render cache."""
        self.axis, self.series, self.axis_label = axis, series, label
        self.active, self.preview = active, preview
        if reset:
            valid = np.flatnonzero(np.isfinite(axis))
            order = np.argsort(axis[valid], kind="stable")
            self._ordered = valid[order]
            self._sorted = axis[self._ordered]
            if valid.size:
                low, high = self._sorted[0], self._sorted[-1]
                self._view = (low, high) if high > low else (low - 0.5, high + 0.5)
            else:
                self._view = None
            self.selection = self.cursor = None
        self._invalidate()

    def _invalidate(self):
        self._image = None
        self.update()

    def _plot(self):
        return QRectF(95, 4, max(1, self.width() - 132), max(1, self.height() - 43))

    def _pixel(self, x):
        low, high = self._view
        plot = self._plot()
        return plot.left() + (x - low) / (high - low) * plot.width()

    def _sample(self, point):
        low, high = self._view
        plot = self._plot()
        x = low + (point.x() - plot.left()) / plot.width() * (high - low)
        right = int(np.clip(np.searchsorted(self._sorted, x), 0, len(self._sorted) - 1))
        left = max(0, right - 1)
        index = (
            left
            if abs(x - self._sorted[left]) <= abs(x - self._sorted[right])
            else right
        )
        return int(self._ordered[index])

    def _render(self):
        self._image = QPixmap(self.size())
        palette = self.palette()
        self._image.fill(palette.base().color())
        if self._view is None or not self.series:
            return
        painter = QPainter(self._image)
        plot = self._plot()
        height = plot.height() / len(self.series)
        for index, (key, (label, values)) in enumerate(self.series.items()):
            top = plot.top() + index * height
            box = QRectF(plot.left(), top + 20, plot.width(), max(1, height - 24))
            self._draw_series(painter, box, key, label, values)
        painter.setPen(palette.text().color())
        for value, label in profile_ticks(*self._view, intervals=5):
            x = self._pixel(value)
            painter.drawLine(QPointF(x, plot.bottom() - 4), QPointF(x, plot.bottom()))
            painter.drawText(QRectF(x - 42, plot.bottom(), 84, 17), 0x84, label)
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 17, plot.width(), 20),
            0x84,
            self.axis_label,
        )
        painter.end()

    def _draw_series(self, painter, box, key, label, values):
        palette = self.palette()
        color = palette.highlight().color() if key == self.active else QColor("#268273")
        painter.setPen(color)
        painter.drawText(QPointF(box.left(), box.top() - 4), label)
        painter.drawRect(box)
        low, high = self._view
        valid = np.isfinite(values) & np.isfinite(self.axis)
        visible = valid & (self.axis >= low) & (self.axis <= high)
        if not visible.any():
            return
        bottom, top = values[visible].min(), values[visible].max()
        if bottom == top:
            bottom, top = bottom - 1, top + 1
        intervals = min(4, max(1, int(box.height() / 24)))
        for value, tick in profile_ticks(bottom, top, intervals):
            y = box.bottom() - (value - bottom) / (top - bottom) * box.height()
            painter.drawLine(QPointF(box.left(), y), QPointF(box.left() + 4, y))
            painter.drawText(QRectF(0, y - 7, box.left() - 6, 14), 0x82, tick)
        painter.save()
        painter.setClipRect(box)
        rows = np.flatnonzero(visible)
        x = box.left() + (self.axis[rows] - low) / (high - low) * box.width()
        y = box.bottom() - (values[rows] - bottom) / (top - bottom) * box.height()
        painter.setPen(QPen(color, 1.15))
        if rows.size > box.width() * 2:
            # One min/max envelope per occupied pixel column preserves spikes.
            pixels = x.astype(int)
            order = np.argsort(pixels, kind="stable")
            pixels, y = pixels[order], y[order]
            starts = np.r_[0, np.flatnonzero(np.diff(pixels)) + 1]
            for px, lo, hi in zip(
                pixels[starts],
                np.minimum.reduceat(y, starts),
                np.maximum.reduceat(y, starts),
            ):
                painter.drawLine(QPointF(px, lo), QPointF(px, max(lo + 0.5, hi)))
        else:
            cuts = np.flatnonzero(np.diff(rows) != 1) + 1
            for segment in np.split(np.arange(rows.size), cuts):
                points = QPolygonF([QPointF(x[i], y[i]) for i in segment])
                if len(points) == 1:
                    painter.drawEllipse(points[0], 2, 2)
                else:
                    painter.drawPolyline(points)
        if key == self.active and self.preview.size:
            candidates = self.preview[visible[self.preview]]
            painter.setPen(QPen(QColor("#d26d22"), 1.5))
            px = self._pixel(self.axis[candidates])
            py = (
                box.bottom()
                - (values[candidates] - bottom) / (top - bottom) * box.height()
            )
            pixels = np.column_stack((px, py)).astype(int)
            for x_dot, y_dot in np.unique(pixels, axis=0)[:10000]:
                painter.drawEllipse(QPointF(x_dot, y_dot), 3, 3)
        painter.restore()

    def paintEvent(self, event):
        if self._image is None or self._image.size() != self.size():
            self._render()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._image)
        if self._view is None:
            return
        box = self._plot()
        painter.setClipRect(box)
        color = self.palette().highlight().color()
        if self.selection:
            first, last = self.selection
            x, end = sorted(self._pixel(self.axis[[first, last]]))
            color.setAlpha(45)
            painter.fillRect(
                QRectF(x - 1, box.top(), max(2, end - x), box.height()), color
            )
        if self.cursor is not None and np.isfinite(self.axis[self.cursor]):
            x = self._pixel(self.axis[self.cursor])
            painter.setPen(
                QPen(
                    self.palette().text().color(),
                    1,
                    qt_enum(Qt, "PenStyle", "DashLine"),
                )
            )
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))

    def wheelEvent(self, event):
        point = SurveyProfileWidget.event_position(event)
        if self._view is None or not self._plot().contains(point):
            event.ignore()
            return
        low, high = self._view
        ratio = (point.x() - self._plot().left()) / self._plot().width()
        anchor = low + ratio * (high - low)
        factor = 0.8 if event.angleDelta().y() > 0 else 1.25
        start, end = anchor + (low - anchor) * factor, anchor + (high - anchor) * factor
        if np.isfinite([start, end]).all() and end > start:
            self._view = start, end
            self._invalidate()
        event.accept()

    def mousePressEvent(self, event):
        point = SurveyProfileWidget.event_position(event)
        if not self.series or self._view is None or not self._plot().contains(point):
            return
        if event.button() == qt_enum(Qt, "MouseButton", "LeftButton"):
            index = int(
                (point.y() - self._plot().top())
                / self._plot().height()
                * len(self.series)
            )
            self.channelClicked.emit(
                list(self.series)[min(index, len(self.series) - 1)]
            )
            sample = self._sample(point)
            self.setFocus()
            self._drag = ("select", sample)
            self._select(sample, sample)
        elif event.button() in (
            qt_enum(Qt, "MouseButton", "RightButton"),
            qt_enum(Qt, "MouseButton", "MiddleButton"),
        ):
            self._drag = ("pan", point.x(), self._view)

    def mouseMoveEvent(self, event):
        if self._view is None:
            return
        point = SurveyProfileWidget.event_position(event)
        if self._drag and self._drag[0] == "pan":
            _, origin, (low, high) = self._drag
            shift = (point.x() - origin) / self._plot().width() * (high - low)
            self._view = low - shift, high - shift
            self._invalidate()
        elif self._plot().contains(point):
            row = self._sample(point)
            if self._drag:
                self._select(self._drag[1], row)
            self.cursor = row
            self.hovered.emit(row)
            self.update()

    def _select(self, first, last):
        self.selection = tuple(sorted((first, last)))
        self.selected.emit(*self.selection)
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None

    def keyPressEvent(self, event):
        if event.key() == qt_enum(Qt, "Key", "Key_Left"):
            self.navigate.emit(-1)
        elif event.key() == qt_enum(Qt, "Key", "Key_Right"):
            self.navigate.emit(1)
        else:
            super().keyPressEvent(event)
