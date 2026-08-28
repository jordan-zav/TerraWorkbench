"""Processing provider for TerraWorkbench."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .metadata_utils import plugin_version
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
    DirectionalHorizontalGradientAlgorithm,
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
from .algorithms.spectral_filters import (
    ButterworthBandPassAlgorithm,
    ButterworthHighPassAlgorithm,
    ButterworthLowPassAlgorithm,
    ButterworthNotchAlgorithm,
    CosineRolloffHighPassAlgorithm,
    CosineRolloffLowPassAlgorithm,
    DirectionalCosinePassAlgorithm,
    DirectionalCosineRejectAlgorithm,
    DownwardContinuationAlgorithm,
    HorizontalIntegrationEastingAlgorithm,
    HorizontalIntegrationNorthingAlgorithm,
    IdealBandPassAlgorithm,
    IdealBandRejectAlgorithm,
    VerticalIntegrationAlgorithm,
)
from .algorithms.magnetic_transforms import (
    FieldDirectionTransformAlgorithm,
    ReductionToEquatorAlgorithm,
    ReductionToPoleIgrfAlgorithm,
)
from .algorithms.survey_gridding import SurveyPointGriddingAlgorithm
from .algorithms.line_leveling import CrossoverLevelingAlgorithm
from .algorithms.microleveling import MicrolevelingAlgorithm
from .algorithms.inversion import (
    GravityDensityInversionAlgorithm,
    JointGravityMagneticInversionAlgorithm,
    MagneticSusceptibilityInversionAlgorithm,
    MagneticVectorInversionAlgorithm,
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
        self.addAlgorithm(DirectionalHorizontalGradientAlgorithm())
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
        self.addAlgorithm(ButterworthLowPassAlgorithm())
        self.addAlgorithm(ButterworthHighPassAlgorithm())
        self.addAlgorithm(ButterworthBandPassAlgorithm())
        self.addAlgorithm(ButterworthNotchAlgorithm())
        self.addAlgorithm(IdealBandPassAlgorithm())
        self.addAlgorithm(IdealBandRejectAlgorithm())
        self.addAlgorithm(CosineRolloffLowPassAlgorithm())
        self.addAlgorithm(CosineRolloffHighPassAlgorithm())
        self.addAlgorithm(DirectionalCosinePassAlgorithm())
        self.addAlgorithm(DirectionalCosineRejectAlgorithm())
        self.addAlgorithm(DownwardContinuationAlgorithm())
        self.addAlgorithm(HorizontalIntegrationEastingAlgorithm())
        self.addAlgorithm(HorizontalIntegrationNorthingAlgorithm())
        self.addAlgorithm(VerticalIntegrationAlgorithm())
        self.addAlgorithm(ReductionToPoleIgrfAlgorithm())
        self.addAlgorithm(ReductionToEquatorAlgorithm())
        self.addAlgorithm(FieldDirectionTransformAlgorithm())
        self.addAlgorithm(SurveyPointGriddingAlgorithm())
        self.addAlgorithm(CrossoverLevelingAlgorithm())
        self.addAlgorithm(MicrolevelingAlgorithm())
        self.addAlgorithm(GravityDensityInversionAlgorithm())
        self.addAlgorithm(MagneticSusceptibilityInversionAlgorithm())
        self.addAlgorithm(MagneticVectorInversionAlgorithm())
        self.addAlgorithm(JointGravityMagneticInversionAlgorithm())

    def id(self):
        return "terraworkbench"

    def name(self):
        return "TerraWorkbench"

    def longName(self):
        return "TerraWorkbench — Geophysical Processing"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.svg"))

    def versionInfo(self):
        return plugin_version()
