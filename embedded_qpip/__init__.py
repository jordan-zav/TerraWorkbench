"""Embedded TerraWorkbench dependency manager adapted from QPIP."""

from .manager import (
    activate_dependency_path,
    dependency_directory,
    dependency_status,
    install_requirements,
)

__all__ = (
    "activate_dependency_path",
    "dependency_directory",
    "dependency_status",
    "install_requirements",
)
