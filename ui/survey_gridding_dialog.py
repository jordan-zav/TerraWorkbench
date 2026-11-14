"""Interactive retry for the minimum-curvature node limit."""

from processing.gui.AlgorithmDialog import AlgorithmDialog
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QMessageBox

from .i18n import translate


class SurveyGriddingDialog(AlgorithmDialog):
    def finish(self, successful, result, context, feedback, in_place=False):
        algorithm = self.algorithm()
        prefix = translate(algorithm.NODE_LIMIT_MESSAGE).split("{nodes:,}", 1)[0]
        limit_error = next(
            (line.strip() for line in feedback.textLog().splitlines()
             if line.strip().startswith(prefix)),
            None,
        ) if not successful else None
        super().finish(successful, result, context, feedback, in_place)
        if limit_error:
            # QGIS clears the previous run's context after finish returns.
            QTimer.singleShot(0, lambda: self._offer_large_grid_retry(limit_error))

    def _offer_large_grid_retry(self, message):
        if not self.isVisible():
            return
        prompt = QMessageBox(self)
        prompt.setWindowTitle(self.algorithm().displayName())
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setText(message)
        prompt.setInformativeText(
            translate("A large grid can require substantially more memory and time.")
        )
        retry = prompt.addButton(
            translate("Continue only this time"), QMessageBox.ButtonRole.AcceptRole
        )
        cancel = prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(cancel)
        prompt.exec()
        if prompt.clickedButton() is retry:
            key = self.algorithm().ALLOW_LARGE_GRID
            self.setParameters({key: True})
            try:
                self.runAlgorithm()
            finally:
                self.setParameters({key: False})
