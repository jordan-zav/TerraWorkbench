"""Read-only, paged Qt model for survey observations."""

from bisect import bisect_right
from collections import OrderedDict
from itertools import groupby
import json
import re
from threading import Event

from qgis.PyQt.QtCore import (
    QAbstractTableModel, QModelIndex, QObject, QRunnable, QThreadPool, Qt, pyqtSignal,
)

from .i18n import language
from ..qgis_plugin.qgis_compat import qt_enum
from ..terraworkbench_core.survey_map import _line_kind, _line_label


PAGE_SIZE = 512
CACHE_PAGES = 6
DISPLAY = qt_enum(Qt, "ItemDataRole", "DisplayRole")
TOOLTIP = qt_enum(Qt, "ItemDataRole", "ToolTipRole")


def tr(en, es, pt):
    return {"en": en, "es": es, "pt": pt}.get(language(), en)


def channel_description(channel):
    fields = [channel["unit"], channel["data_type"]]
    if channel["number"] > 1:
        fields.append(f"v{channel['number']}")
    return f"{channel['name']} ({', '.join(filter(None, fields))})"


def channel_tooltip(channel):
    provenance = json.loads(channel["provenance"])
    source = provenance.get("source") or provenance.get("operation") or "—"
    return tr(
        "Type: {kind}\nVersion: {version}\nSource: {source}",
        "Tipo: {kind}\nVersión: {version}\nOrigen: {source}",
        "Tipo: {kind}\nVersão: {version}\nOrigem: {source}",
    ).format(kind=channel["data_type"], version=channel["number"], source=source)


def line_spans(store, database, channel, kind_channel, metadata, canceled):
    """Index contiguous physical ranges in order of first appearance."""
    index = {}
    names = list(dict.fromkeys(name for name in (channel, kind_channel) if name))
    offset = 0
    declarations = metadata.get("line_metadata") or {}
    with_batches = store.batches(database, names, canceled=canceled)
    try:
        for batch in with_batches:
            values = batch.column(channel).to_pylist()
            kinds = batch.column(kind_channel).to_pylist() if kind_channel else None
            position = 0
            for value, run in groupby(values):
                length = sum(1 for _ in run)
                label = _line_label(value)
                if label is not None:
                    spans, counts, kind = index.setdefault(value, ([], [], None))
                    start = offset + position
                    if spans and spans[-1][1] == start:
                        spans[-1] = (spans[-1][0], start + length)
                        counts[-1] += length
                    else:
                        spans.append((start, start + length))
                        counts.append((counts[-1] if counts else 0) + length)
                    if not kind:
                        declaration = declarations.get(label) or {}
                        kind = _line_kind(declaration.get("kind") or declaration.get("type"))
                        if not kind and kinds:
                            kind = next(
                                (k for item in kinds[position:position + length] if (k := _line_kind(item))),
                                None,
                            )
                        if kind:
                            index[value] = spans, counts, kind
                position += length
            offset += len(batch)
    finally:
        with_batches.close()
    for value, (spans, counts, kind) in index.items():
        if kind is None:
            if re.match(r"^(?:FL(?:[ _-]|\d|$)|L[ _-]?\d)", str(value), re.I):
                index[value] = spans, counts, "traverse"
            elif re.match(r"^(?:TL(?:[ _-]|\d|$)|T[ _-]?\d)", str(value), re.I):
                index[value] = spans, counts, "tie"
    return index


class _Signals(QObject):
    done = pyqtSignal(object, object, object)


class _Job(QRunnable):
    def __init__(self, key, work):
        super().__init__()
        self.key, self.work = key, work
        self.signals = _Signals()

    def run(self):
        try:
            result = self.work()
        except Exception as error:
            self.signals.done.emit(self.key, None, str(error))
        else:
            self.signals.done.emit(self.key, result, None)


def background(key, work, callback):
    job = _Job(key, work)
    job.signals.done.connect(callback, qt_enum(Qt, "ConnectionType", "QueuedConnection"))
    QThreadPool.globalInstance().start(job)


class SurveySheetModel(QAbstractTableModel):
    failed = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.canceled = Event()
        self.channels = []
        self.cache = OrderedDict()
        self.pending = set()
        self.requested = None
        self.store = None
        self.spans, self.ends = [], []
        self.rows = self.offset = 0
        self.page = None

    def reset(self, channels, *, store=None, spans=None, ends=None, page=None, offset=0):
        self.beginResetModel()
        self.canceled.set()
        self.canceled = Event()
        self.channels = list(channels)
        self.store = store
        self.spans, self.ends = spans or [], ends or []
        self.page, self.offset = page, offset
        self.rows = self.ends[-1] if self.ends else len(next(iter(page.values()), [])) if page else 0
        self.cache.clear()
        self.pending.clear()
        self.requested = None
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.rows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.channels)

    def headerData(self, section, orientation, role=DISPLAY):
        if orientation == qt_enum(Qt, "Orientation", "Vertical"):
            return str(self.offset + section + 1) if role == DISPLAY else None
        if not 0 <= section < len(self.channels):
            return None
        channel = self.channels[section]
        if role == DISPLAY:
            return f"{channel['name']}\n{channel['unit']}" if channel["unit"] else channel["name"]
        if role == TOOLTIP:
            return channel_tooltip(channel)
        return None

    def retranslate(self):
        if self.channels:
            self.headerDataChanged.emit(qt_enum(Qt, "Orientation", "Horizontal"), 0, len(self.channels) - 1)

    def data(self, index, role=DISPLAY):
        if not index.isValid() or role != DISPLAY:
            return None
        row = index.row()
        if self.page is not None:
            value = self.page[self.channels[index.column()]["name"]][row]
        else:
            block, within = divmod(row, PAGE_SIZE)
            if block not in self.cache:
                self._request(block)
                return None
            self.cache.move_to_end(block)
            value = self.cache[block][self.channels[index.column()]["name"]][within]
        return "" if value is None else str(value)

    def _request(self, block):
        if block in self.pending or self.store is None:
            return
        if len(self.pending) >= 2:
            self.requested = block
            return
        self.pending.add(block)
        first, last = block * PAGE_SIZE, min((block + 1) * PAGE_SIZE, self.rows)
        positions = []
        while first < last:
            span = bisect_right(self.ends, first)
            count = min(last, self.ends[span]) - first
            start = self.spans[span][1] - (self.ends[span] - first)
            positions.extend(range(start, start + count))
            first += count
        store, channels, canceled = self.store, self.channels, self.canceled
        background(
            (canceled, block),
            lambda: None if canceled.is_set() else store._sheet_rows(channels, positions),
            self._loaded,
        )

    def _loaded(self, key, data, error):
        generation, block = key
        if generation is not self.canceled or generation.is_set():
            return
        self.pending.discard(block)
        if error:
            self.store = None
            self.failed.emit(error)
        elif data is not None:
            self.cache[block] = data
            if len(self.cache) > CACHE_PAGES:
                self.cache.popitem(last=False)
            first = self.index(block * PAGE_SIZE, 0)
            last = self.index(min((block + 1) * PAGE_SIZE, self.rows) - 1, len(self.channels) - 1)
            self.dataChanged.emit(first, last, [DISPLAY])
        requested, self.requested = self.requested, None
        if requested is not None and requested not in self.cache:
            self._request(requested)
