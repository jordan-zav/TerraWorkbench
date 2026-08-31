"""Processing provider for TerraWorkbench."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .metadata_utils import plugin_version
from .algorithms.bouguer import BouguerCorrectionAlgorithm
from .algorithms.gravity_corrections import (
    AiryIsostaticAnomalyAlgorithm,
    AiryMohoAlgorithm,
    CompleteBouguerAnomalyAlgorithm,
    CurvatureCorrectionAlgorithm,
    FreeAirAnomalyAlgorithm,
    FreeAirCorrectionAlgorithm,
    LatitudeCorrectionAlgorithm,
    NormalGravityAlgorithm,
    SimpleBouguerAnomalyAlgorithm,
    TerrainCorrectionAlgorithm,
)
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
    GravityUpwardContinuationAlgorithm,
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
    MagneticUpwardContinuationAlgorithm,
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
    FftDerivativeEastingAlgorithm,
    FftDerivativeNorthingAlgorithm,
    FftDerivativeUpwardAlgorithm,
    HorizontalIntegrationEastingAlgorithm,
    HorizontalIntegrationNorthingAlgorithm,
    IdealBandPassAlgorithm,
    IdealBandRejectAlgorithm,
    VerticalIntegrationAlgorithm,
    MagneticPseudogravityAlgorithm,
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
from .algorithms.radiometry import (
    RadiometryBackgroundAlgorithm,
    RadiometryCalibrationAlgorithm,
    RadiometryDeadTimeAlgorithm,
    RadiometryDespikeAlgorithm,
    RadiometryDoseRateAlgorithm,
    RadiometryFParameterAlgorithm,
    RadiometryHeightAlgorithm,
    RadiometryQcAlgorithm,
    RadiometryRatioAlgorithm,
    RadiometrySpectralUnmixAlgorithm,
    RadiometryTernaryAlgorithm,
)
from .algorithms.radiometric_survey import RadiometricSurveyCorrectionAlgorithm
from .algorithms.survey_corrections import (
    GravitySurveyCorrectionAlgorithm,
    MagneticSurveyCorrectionAlgorithm,
)
from .algorithms.equivalent_sources import EquivalentSourceContinuationAlgorithm


class TerraWorkbenchProvider(QgsProcessingProvider):
    """Expose gravity and magnetic algorithms through QGIS Processing."""

    def loadAlgorithms(self):
        self.addAlgorithm(GravDxAlgorithm())
        self.addAlgorithm(GravDyAlgorithm())
        self.addAlgorithm(GravDzAlgorithm())
        self.addAlgorithm(GravDz2Algorithm())
        self.addAlgorithm(GravityUpwardContinuationAlgorithm())
        self.addAlgorithm(GravGaussianRegionalAlgorithm())
        self.addAlgorithm(GravResidualAlgorithm())
        self.addAlgorithm(GravThdrAlgorithm())
        self.addAlgorithm(GravTiltAlgorithm())
        self.addAlgorithm(GravTotalGradientAmplitudeAlgorithm())
        self.addAlgorithm(DxAlgorithm())
        self.addAlgorithm(DyAlgorithm())
        self.addAlgorithm(DzAlgorithm())
        self.addAlgorithm(Dz2Algorithm())
        self.addAlgorithm(MagneticUpwardContinuationAlgorithm())
        self.addAlgorithm(ResidualEnhancementAlgorithm())
        self.addAlgorithm(ThdrAlgorithm())
        self.addAlgorithm(TiltAlgorithm())
        self.addAlgorithm(DirectionalHorizontalGradientAlgorithm())
        self.addAlgorithm(AnalyticSignalAlgorithm())
        self.addAlgorithm(TdxAlgorithm())
        self.addAlgorithm(ThetaMapAlgorithm())
        self.addAlgorithm(BouguerCorrectionAlgorithm())
        self.addAlgorithm(NormalGravityAlgorithm())
        self.addAlgorithm(LatitudeCorrectionAlgorithm())
        self.addAlgorithm(FreeAirCorrectionAlgorithm())
        self.addAlgorithm(FreeAirAnomalyAlgorithm())
        self.addAlgorithm(CurvatureCorrectionAlgorithm())
        self.addAlgorithm(SimpleBouguerAnomalyAlgorithm())
        self.addAlgorithm(TerrainCorrectionAlgorithm())
        self.addAlgorithm(CompleteBouguerAnomalyAlgorithm())
        self.addAlgorithm(AiryMohoAlgorithm())
        self.addAlgorithm(AiryIsostaticAnomalyAlgorithm())
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
        self.addAlgorithm(FftDerivativeEastingAlgorithm())
        self.addAlgorithm(FftDerivativeNorthingAlgorithm())
        self.addAlgorithm(FftDerivativeUpwardAlgorithm())
        self.addAlgorithm(HorizontalIntegrationEastingAlgorithm())
        self.addAlgorithm(HorizontalIntegrationNorthingAlgorithm())
        self.addAlgorithm(VerticalIntegrationAlgorithm())
        self.addAlgorithm(MagneticPseudogravityAlgorithm())
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
        self.addAlgorithm(RadiometryRatioAlgorithm())
        self.addAlgorithm(RadiometryTernaryAlgorithm())
        self.addAlgorithm(RadiometryDoseRateAlgorithm())
        self.addAlgorithm(RadiometryFParameterAlgorithm())
        self.addAlgorithm(RadiometryQcAlgorithm())
        self.addAlgorithm(RadiometryDespikeAlgorithm())
        self.addAlgorithm(RadiometryDeadTimeAlgorithm())
        self.addAlgorithm(RadiometryBackgroundAlgorithm())
        self.addAlgorithm(RadiometryHeightAlgorithm())
        self.addAlgorithm(RadiometryCalibrationAlgorithm())
        self.addAlgorithm(RadiometrySpectralUnmixAlgorithm())
        self.addAlgorithm(RadiometricSurveyCorrectionAlgorithm())
        self.addAlgorithm(MagneticSurveyCorrectionAlgorithm())
        self.addAlgorithm(GravitySurveyCorrectionAlgorithm())
        self.addAlgorithm(EquivalentSourceContinuationAlgorithm())

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
