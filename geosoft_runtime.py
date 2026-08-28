"""Discover an optional licensed Geosoft/Oasis montaj runtime on Windows."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class GeosoftRuntime:
    root: Path
    omscore: Path
    python: Path


def validate_geosoft_location(location):
    """Resolve OMSCORE and bundled Python from an exe, bin, or install folder."""
    if not location:
        return None
    location = Path(location).expanduser()
    candidates = []
    if location.is_file() and location.name.casefold() == "omscore.exe":
        candidates.append(location)
    elif location.is_dir():
        candidates.extend(
            (
                location / "omscore.exe",
                location / "bin" / "omscore.exe",
                location / "Desktop Applications" / "bin" / "omscore.exe",
            )
        )
        candidates.extend(location.glob("**/bin/omscore.exe"))
    for omscore in candidates:
        if not omscore.is_file():
            continue
        application_root = (
            omscore.parent.parent
            if omscore.parent.name.casefold() == "bin"
            else omscore.parent
        )
        python = application_root / "python" / "python.exe"
        if python.is_file():
            return GeosoftRuntime(application_root, omscore, python)
    return None


def _program_roots():
    program_roots = []
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value and Path(value) not in program_roots:
            program_roots.append(Path(value))
    return program_roots


def standard_geosoft_locations():
    """Return conventional vendor locations without assuming a drive letter."""
    for program_root in _program_roots():
        yield program_root / "Geosoft" / "Desktop Applications"
        yield program_root / "Seequent" / "Desktop Applications"


def find_geosoft_runtime(configured_location=None):
    """Use standard path, saved path, then a bounded vendor-folder scan."""
    checked = set()
    for location in (*standard_geosoft_locations(), configured_location):
        if not location:
            continue
        key = str(location).casefold()
        if key in checked:
            continue
        checked.add(key)
        runtime = validate_geosoft_location(location)
        if runtime:
            return runtime

    for program_root in _program_roots():
        for vendor_name in ("Geosoft", "Seequent"):
            vendor_root = program_root / vendor_name
            if not vendor_root.is_dir():
                continue
            for omscore in vendor_root.glob("**/bin/omscore.exe"):
                runtime = validate_geosoft_location(omscore)
                if runtime:
                    return runtime
    return None
