"""Read canonical plugin metadata shared by runtime components."""

from __future__ import annotations

import configparser
from functools import lru_cache
from pathlib import Path


METADATA_PATH = Path(__file__).with_name("metadata.txt")


@lru_cache(maxsize=1)
def plugin_metadata() -> configparser.SectionProxy:
    """Return the validated ``[general]`` metadata section."""
    parser = configparser.ConfigParser(interpolation=None)
    with METADATA_PATH.open(encoding="utf-8") as metadata_file:
        parser.read_file(metadata_file)
    if "general" not in parser:
        raise RuntimeError("metadata.txt does not contain a [general] section")
    return parser["general"]


def plugin_version() -> str:
    """Return the single canonical TerraWorkbench version."""
    version = plugin_metadata().get("version", "").strip()
    if not version:
        raise RuntimeError("metadata.txt does not define a plugin version")
    return version
