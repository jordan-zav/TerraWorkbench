"""Small checks that do not require a running QGIS instance."""

from pathlib import Path
import configparser


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_declares_processing_provider():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "metadata.txt", encoding="utf-8")
    assert parser["general"]["hasprocessingprovider"] == "yes"
    assert parser["general"]["version"] == "0.3.0"


def test_required_plugin_files_exist():
    for name in ("__init__.py", "metadata.txt", "plugin.py", "provider.py"):
        assert (ROOT / name).is_file()
