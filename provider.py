"""Processing provider for TerraWorkbench."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithms.bouguer import BouguerCorrectionAlgorithm
from .algorithms.gravity_filters import (
    GravDxAlgorithm,
    GravDyAlgorithm,
    GravDz2Algorithm,
    GravDzAlgorithm,
    GravGaussianRegionalAlgorithm,
    GravResidualAlgorithm,
    GravThdrAlgorithm,
    GravTiltAlgorithm,
    GravTotalGradientAmplitudeAlgorithm,
    GravUc500Algorithm,
)
from .algorithms.magnetic_filters import (
    AnalyticSignalAlgorithm,
    Directional45Algorithm,
    DxAlgorithm,
    DyAlgorithm,
    Dz2Algorithm,
    DzAlgorithm,
    ResidualEnhancementAlgorithm,
    TdxAlgorithm,
    ThetaMapAlgorithm,
    ThdrAlgorithm,
    TiltAlgorithm,
    Uc500Algorithm,
)
from .algorithms.transforms import (
    DerivativeEastingAlgorithm,
    DerivativeNorthingAlgorithm,
    DerivativeUpwardAlgorithm,
    GaussianHighPassAlgorithm,
    GaussianLowPassAlgorithm,
    ReductionToPoleAlgorithm,
    UpwardContinuationAlgorithm,
)


class TerraWorkbenchProvider(QgsProcessingProvider):
    """Expose gravity and magnetic algorithms through QGIS Processing."""

    def loadAlgorithms(self):
        self.addAlgorithm(GravDxAlgorithm())
        self.addAlgorithm(GravDyAlgorithm())
        self.addAlgorithm(GravDzAlgorithm())
        self.addAlgorithm(GravDz2Algorithm())
        self.addAlgorithm(GravUc500Algorithm())
        self.addAlgorithm(GravGaussianRegionalAlgorithm())
        self.addAlgorithm(GravResidualAlgorithm())
        self.addAlgorithm(GravThdrAlgorithm())
        self.addAlgorithm(GravTiltAlgorithm())
        self.addAlgorithm(GravTotalGradientAmplitudeAlgorithm())
        self.addAlgorithm(DxAlgorithm())
        self.addAlgorithm(DyAlgorithm())
        self.addAlgorithm(DzAlgorithm())
        self.addAlgorithm(Dz2Algorithm())
        self.addAlgorithm(Uc500Algorithm())
        self.addAlgorithm(ResidualEnhancementAlgorithm())
        self.addAlgorithm(ThdrAlgorithm())
        self.addAlgorithm(TiltAlgorithm())
        self.addAlgorithm(Directional45Algorithm())
        self.addAlgorithm(AnalyticSignalAlgorithm())
        self.addAlgorithm(TdxAlgorithm())
        self.addAlgorithm(ThetaMapAlgorithm())
        self.addAlgorithm(BouguerCorrectionAlgorithm())
        self.addAlgorithm(UpwardContinuationAlgorithm())
        self.addAlgorithm(GaussianLowPassAlgorithm())
        self.addAlgorithm(GaussianHighPassAlgorithm())
        self.addAlgorithm(ReductionToPoleAlgorithm())
        self.addAlgorithm(DerivativeEastingAlgorithm())
        self.addAlgorithm(DerivativeNorthingAlgorithm())
        self.addAlgorithm(DerivativeUpwardAlgorithm())

    def id(self):
        return "terraworkbench"

    def name(self):
        return "TerraWorkbench"

    def longName(self):
        return "TerraWorkbench — Geophysical Processing"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.svg"))

    def versionInfo(self):
        return "0.3.0"
