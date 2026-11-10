"""The core must run without the plugin host, even when QGIS is installed."""
import ast
import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted(p.stem for p in (ROOT / "terraworkbench_core").glob("*.py") if p.stem != "__init__")


def test_legacy_imports_share_implementation():
    # Only historical top-level modules promise legacy compatibility.
    for name in (n for n in MODULES if (ROOT/"compat"/(n+".py")).is_file()
                 and "Compatibility import" in (ROOT/"compat"/(n+".py")).read_text(encoding="utf-8")):
        legacy = importlib.import_module("compat." + name)
        core = importlib.import_module("terraworkbench_core." + name)
        for key, value in vars(core).items():
            if callable(value) and not key.startswith("__"):
                assert getattr(legacy, key) is value


def test_core_has_no_host_imports():
    forbidden = {"qgis", "PyQt5", "PyQt6", "PySide6", "TerraWorkbench", "dependencies", "ui"}
    for path in (ROOT / "terraworkbench_core").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert not any(alias.name.split(".")[0] in forbidden for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden
                assert node.level <= 1


def test_plugin_archive_bundles_shared_core(tmp_path, monkeypatch):
    from scripts import package_plugin
    monkeypatch.setattr(package_plugin, "DIST_DIR", tmp_path)
    archive = package_plugin.build_archive()
    assert not package_plugin.validate_archive(archive, package_plugin.current_version())
    from zipfile import ZipFile
    with ZipFile(archive) as bundle:
        for name in ["__init__", *MODULES]:
            assert "TerraWorkbench/terraworkbench_core/" + name + ".py" in bundle.namelist()


def test_core_import_and_calculation_without_qgis():
    code = '''
import importlib, sys
class BlockHost:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qgis', 'PyQt5', 'PyQt6', 'PySide6', 'TerraWorkbench'}:
            raise AssertionError('Host import: ' + fullname)
sys.meta_path.insert(0, BlockHost())
for name in MODULES:
    importlib.import_module('terraworkbench_core.' + name)
import numpy as np
from terraworkbench_core.magnetic_pipeline import MagneticPipelineOptions, magnetic_grid_products
from terraworkbench_core.gravity_corrections import normal_gravity_grs80
assert abs(normal_gravity_grs80(0.) - 978032.67715) < 1e-8
values = np.arange(64.).reshape(8,8)
products, recipe = magnetic_grid_products(values, (1.,1.), MagneticPipelineOptions(90.,0.))
assert len(products) == 14 and np.isfinite(products['RTP']).all()
'''
    subprocess.run([sys.executable, "-c", "MODULES=" + repr(MODULES) + "\n" + code], cwd=ROOT, check=True)
