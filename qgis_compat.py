"""Compatibility values shared by supported QGIS 3 and QGIS 4 releases."""

from qgis.core import (
    Qgis,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterNumber,
)


def qt_enum(container, scoped_name, member_name):
    """Return a Qt5 unscoped or Qt6 scoped enum member."""
    scoped_enum = getattr(container, scoped_name, None)
    if scoped_enum is not None:
        return getattr(scoped_enum, member_name)
    return getattr(container, member_name)


def processing_parameter_is_optional(parameter):
    """Return whether a Processing parameter has the optional flag."""
    scoped_enum = getattr(Qgis, "ProcessingParameterFlag", None)
    if scoped_enum is not None:
        optional_flag = scoped_enum.Optional
    else:
        optional_flag = QgsProcessingParameterDefinition.FlagOptional
    return bool(parameter.flags() & optional_flag)


def _processing_number_type(name):
    scoped_enum = getattr(Qgis, "ProcessingNumberParameterType", None)
    if scoped_enum is not None:
        return getattr(scoped_enum, name)
    return getattr(QgsProcessingParameterNumber, name)


PROCESSING_NUMBER_DOUBLE = _processing_number_type("Double")
PROCESSING_NUMBER_INTEGER = _processing_number_type("Integer")
