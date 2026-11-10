"""The scientific core must work without importing its ARCHIE client."""
import subprocess
import sys
from pathlib import Path


def test_processing_core_does_not_require_archie():
    root = Path(__file__).resolve().parents[1]
    script = r'''
import importlib, importlib.abc, sys
import numpy as np
class BlockClient(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('archie'):
            raise AssertionError('Core imported its client: '+fullname)
sys.meta_path.insert(0, BlockClient())
for name in ('profile_preparation','crossovers','magnetic_compensation',
             'filter_recipes','magnetic_products','process_effect','archaeology',
             'terrain_analysis','grid_tools','paired_flights','survey_processing',
             'multisensor_project','multisensor_fusion','vector_grid_audit'):
    importlib.import_module('terraworkbench_core.'+name)
from terraworkbench_core.grid_tools import directional_filter, mosaic_arrays
from terraworkbench_core.filter_recipes import apply_proposals
y,x=np.indices((32,32)); grid=42+7*np.cos(2*np.pi*x/8)
settings=dict(stripe_angle_degrees=0,half_width_degrees=10,
              wavelength_min_m=4,wavelength_max_m=16,strength=0)
filtered,_=directional_filter(grid,1,padding_cells=0,**settings)
np.testing.assert_allclose(filtered,grid,atol=1e-12)
products,_=apply_proposals(grid,1,[dict(name='vertical',steps=[dict(filter='1VD')])],padding=0)
np.testing.assert_allclose(products['vertical'],7*(2*np.pi/8)*np.cos(2*np.pi*x/8),atol=1e-12)
products,metadata=mosaic_arrays([grid,grid+3],min_overlap_cells=100)
np.testing.assert_allclose(metadata['offsets_added'],[0,-3],atol=1e-12)
assert not any(name.startswith('archie') for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=root,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_numerical_modules_do_not_import_archie():
    import ast
    core = Path(__file__).resolve().parents[1] / 'terraworkbench_core'
    names = ('profile_preparation','crossovers','magnetic_compensation',
             'filter_recipes','magnetic_products','process_effect','archaeology',
             'terrain_analysis','grid_tools','paired_flights','survey_processing',
             'multisensor_project','multisensor_fusion','vector_grid_audit')
    for name in names:
        tree = ast.parse((core/(name+'.py')).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('archie'), name
            elif isinstance(node, ast.Import):
                assert not any(alias.name.startswith('archie') for alias in node.names), name
