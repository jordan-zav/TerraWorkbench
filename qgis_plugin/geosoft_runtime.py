"""Discover an optional installed Geosoft Desktop runtime on Windows."""

from __future__ import annotations

from dataclasses import dataclass
import os
import json
from pathlib import Path


@dataclass(frozen=True)
class GeosoftRuntime:
    root: Path
    omscore: Path | None
    python: Path
    standalone: bool = False
    redist: Path | None = None


SEEQUENT_CONNECTOR_URL = "https://downloads.seequent.com/Geosoft/SeequentConnector.zip"
SEEQUENT_ID_URL = "https://www.seequent.com/help-support/seequent-id/"
GEOSOFT_VIEWER_URL = "https://www.seequent.com/products-solutions/geosoft-viewer/"


def managed_gx_runtime(dependencies):
    """Find the manager-prepared native runtime without using a desktop install."""
    folder = Path(dependencies) / "_gx_runtime"
    try:
        marker = json.loads((folder / "installed.json").read_text(encoding="utf-8"))
        from .gx_runtime_setup import GX_REDIST_SHA256

        if marker.get("archive_sha256") != GX_REDIST_SHA256:
            return None
        root = (folder / marker["root"]).resolve()
        if folder.resolve() not in root.parents:
            return None
        return root if (root / "bin/geodist.dll").is_file() else None
    except (OSError, ValueError, KeyError):
        return None


def find_seequent_connector():
    """Detect documented Connector locations without launching external software."""
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roots = [local / name for name in ("Geosoft_Inc/Geosoft Connect", "Geosoft_Inc/Seequent Connector",
                                       "Seequent/Seequent Connector", "Seequent/Seequent Connect")]
    roots += [p / name for p in _program_roots() for name in (
        "Geosoft/Geosoft Connect", "Seequent/Seequent Connector", "Seequent/Seequent Connect",
        "Geosoft/Seequent Connector")]
    for root in roots:
        for name in ("GeosoftConnect.exe", "SeequentConnector.exe", "SeequentConnect.exe"):
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def gdb_prerequisite_notice(locale="en"):
    """Explain the requirements for direct conversion and the open-file alternative."""
    messages = {
        "en": (
            "GDB conversion requires Geosoft Connect with a free Seequent ID account. "
            "If your account belongs to an organization with licences, a checkout window may appear. "
            "Accept it (While app is running) and the checkout ends when GX closes. Oasis montaj is not required. "
            "If you prefer to work without a Seequent account, import XYZ or CSV."
        ),
        "es": (
            "La conversión de GDB requiere Geosoft Connect con una cuenta Seequent ID (gratuita). "
            "Si tu cuenta pertenece a una organización con licencias, puede aparecer una ventana de checkout. "
            "Acéptala (While app is running). La reserva se libera al cerrar GX. No hace falta Oasis montaj. "
            "Si prefieres trabajar sin una cuenta Seequent, importa XYZ o CSV."
        ),
        "pt": (
            "A conversão de GDB requer Geosoft Connect com uma conta Seequent ID gratuita. "
            "Se sua conta pertencer a uma organização com licenças, pode aparecer uma janela de checkout. "
            "Aceite (While app is running). A reserva é liberada ao fechar o GX. O Oasis montaj é dispensável. "
            "Se preferir trabalhar sem uma conta Seequent, importe XYZ ou CSV."
        ),
    }
    return messages.get(locale, messages["en"]) + "\n\n" + "\n".join(
        (SEEQUENT_ID_URL, GEOSOFT_VIEWER_URL)
    )


def conversion_notice(locale="en", *, connector_missing=False):
    """Include the official Connector download when it is missing."""
    value = gdb_prerequisite_notice(locale)
    if connector_missing:
        value += "\n\n" + {
            "en": "Seequent Connector was not found in its standard locations. If GX requires sign-in, download it from the official link below. It is only needed for conversion, never to open converted archives.",
            "es": "No se encontró Seequent Connector en sus ubicaciones habituales. Si GX requiere iniciar sesión, se descarga desde el enlace oficial indicado. Solo hace falta para convertir, nunca para abrir copias convertidas.",
            "pt": "Seequent Connector não foi encontrado nos locais habituais. Se GX exigir autenticação, ele pode ser obtido pelo link oficial abaixo. Só é necessário para converter, nunca para abrir cópias convertidas.",
        }.get(locale, "Seequent Connector was not found.") + "\n" + SEEQUENT_CONNECTOR_URL
    return value


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
