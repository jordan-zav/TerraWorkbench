"""Embedded TerraWorkbench dependency manager adapted from QPIP."""

from .manager import (
    activate_dependency_path,
    dependency_directory,
    dependency_status,
    inversion_supported,
    install_requirements,
)

__all__ = (
    "activate_dependency_path",
    "dependency_directory",
    "dependency_status",
    "inversion_supported",
    "install_requirements",
)
