"""Render actual widgets offscreen without controlling a user's desktop.

The caller owns QApplication and must initialize an isolated settings/profile
directory before constructing widgets. QGIS's existing Qt runtime is reused.
"""

from pathlib import Path
import time

from qgis.PyQt.QtGui import QGuiApplication


def capture_widget(widget, destination, *, width=1280, height=850):
    """Save a real widget render; refuse desktop platforms and overwrites."""
    app = QGuiApplication.instance()
    if app is None or app.platformName() != "offscreen":
        raise RuntimeError("Evidence capture requires an offscreen Qt application")
    path = Path(destination)
    if path.exists():
        raise FileExistsError(path)
    if path.suffix.lower() != ".png" or not (
        320 <= width <= 4096 and 240 <= height <= 4096
    ):
        raise ValueError("Use PNG and bounded pixel dimensions")
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.resize(width, height)
    widget.show()
    app.processEvents()
    if not widget.grab().save(str(path), "PNG"):
        raise RuntimeError("Qt could not save the widget render")
    return str(path.resolve())


def capture_workspace(
    workspace,
    database_id,
    channels,
    destination,
    *,
    timeout=30,
    filter_channel=None,
    filter_values=(),
    workspace_label=None,
):
    """Open a stored database, wait for its real preview, then capture it."""
    from .survey_workspace_dialog import SurveyWorkspaceDialog

    app = QGuiApplication.instance()
    if app is None or app.platformName() != "offscreen":
        raise RuntimeError("Evidence capture requires an offscreen Qt application")
    if not 0 < timeout <= 120:
        raise ValueError("Use a bounded positive preview timeout")
    dialog = SurveyWorkspaceDialog()
    errors = []
    dialog.fail = errors.append
    try:
        dialog.set_project(workspace, create=False)
        if workspace_label is not None:
            # Presentation alias for public evidence; never changes the store.
            dialog.path_label.setText(str(workspace_label))
        found = False
        for index in range(dialog.databases_list.count()):
            item = dialog.databases_list.item(index)
            match = item.data(256) == database_id
            item.setSelected(match)
            found |= match
        if not found:
            raise ValueError("Database not found in workspace")
        available = set()
        for index in range(dialog.channels_list.count()):
            item = dialog.channels_list.item(index)
            available.add(item.data(256))
            item.setSelected(item.data(256) in channels)
        if not set(channels).issubset(available):
            raise ValueError("Requested preview channels do not exist")
        selected_items = dialog.channels_list.selectedItems()
        if selected_items:
            dialog.channels_list.scrollToItem(selected_items[0])
        if filter_channel is not None:
            import csv
            import io

            index = dialog.filter_channel.findData(filter_channel)
            if index < 0 or not filter_values:
                raise ValueError(
                    "Select an existing filter channel and explicit values"
                )
            text = io.StringIO()
            csv.writer(text).writerow(filter_values)
            dialog.filter_channel.setCurrentIndex(index)
            dialog.filter_values.setText(text.getvalue().strip())
        dialog.preview()
        deadline = time.monotonic() + timeout
        while dialog.worker is not None:
            app.processEvents()
            if time.monotonic() >= deadline:
                # Keep the live dialog referenced until the worker completes;
                # destroying a running QThread can terminate the host process.
                app._evidence_pending_dialog = dialog
                raise TimeoutError("Database preview did not finish")
            time.sleep(0.01)
        if errors or not dialog.table.rowCount():
            raise RuntimeError("Database preview failed: " + str(errors))
        # Resolve offscreen layout before scrolling the selected channel into view.
        # Scrolling a hidden list uses provisional geometry on some Qt platforms.
        dialog.resize(1280, 850)
        dialog.show()
        app.processEvents()
        # Preview completion can rebuild the list: reacquire items after events.
        for index in range(dialog.channels_list.count()):
            item = dialog.channels_list.item(index)
            item.setSelected(item.data(256) in channels)
        selected_items = dialog.channels_list.selectedItems()
        if selected_items:
            dialog.channels_list.scrollToItem(selected_items[0])
        return capture_widget(dialog, destination)
    finally:
        if dialog.worker is None:
            dialog.close()
