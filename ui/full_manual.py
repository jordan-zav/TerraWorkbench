"""Local, language-aware chapter reader; usable directly through offscreen API."""

import json
from pathlib import Path

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices, QImageReader, QTextCursor, QTextOption
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QTextBrowser,
    QSizePolicy,
)

from ._paths import PLUGIN_ROOT
from .i18n import language


class ResponsiveManualBrowser(QTextBrowser):
    """Fit images to the viewport; use a legible vertical architecture on narrow screens."""

    def fit_images(self):
        if getattr(self, "_fitting_images", False):
            return
        self._fitting_images = True
        try:
            document = self.document()
            available = max(100, self.viewport().width() - 2 * document.documentMargin() - 4)
            block = document.begin()
            while block.isValid():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    if fragment.isValid() and fragment.charFormat().isImageFormat():
                        image = fragment.charFormat().toImageFormat()
                        path = Path(document.baseUrl().resolved(QUrl(image.name())).toLocalFile())
                        if path.name in ("arquitectura.svg", "arquitectura_compacta.svg"):
                            variant = "arquitectura_compacta.svg" if available < 1120 else "arquitectura.svg"
                            path = path.with_name(variant)
                        size = QImageReader(str(path)).size()
                        if size.isValid():
                            width = min(size.width(), available)
                            image.setName(QUrl.fromLocalFile(str(path)).toString())
                            image.setWidth(width)
                            image.setHeight(width * size.height() / size.width())
                            cursor = QTextCursor(document)
                            cursor.setPosition(fragment.position())
                            cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                            cursor.setCharFormat(image)
                    iterator += 1
                block = block.next()
            document.setTextWidth(self.viewport().width())
        finally:
            self._fitting_images = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_images()


class FullManualWidget(QWidget):
    """Read all 28 chapters without changing user preferences or launching apps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_chapter = "01"
        self.locale = language()
        self.current_path = None
        self.chapters = json.loads(
            (PLUGIN_ROOT / "docs/manuals/_meta/coverage.json").read_text(
                encoding="utf-8"
            )
        )
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.title = QLabel()
        self.locale_combo = QComboBox()
        for label, key in (("English", "en"), ("Español", "es"), ("Português", "pt")):
            self.locale_combo.addItem(label, key)
        self.chapter_combo = QComboBox()
        self.chapter_combo.setMinimumContentsLength(12)
        self.chapter_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.chapter_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        controls.addWidget(self.title)
        controls.addWidget(self.locale_combo)
        controls.addWidget(self.chapter_combo, 1)
        layout.addLayout(controls)
        self.browser = ResponsiveManualBrowser()
        option = self.browser.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.browser.document().setDefaultTextOption(option)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self.open_link)
        layout.addWidget(self.browser, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.locale_combo.currentIndexChanged.connect(self._language_selected)
        self.chapter_combo.currentIndexChanged.connect(self._chapter_selected)
        self.retranslate(self.locale)

    def retranslate(self, locale=None):
        self.locale = locale or language()
        self.title.setText(
            {"en": "Complete manual", "es": "Manual completo", "pt": "Manual completo"}[
                self.locale
            ]
        )
        self.note.setText(
            {
                "en": "Full chapters and editorial notes follow the selected language. API identifiers and original technical docstrings remain unchanged.",
                "es": "Los capítulos y notas editoriales siguen el idioma elegido. Los IDs de API y docstrings técnicos originales se conservan.",
                "pt": "Capítulos e notas editoriais seguem o idioma escolhido. IDs de API e docstrings técnicos originais são preservados.",
            }[self.locale]
        )
        self.locale_combo.blockSignals(True)
        self.locale_combo.setCurrentIndex(self.locale_combo.findData(self.locale))
        self.locale_combo.blockSignals(False)
        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        for chapter in self.chapters:
            key = chapter["file"][:2]
            self.chapter_combo.addItem(
                key + " · " + chapter["titles"][self.locale], key
            )
        self.chapter_combo.setCurrentIndex(
            self.chapter_combo.findData(self.current_chapter)
        )
        self.chapter_combo.blockSignals(False)
        self.set_chapter_id(self.current_chapter)

    def _language_selected(self, *_):
        self.retranslate(self.locale_combo.currentData())

    def _chapter_selected(self, *_):
        key = self.chapter_combo.currentData()
        if key:
            self.set_chapter_id(key)

    def set_chapter_id(self, chapter_id):
        chapter = next(
            (c for c in self.chapters if c["file"].startswith(str(chapter_id) + "_")),
            None,
        )
        if chapter is None:
            raise ValueError("Unknown manual chapter ID")
        self.current_chapter = str(chapter_id)
        self.chapter_combo.blockSignals(True)
        self.chapter_combo.setCurrentIndex(
            self.chapter_combo.findData(self.current_chapter)
        )
        self.chapter_combo.blockSignals(False)
        self.load_document(PLUGIN_ROOT / "docs/manuals" / self.locale / chapter["file"])

    def load_document(self, path):
        path = Path(path).resolve()
        if (
            PLUGIN_ROOT.resolve() not in path.parents
            or path.stat().st_size > 2 * 1024**2
        ):
            raise ValueError("Document outside package or above the reader byte budget")
        self.current_path = path
        self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(path.parent) + "/"))
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".md":
            self.browser.setMarkdown(text)
        else:
            self.browser.setPlainText(text)
        self.browser.fit_images()

    def open_link(self, url):
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        if url.fragment() and not url.path():
            self.browser.scrollToAnchor(url.fragment())
            return
        resolved = QUrl.fromLocalFile(str(self.current_path)).resolved(url)
        path = Path(resolved.toLocalFile()).resolve()
        if not path.is_file() or PLUGIN_ROOT.resolve() not in path.parents:
            return
        # Follow manual language links locally, without altering global settings.
        if (
            path.parent.name in ("en", "es", "pt")
            and path.parent.parent.name == "manuals"
        ):
            self.locale = path.parent.name
            if path.name[:2].isdigit():
                self.current_chapter = path.name[:2]
            self.retranslate(self.locale)
            if path.name[:2].isdigit():
                return
        self.load_document(path)
