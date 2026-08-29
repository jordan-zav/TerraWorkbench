"""Validate and package TerraWorkbench for the official QGIS repository."""

from __future__ import annotations

import argparse
import ast
import configparser
import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "TerraWorkbench"
METADATA_PATH = ROOT / "metadata.txt"
DIST_DIR = ROOT / "dist"
MAX_PACKAGE_BYTES = 25 * 1024 * 1024
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")

REQUIRED_METADATA = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
)

ROOT_FILES = (
    "__init__.py",
    "metadata.txt",
    "metadata_utils.py",
    "qgis_compat.py",
    "plugin.py",
    "provider.py",
    "raster_io.py",
    "spectral.py",
    "line_processing.py",
    "microlevel.py",
    "inversion_core.py",
    "dependencies.py",
    "dependency_dialog.py",
    "workflow_dock.py",
    "data_import.py",
    "geosoft_runtime.py",
    "geosoft_bridge.py",
    "icon.svg",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "requirements-inversion.txt",
    "THIRD_PARTY_LICENSES.md",
)

DOC_FILES = (
    "docs/filter-stack.png",
)


def load_metadata() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    with METADATA_PATH.open(encoding="utf-8") as metadata_file:
        parser.read_file(metadata_file)
    return parser


def current_version() -> str:
    parser = load_metadata()
    if "general" not in parser:
        return ""
    return parser["general"].get("version", "").strip()


def update_version(version: str) -> None:
    content = METADATA_PATH.read_text(encoding="utf-8")
    updated, replacements = re.subn(
        r"(?im)^version=.*$",
        f"version={version}",
        content,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("metadata.txt must contain exactly one version field")
    with METADATA_PATH.open("w", encoding="utf-8", newline="\n") as metadata_file:
        metadata_file.write(updated)


def package_files() -> list[Path]:
    files = [ROOT / relative_path for relative_path in ROOT_FILES]
    files.extend(ROOT / relative_path for relative_path in DOC_FILES)
    files.extend(sorted((ROOT / "algorithms").glob("*.py")))
    return files


def validate_source() -> list[str]:
    errors: list[str] = []
    try:
        metadata = load_metadata()
    except (OSError, configparser.Error) as error:
        return [f"metadata.txt could not be read: {error}"]

    if "general" not in metadata:
        return ["metadata.txt is missing the [general] section"]

    general = metadata["general"]
    for key in REQUIRED_METADATA:
        if not general.get(key, "").strip():
            errors.append(f"metadata.txt is missing required field: {key}")

    version = general.get("version", "").strip()
    if version and VERSION_PATTERN.fullmatch(version) is None:
        errors.append(f"invalid semantic version: {version}")
    if general.get("plugin_dependencies", "").strip() != "qpip":
        errors.append("plugin_dependencies must declare qpip")
    if "requirements.txt" not in general.get("about", ""):
        errors.append("about must explain the external requirements.txt dependency")
    if general.get("qgisMaximumVersion", "").strip() != "3.99":
        errors.append(
            "qgisMaximumVersion must remain 3.99 until QGIS 4 runtime tests exist"
        )

    for source in package_files():
        if not source.is_file():
            errors.append(
                f"required package file is missing: {source.relative_to(ROOT)}"
            )
        elif source.suffix == ".py":
            try:
                ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            except (OSError, SyntaxError, UnicodeError) as error:
                errors.append(
                    f"invalid Python source {source.relative_to(ROOT)}: {error}"
                )

    return errors


def validate_archive(archive: Path, expected_version: str) -> list[str]:
    errors: list[str] = []
    expected_entries = {
        str(PurePosixPath(PLUGIN_ID) / source.relative_to(ROOT).as_posix())
        for source in package_files()
    }
    with ZipFile(archive) as bundle:
        entries = set(bundle.namelist())
        if entries != expected_entries:
            missing = sorted(expected_entries - entries)
            unexpected = sorted(entries - expected_entries)
            if missing:
                errors.append(f"archive is missing files: {', '.join(missing)}")
            if unexpected:
                errors.append(
                    f"archive contains unexpected files: {', '.join(unexpected)}"
                )

        metadata_entry = f"{PLUGIN_ID}/metadata.txt"
        packaged_parser = configparser.ConfigParser(interpolation=None)
        packaged_parser.read_string(bundle.read(metadata_entry).decode("utf-8"))
        packaged_version = packaged_parser["general"].get("version", "").strip()
        if packaged_version != expected_version:
            errors.append(
                f"archive metadata version {packaged_version!r} does not match {expected_version!r}"
            )

    if archive.stat().st_size > MAX_PACKAGE_BYTES:
        errors.append("archive exceeds the official QGIS 25 MB package limit")
    return errors


def build_archive() -> Path:
    version = current_version()
    DIST_DIR.mkdir(exist_ok=True)
    archive = DIST_DIR / f"{PLUGIN_ID}-{version}.zip"
    if archive.exists():
        archive.unlink()

    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for source in package_files():
            archive_name = (
                PurePosixPath(PLUGIN_ID) / source.relative_to(ROOT).as_posix()
            )
            bundle.write(source, str(archive_name))
    return archive


def fail(errors: list[str]) -> None:
    print("\nERROR: release validation failed:", file=sys.stderr)
    for error in errors:
        print(f" - {error}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true", help="prompt for version")
    parser.add_argument("--version", help="set the package version non-interactively")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate source without creating an archive",
    )
    args = parser.parse_args()

    version = args.version.strip() if args.version else current_version()
    if args.interactive:
        entered = input(f"Version [{version}]: ").strip()
        if entered:
            version = entered
    if VERSION_PATTERN.fullmatch(version) is None:
        fail([f"invalid semantic version: {version!r}"])
    if version != current_version():
        update_version(version)

    errors = validate_source()
    if errors:
        fail(errors)
    print(f"OK: source and metadata validated for TerraWorkbench {version}.")

    if args.check_only:
        return

    archive = build_archive()
    errors = validate_archive(archive, version)
    if errors:
        archive.unlink(missing_ok=True)
        fail(errors)
    print(f"OK: {archive} ({archive.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
