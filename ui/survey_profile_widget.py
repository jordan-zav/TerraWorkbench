"""Native Qt profile rendering; no Matplotlib, resampling or scientific edits."""

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPolygonF, QPalette
from qgis.PyQt.QtWidgets import QWidget

from ..qgis_plugin.qgis_compat import qt_enum


class SurveyProfileWidget(QWidget):
    positionChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.profile = None
        self.x_label = ""
        self.y_label = ""
        self.empty_text = ""
        self.viewport = None
        self.selected_sample = None
        self._drag = None
        self.setMouseTracking(True)

    def set_profile(self, profile, x_label, y_label):
        self.profile = profile
        self.x_label, self.y_label = x_label, y_label
        self.viewport = None
        self.update()

    def clear(self):
        self.profile = None
        self.viewport = None
        self.update()

    def set_selected_sample(self, sample):
        self.selected_sample = sample
        self.update()

    def plot_box(self):
        return QRectF(80, 25, max(1, self.width() - 105), max(1, self.height() - 85))

    def bounds(self):
        if self.viewport is not None:
            return self.viewport
        segments = self.profile["segments"] if self.profile else []
        if not segments:
            return None
        x = np.concatenate([s["x"] for s in segments])
        y = np.concatenate([s["y"] for s in segments])
        lx, hx, ly, hy = x.min(), x.max(), y.min(), y.max()
        if lx == hx:
            lx, hx = lx - 0.5, hx + 0.5
        pad = (hy - ly) * 0.05 if ly != hy else max(abs(ly) * 0.01, 1.0)
        return lx, hx, ly - pad, hy + pad

    def fit(self):
        self.viewport = None
        self.update()

    def zoom(self, factor, anchor=None):
        bounds = self.bounds()
        if bounds is None:
            return
        lx, hx, ly, hy = bounds
        fx, fy = anchor or (0.5, 0.5)
        cx, cy = lx + fx * (hx - lx), ly + fy * (hy - ly)
        updated = (
            cx + (lx - cx) * factor,
            cx + (hx - cx) * factor,
            cy + (ly - cy) * factor,
            cy + (hy - cy) * factor,
        )
        if (
            np.isfinite(updated).all()
            and updated[1] > updated[0]
            and updated[3] > updated[2]
        ):
            self.viewport = updated
            self.update()

    @staticmethod
    def event_position(event):
        return event.position() if hasattr(event, "position") else QPointF(event.pos())

    def wheelEvent(self, event):
        point, box = self.event_position(event), self.plot_box()
        if box.contains(point):
            self.zoom(
                0.8 if event.angleDelta().y() > 0 else 1.25,
                (
                    (point.x() - box.left()) / box.width(),
                    (box.bottom() - point.y()) / box.height(),
                ),
            )
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if (
            event.button() == qt_enum(Qt, "MouseButton", "LeftButton")
            and self.bounds() is not None
        ):
            point = self.event_position(event)
            if self.plot_box().contains(point):
                self._drag = (point, self.bounds())

    def mouseReleaseEvent(self, event):
        self._drag = None

    def mouseMoveEvent(self, event):
        point, box = self.event_position(event), self.plot_box()
        if self._drag is not None:
            origin, (lx, hx, ly, hy) = self._drag
            dx = (point.x() - origin.x()) / box.width() * (hx - lx)
            dy = (point.y() - origin.y()) / box.height() * (hy - ly)
            self.viewport = (lx - dx, hx - dx, ly + dy, hy + dy)
            self.update()
        bounds = self.bounds()
        if bounds is not None and box.contains(point):
            lx, hx, ly, hy = bounds
            self.positionChanged.emit(
                f"{self.x_label}: {lx + (point.x() - box.left()) / box.width() * (hx - lx):.7g} · {self.y_label}: {ly + (box.bottom() - point.y()) / box.height() * (hy - ly):.7g}"
            )

    def series_colors(self):
        colors = [
            self.palette().color(
                qt_enum(QPalette, "ColorGroup", "Active"),
                qt_enum(QPalette, "ColorRole", "Highlight"),
            ),
            QColor("#d47b27"),
            QColor("#2b9a72"),
            QColor("#a45cab"),
        ]
        labels = (
            list(dict.fromkeys(s["label"] for s in self.profile["segments"]))
            if self.profile
            else []
        )
        return {
            label: colors[index % len(colors)] for index, label in enumerate(labels)
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(qt_enum(QPainter, "RenderHint", "Antialiasing"))
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        painter.setPen(palette.text().color())
        segments = self.profile["segments"] if self.profile else []
        if not segments:
            painter.drawText(QRectF(self.rect()), 0x84, self.empty_text)
            return
        box = self.plot_box()
        low_x, high_x, low_y, high_y = self.bounds()
        grid = QColor(palette.text().color())
        grid.setAlpha(45)
        for step in range(5):
            fraction = step / 4
            px, py = (
                box.left() + fraction * box.width(),
                box.bottom() - fraction * box.height(),
            )
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(px, box.top()), QPointF(px, box.bottom()))
            painter.drawLine(QPointF(box.left(), py), QPointF(box.right(), py))
            painter.setPen(palette.text().color())
            painter.drawText(
                QRectF(px - 48, box.bottom() + 5, 96, 20),
                0x84,
                f"{low_x + fraction * (high_x - low_x):.5g}",
            )
            painter.drawText(
                QRectF(0, py - 10, box.left() - 7, 20),
                0x82,
                f"{low_y + fraction * (high_y - low_y):.5g}",
            )
        painter.drawRect(box)
        colors = self.series_colors()
        painter.save()
        painter.setClipRect(box)
        for segment in segments:
            painter.setPen(QPen(colors[segment["label"]], 1.4))
            points = QPolygonF(
                [
                    QPointF(
                        box.left() + (a - low_x) / (high_x - low_x) * box.width(),
                        box.bottom() - (b - low_y) / (high_y - low_y) * box.height(),
                    )
                    for a, b in zip(segment["x"], segment["y"])
                ]
            )
            if len(points) == 1:
                painter.drawEllipse(points[0], 2.5, 2.5)
            else:
                painter.drawPolyline(points)
        if self.selected_sample is not None:
            x = box.left() + (self.selected_sample - low_x) / (high_x - low_x) * box.width()
            painter.setPen(QPen(palette.text().color(), 1.25, qt_enum(Qt, "PenStyle", "DashLine")))
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))
        painter.restore()
        painter.setPen(palette.text().color())
        painter.drawText(
            QRectF(box.left(), box.bottom() + 30, box.width(), 25), 0x84, self.x_label
        )
        painter.drawText(QRectF(box.left(), 0, box.width(), 23), 0x84, self.y_label)
