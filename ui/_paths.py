"""Package resource root, independent of the UI module location."""

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
