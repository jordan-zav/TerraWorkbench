"""Old public import names resolve lazily to the organized implementations."""

from pathlib import Path
import subprocess
import sys

import pytest
from zipfile import ZipFile

from scripts import package_plugin

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("from_archive", [False, True])
def test_plugin_aliases_are_lazy_and_preserve_canonical_module_identity(
    from_archive, tmp_path, monkeypatch
):
    parent = ROOT.parent
    if from_archive:
        monkeypatch.setattr(package_plugin, "DIST_DIR", tmp_path / "dist")
        archive = package_plugin.build_archive()
        parent = tmp_path / "installed"
        with ZipFile(archive) as bundle:
            bundle.extractall(parent)
    code = """
import importlib, importlib.util, pathlib, sys
sys.path.insert(0, sys.argv[1])
class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qgis', 'PyQt5', 'PyQt6', 'PySide6'}:
            raise AssertionError('Unexpected host import: ' + fullname)
sys.meta_path.insert(0, BlockQt())
source = pathlib.Path(sys.argv[2])
if source.name != 'TerraWorkbench':
    spec = importlib.util.spec_from_file_location('TerraWorkbench', source / '__init__.py',
                                                  submodule_search_locations=[str(source)])
    package = importlib.util.module_from_spec(spec)
    sys.modules['TerraWorkbench'] = package
    spec.loader.exec_module(package)
import TerraWorkbench
assert 'numpy' not in sys.modules
assert callable(TerraWorkbench.classFactory)
for old, new in [('basic_processing','compat.basic_processing'),
                 ('spectral','compat.spectral'),('text_import','compat.text_import'),
                 ('metadata_utils','qgis_plugin.metadata_utils'),
                 ('core_parameter_schema','ui.core_parameter_schema')]:
    legacy=importlib.import_module('TerraWorkbench.'+old)
    canonical=importlib.import_module('TerraWorkbench.'+new)
    assert legacy is canonical
    assert canonical.__spec__.name == 'TerraWorkbench.'+new
assert TerraWorkbench.metadata_utils.plugin_version()
"""
    source = parent / "TerraWorkbench" if from_archive else ROOT
    subprocess.run([sys.executable, "-c", code, str(parent), str(source)], check=True)


def test_short_legacy_names_are_explicitly_enabled_without_duplicate_modules():
    code = """
import importlib, sys
sys.path.insert(0, sys.argv[1])
from compat.redirects import install_legacy_imports
first=install_legacy_imports()
assert install_legacy_imports() is first
for name in ['basic_processing','spectral','survey_store','text_import']:
    legacy=importlib.import_module(name)
    assert legacy is importlib.import_module('compat.'+name)
    assert legacy.__spec__.name == 'compat.'+name
assert 'qgis' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code, str(ROOT)], check=True)
