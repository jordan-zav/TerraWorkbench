"""Optional survey table packages must not prevent minimal Core discovery."""

from pathlib import Path
import subprocess
import sys


def test_all_core_modules_import_without_optional_table_and_crs_packages():
    code = """
import importlib, pkgutil, sys
sys.path.insert(0, sys.argv[1])
class BlockOptional:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pandas', 'pyproj', 'shapely'}:
            raise ModuleNotFoundError('Optional dependency blocked: ' + fullname)
sys.meta_path.insert(0, BlockOptional())
import terraworkbench_core as core
for module in pkgutil.iter_modules(core.__path__):
    importlib.import_module(core.__name__ + '.' + module.name)
from terraworkbench_core.profile_preparation import spectrum
from terraworkbench_core.magnetic_compensation import tolles_lawson_design
import numpy as np
signal = np.sin(np.arange(64.))
result = spectrum(np.arange(64.), signal, signal)
assert result
assert callable(tolles_lawson_design)
"""
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(Path(__file__).resolve().parents[1])],
        check=True,
        capture_output=True,
        text=True,
    )
