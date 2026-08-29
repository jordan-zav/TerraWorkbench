"""Compatibility values shared by supported QGIS releases."""

from qgis.PyQt.QtCore import QMetaType, QVariant

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


def _field_type(name):
    """Return the non-deprecated field type supported by this QGIS version."""
    if Qgis.QGIS_VERSION_INT >= 33800:
        scoped_enum = getattr(QMetaType, "Type", QMetaType)
        return getattr(scoped_enum, name)
    legacy_names = {
        "QString": "String",
        "Double": "Double",
        "Int": "Int",
        "Bool": "Bool",
    }
    return getattr(QVariant, legacy_names[name])


FIELD_TYPE_STRING = _field_type("QString")
FIELD_TYPE_DOUBLE = _field_type("Double")
FIELD_TYPE_INTEGER = _field_type("Int")
FIELD_TYPE_BOOL = _field_type("Bool")
