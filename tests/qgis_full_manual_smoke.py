"""Read all locales, local links and packaged figures without desktop control."""

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.PyQt.QtCore import QSettings, QCoreApplication, QUrl
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QFont, QFontDatabase
from TerraWorkbench.ui.full_manual import FullManualWidget
from TerraWorkbench.ui.i18n import set_language, language
from TerraWorkbench.ui._paths import PLUGIN_ROOT


def main():
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    folder = Path(tempfile.mkdtemp(prefix="tw_manual_"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(folder))
    QCoreApplication.setOrganizationName("TerraWorkbenchManualTest")
    QCoreApplication.setApplicationName("Offscreen")
    app = QApplication([])
    if os.name == "nt" and "WINDIR" in os.environ:
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf"))
    app.setFont(QFont("Arial", 10))
    set_language("es")
    reader = FullManualWidget()
    assert reader.chapter_combo.count() == 28
    for locale in ("en", "pt", "es"):
        reader.retranslate(locale)
        for chapter in reader.chapters:
            reader.set_chapter_id(chapter["file"][:2])
            assert reader.current_path.parent.name == locale
            assert reader.browser.toPlainText().strip()
        reader.set_chapter_id("01")
        for width in (800, 950, 1400):
            reader.resize(width, 1000)
            reader.show()
            app.processEvents()
            assert reader.width() == width
            assert reader.browser.horizontalScrollBar().maximum() == 0
            reader.grab().save(str(folder / f"manual-{locale}-{width}.png"))
        assert language() == "es", "Reader must not mutate global preferences"
    reader.set_chapter_id("01")
    reader.open_link(QUrl("../pt/01_inicio.md"))
    assert reader.locale == "pt" and reader.current_chapter == "01"
    reader.set_chapter_id("28")
    assert reader.chapter_combo.currentData() == "28"
    reader.open_link(QUrl("README.md"))
    reader.open_link(QUrl("../en/README.md"))
    assert reader.locale_combo.currentData() == "en"
    assert reader.current_path.name == "README.md"
    reader.open_link(QUrl("../pt/fuentes.md"))
    assert reader.locale_combo.currentData() == "pt"
    assert reader.current_path.name == "fuentes.md"
    assert language() == "es"
    before = reader.current_path
    reader.open_link(QUrl("../../../../../../missing.md"))
    assert reader.current_path == before
    try:
        reader.load_document(folder / "outside.md")
    except ValueError:
        pass
    else:
        raise AssertionError("Reader accepted document outside package")
    reader.load_document(PLUGIN_ROOT / "docs/reference/api/pt.md")
    assert "Referência de API" in reader.browser.toPlainText()
    assert "adaptive_terrain" in reader.browser.toPlainText()
    reader.close()
    app.processEvents()
    print(
        "Full manual: 84 chapter reads, language links, API links and settings isolation passed"
    )


if __name__ == "__main__":
    main()
