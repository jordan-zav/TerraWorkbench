"""Build/install an isolated core wheel and exercise it without the checkout."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import zipfile
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="tw_core_install_") as folder:
        root = Path(folder)
        source = root / "source"
        source.mkdir()
        shutil.copyfile(ROOT / "pyproject.toml", source / "pyproject.toml")
        shutil.copytree(
            ROOT / "terraworkbench_core",
            source / "terraworkbench_core",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                str(source),
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(root),
            ],
            check=True,
        )
        wheel = next(root.glob("terraworkbench_core-*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            assert all(
                name.startswith("terraworkbench_core/") or ".dist-info/" in name
                for name in archive.namelist()
            )
        target = root / "installed"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                str(wheel),
                "--no-deps",
                "--target",
                str(target),
            ],
            check=True,
        )
        code = '''
import sys, importlib, pkgutil
sys.path.insert(0, sys.argv[1])
sys.path[1:1] = sys.argv[2:]
class BlockHost:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qgis', 'PyQt5', 'PyQt6', 'PySide6', 'TerraWorkbench', 'survey_store', 'text_import', 'survey_grid_pipeline'}:
            raise AssertionError('Host dependency: ' + fullname)
sys.meta_path.insert(0, BlockHost())
import terraworkbench_core as core
from pathlib import Path
assert Path(core.__file__).is_relative_to(Path(sys.argv[1]))
class BlockOptionalTables:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pandas', 'pyproj', 'shapely'}:
            raise ModuleNotFoundError('Optional dependency during Core import: ' + fullname)
optional_blocker = BlockOptionalTables()
sys.meta_path.insert(0, optional_blocker)
for module in pkgutil.iter_modules(core.__path__):
    importlib.import_module(core.__name__ + '.' + module.name)
sys.meta_path.remove(optional_blocker)
print('PASS: installed Core imports with optional table/CRS dependencies blocked')
import numpy as np
from terraworkbench_core.gravity_corrections import normal_gravity_grs80
from terraworkbench_core.magnetic_pipeline import MagneticPipelineOptions, magnetic_grid_products
assert abs(normal_gravity_grs80(0.) - 978032.67715) < 1e-8
products, _ = magnetic_grid_products(np.arange(64.).reshape(8,8), (1.,1.), MagneticPipelineOptions(90.,0.))
assert len(products) == 14 and np.isfinite(products['RTP']).all()
from terraworkbench_core.source_depth import euler_profile, werner_profile, spi_profile
x = np.linspace(-500., 500., 101)
h = 100.
field = 20000*h/(x*x+h*h)
gx = -40000*h*x/(x*x+h*h)**2
gz = 20000*(x*x-h*h)/(x*x+h*h)**2
for catalog in (euler_profile(x, 0., field, gx, gz, structural_index=1),
                werner_profile(x, field), spi_profile(x, gx, gz, source_model='thin_sheet')):
    assert catalog['solutions']
    assert np.isfinite([row['depth'] for row in catalog['solutions']]).all()
print('PASS: installed Euler, Werner and SPI calculations without QGIS/checkout')
from terraworkbench_core.preprocessing import flight_line_metrics, magnetic_elements
assert np.allclose(flight_line_metrics([0,1],[0,0],[0,1])['speed'][1:], 1.)
assert magnetic_elements([3.],[4.],[0.])[0][0] == 5.
if importlib.util.find_spec('pyproj') is not None:
    from terraworkbench_core.coordinates import reproject_xy
    transformed = reproject_xy([-75.],[0.], 'EPSG:4326', 'EPSG:32718')
    assert abs(transformed['x'][0]-500000.) < 1e-6
if importlib.util.find_spec('ppigrf') is not None:
    from terraworkbench_core.geomagnetism import igrf_field
    igrf = igrf_field([-75.],[-10.],[0.], '2025-01-01')
    assert np.isfinite(igrf['total_nt']).all()
if importlib.util.find_spec('harmonica') is not None:
    from terraworkbench_core.terrain_gravity import terrain_correction_prisms
    terrain = terrain_correction_prisms([0.,1.],[0.,1.], np.zeros((2,2)), density_crust=2670.,density_water=1040.,clearance_m=1.)
    assert np.allclose(terrain['terrain_mgal'],0.)
    from terraworkbench_core.operations import run_operation as run_terrain_operation
    adaptive = run_terrain_operation('gravity.terrain_adaptive',easting=[0.,1.],northing=[0.,1.],elevation_m=[[1.,2.],[3.,4.]],observation_xyz=[[0.,0.,10.],[100.,100.,50.]],density_crust=2670.,density_water=1040.,reference_elevation_m=0.,absolute_tolerance_mgal=1e-6)
    assert np.isfinite(adaptive['result']['prism_effect_mgal']).all()
    assert np.all(adaptive['result']['truncation_bound_mgal'] <= 1e-6)
print('PASS: installed QC, coordinates, IGRF and terrain APIs without QGIS/checkout (available optional engines)')
from terraworkbench_core.magnetic_components import convert_field_component, reconstruct_tmi_from_gradients
wave = np.broadcast_to(np.cos(2*np.pi*np.arange(9)/9),(9,9))
converted = convert_field_component(wave,(1.,1.),input_component='up',output_component='down',output_mean_nt=0.)
assert np.allclose(converted['field_nt'],-wave)
reconstructed = reconstruct_tmi_from_gradients((1.,1.),reference_mean_nt=5.,gradient_up=-(2*np.pi/9)*wave)
assert np.allclose(reconstructed['tmi_nt'],wave+5.)
print('PASS: installed component conversion and gradient reconstruction without QGIS/checkout')
from terraworkbench_core.radial_filters import tabulated_radial_filter
radial = tabulated_radial_filter(wave,(1.,1.),[0.,100.],[1.,1.],max_abs_gain=1.)
assert np.allclose(radial['filtered'],wave)
print('PASS: installed tabulated radial filter without QGIS/checkout')
from terraworkbench_core.apparent_properties import layer_property_response, apparent_layer_property
layer_options = dict(kind='density',top_depth_m=0.,thickness_m=2.)
layer_data = layer_property_response(wave,(1.,1.),**layer_options)['predicted']
layer_inverse = apparent_layer_property(layer_data,(1.,1.),background=0.,regularization_response=0.,max_inverse_gain=1e12,minimum_wavelength_m=2.,**layer_options)
assert np.allclose(layer_inverse['contrast'],wave)
assert len(layer_inverse['recipe']['source_sha256']['apparent_properties.py']) == 64
print('PASS: installed finite-layer apparent properties without QGIS/checkout')
from terraworkbench_core.compact_magnetics import magnetic_dipole_field
dipole = magnetic_dipole_field([[0.,0.,1.]],[[0.,0.,0.]],[[0.,0.,1.]],minimum_distance_m=.1)
assert dipole['field_enu_nt'][0,2] > 0
assert np.allclose(dipole['field_enu_nt'][0,:2],0.)
from terraworkbench_core.structural_attributes import monogenic_phase_attributes, local_grid_texture, local_orientation_entropy
phase = monogenic_phase_attributes(np.ones((9,9)),(1.,1.),[3.,6.],sigma_on_f=.55,noise_threshold=0.)
assert np.allclose(phase['phase_symmetry'],0.)
texture = local_grid_texture(np.ones((9,9)),3,(0.,2.))
assert texture['entropy_bits'][4,4] == 0.
orientation = local_orientation_entropy(np.zeros((9,9)),3,bin_origin_degrees=0.)
assert orientation['entropy_bits'][4,4] == 0.
if importlib.util.find_spec('skimage') is not None:
    from terraworkbench_core.lineament_geometry import skeleton_paths
    mask = np.zeros((9,9),bool)
    mask[4,2:7] = True
    paths = skeleton_paths(mask,(1.,1.),(0.,0.))
    assert len(paths['paths']) == 1 and paths['paths'][0]['length_m'] == 4.
print('PASS: installed compact dipole and structural APIs without QGIS/checkout')
from terraworkbench_core.operations import list_operations, run_operation
assert len(list_operations()) >= 94
from terraworkbench_core.operation_workflows import run_core_workflow
from terraworkbench_core.operation_jobs import load_core_job
options = dict(kind='density',top_depth_m=0.,thickness_m=2.,spacing=[1.,1.])
workflow = {'steps':[
    {'id':'response','operation':'potential.layer_response','parameters':dict(options,values=wave.tolist())},
    {'id':'recover','operation':'potential.apparent_property','parameters':dict(options,values={'$result':['response','predicted']},background=0.,regularization_response=0.,max_inverse_gain=1e12,minimum_wavelength_m=2.)},
]}
import json
saved = run_core_workflow(json.dumps(workflow),Path.cwd())
assert np.allclose(load_core_job(Path(saved['folder'])/'recover')['result']['contrast'],wave)
print('PASS: installed multi-process workflow, result references and typed reload without QGIS/checkout')
psd = run_operation('spectra.grid_psd', values=np.arange(64.).reshape(8,8), spacing=(1.,1.))
assert psd['provenance']['status'] == 'completed'
mt = run_operation('mt.layered_forward', frequency_hz=[1.,10.], resistivity_ohm_m=[100.], thicknesses_m=[])
response = run_operation('mt.apparent_resistivity_phase', frequency_hz=[1.,10.], impedance_ohm=mt['result']['impedance_ohm'])
assert np.allclose(response['result']['rho_a_ohm_m'], 100.)
print('PASS: installed operation catalog, provenance, PSD and MT without QGIS/checkout')
radon = run_operation('radiometry.paired_radon', times_s=[0.,1.],
    downward_u_rate=[12.,14.], upward_u_rate=[3.,4.], downward_std=[1.,1.], upward_std=[1.,1.],
    downward_radon_response=1., upward_ground_response=0., upward_radon_response=1., roughness=0.)
assert np.allclose(radon['result']['terrestrial_u_rate'],[9.,10.])
print('PASS: installed calibrated paired-detector radon proxy')
calibration = run_operation('radiometry.fit_response',
    known_concentrations=[[0.],[1.],[2.]], window_rates=[[1.],[3.],[5.]],
    rate_covariance=[[.01]], component_names=['K'], concentration_units=['%'], window_names=['K_window'])
concentrations = run_operation('radiometry.calibrated_concentrations',
    window_rates=[[7.]], rate_covariance=[[.01]], calibration=calibration['result'])
assert np.allclose(concentrations['result']['concentrations'],[[3.]])
complex_response = run_operation('em.fit_complex_response',
    reference=[0j,1j,1+0j], measured=[1+0j,-1+0j,1+2j], covariance=np.eye(2)*.01)
corrected = run_operation('em.apply_complex_response',
    measured=[-3+6j], covariance=np.eye(2)*.01, calibration=complex_response['result'])
assert np.allclose(corrected['result']['corrected'],[3+2j])
flexure = run_operation('regional.elastic_flexure',load_pa=np.full((4,4),1000.),
    spacing_m=[1000.,1000.],elastic_thickness_m=0.,young_modulus_pa=7e10,
    poisson_ratio=.25,restoring_contrast_kg_m3=500.)
assert np.allclose(flexure['result']['displacement_down_m'],1000./(500*9.80665))
print('PASS: installed radiometric/complex calibration and elastic flexure')
if importlib.util.find_spec('pyarrow') is not None:
    import pyarrow as pa
    import json
    from terraworkbench_core.survey_store import SurveyStore
    from terraworkbench_core.survey_text_import import ColumnSpec, TextImportOptions
    source = Path.cwd() / 'storage_input.csv'
    source.write_text("""line;x;y;mag;base
001;500000;4000000;100;5
002;500001;4000001;110;6
""",encoding='utf-8')
    original = source.read_bytes()
    from terraworkbench_core.text_import import inspect_text as inspect_table
    assert inspect_table(source,separator='semicolon')['columns'] == ['line','x','y','mag','base']
    options = TextImportOptions(delimiter=';',columns=[ColumnSpec('line'),ColumnSpec('x','float'),
        ColumnSpec('y','float'),ColumnSpec('mag','float',unit='nT'),ColumnSpec('base','float',unit='nT')])
    store = SurveyStore(Path.cwd()/'installed_storage',create=True)
    database = store.import_file(source,text_options=options)
    store.configure_geometry(database,'x','y','EPSG:32618')
    store.derive(database,'corrected','c("mag")-c("base")',unit='nT')
    reopened = SurveyStore(store.root)
    data = pa.Table.from_batches(list(reopened.batches(database,['line','corrected']))).to_pydict()
    assert data == {'line':['001','002'],'corrected':[95.,104.]}
    assert json.loads(reopened.databases()[0]['metadata'])['geometry']['crs'] == 'EPSG:32618'
    assert len(reopened.channel_pipeline(database,'corrected')['edges']) == 2
    assert source.read_bytes() == original
    print('PASS: installed SurveyStore, typed text import, CRS metadata and channel lineage outside checkout')
mnf = run_operation('radiometry.mnf', training_spectra=np.arange(30.).reshape(10,3), noise_covariance=np.eye(3), rank=3)
assert np.allclose(mnf['result']['spectra'],np.arange(30.).reshape(10,3))
gated = run_operation('tem.integrate_recorded_gates', times_s=[0.,1.,2.], transients=[1.,3.,5.], gates_s=[[.5,1.5]])
assert np.allclose(gated['result']['gate_mean'],[3.])
print('PASS: installed MNF and recorded TEM gate integration')
well = run_operation('borehole.trajectory', measured_depth_m=[0.,100.], inclination_deg=[0.,0.], azimuth_deg=[0.,0.], collar_enu_m=[0.,0.,0.])
assert np.allclose(well['result']['coordinates_enu_m'][-1],[0.,0.,-100.])
radar = run_operation('gpr.dewow', traces=np.ones((2,101)), dt_s=1e-9, window_samples=11)
assert np.allclose(radar['result']['traces'],0.)
print('PASS: installed borehole and radar processing without host dependencies')
if importlib.util.find_spec('lasio') is not None:
    las_text = """~Version
VERS. 2.0 : version
WRAP. NO : wrap
~Well
STRT.M 0 : start
STOP.M 1 : stop
STEP.M 1 : step
NULL. -999.25 : null
~Curve
DEPT.M : depth
TEST.SI : test
~ASCII
0 1
1 2
"""
    las = run_operation('borehole.read_las', text=las_text)
    assert np.allclose(las['result']['depth_m'],[0.,1.])
    assert 'lasio' in las['provenance']['libraries']
    print('PASS: installed optional LAS reader and dependency provenance')
if importlib.util.find_spec('simpeg') is not None:
    qsp = np.zeros(8)
    qsp[0], qsp[1] = .01, -.01
    sp_pde = run_operation('sp.pde_forward',mesh_widths=[np.ones(2)]*3,
        mesh_origin=[0.,0.,0.],conductivity_s_m=np.ones(8)*.1,
        source_density_a_m3=qsp,observation_m=[[.5,.5,.5]],reference_m=[1.5,.5,.5])
    assert np.isfinite(sp_pde['result']['potential_difference_v']).all()
    assert sp_pde['result']['potential_difference_v'][0] > 0
    print('PASS: installed heterogeneous SP PDE backend')
    fdem3 = run_operation('fdem.3d_forward', mesh_widths=[np.full(4,5.)]*3,
        mesh_origin=[-10.,-10.,-10.], frequency_hz=[1000.], conductivity_s_m=[.1],
        source_m=[0.,0.,0.], receiver_m=[5.,0.,0.], parameter_labels=np.zeros(64,dtype=int))
    assert np.isfinite(fdem3['result']['secondary_b_t']).all()
    assert fdem3['result']['earth_dimension'] == '3D'
    assert 'simpeg' in fdem3['provenance']['libraries']
    print('PASS: installed 3D FDEM backend and provenance')
    pde = run_operation('electrical.pde_forward', mesh_widths=[np.full(12,10.),np.full(6,10.)],
        mesh_origin=[-60.,-60.], electrodes=[[-30.,0.,0.],[-10.,0.,0.],[10.,0.,0.],[30.,0.,0.]],
        abmn=[[0,3,1,2]], conductivity_s_m=[.01], parameter_labels=np.zeros(72,dtype=int))
    assert np.isfinite(pde['result']['predicted']).all()
    assert pde['result']['earth_dimension'] == '2.5D'
    print('PASS: installed electrical PDE backend without QGIS/checkout')
    waveform = run_operation('tem.waveform_forward', times_s=[1e-4,1e-3], conductivity_s_m=[.03], thicknesses_m=[],
        waveform_times_s=[-1e-4,0.], relative_current=[1.,0.], source_m=[0.,0.,0.], receiver_m=[10.,0.,0.])
    assert np.isfinite(waveform['result']['dbdt_t_s']).all()
    assert 'simpeg' in waveform['provenance']['libraries']
    print('PASS: installed finite-waveform TEM backend')
    dc = run_operation('electrical.layered_forward',
        electrodes=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],[3.,0.,0.]],
        abmn=[[0,3,1,2]], resistivity_ohm_m=[100.], thicknesses_m=[])
    assert np.allclose(dc['result']['rho_a_ohm_m'],100.,rtol=1e-3)
    assert 'simpeg' in dc['provenance']['libraries']
    print('PASS: installed layered DC and optional-engine provenance')
    from terraworkbench_core.inversion import run_inversion_workflow
    x, y = np.meshgrid(np.arange(3.) * 100, np.arange(3.) * 100)
    xyz = np.column_stack([x.ravel(), y.ravel(), np.full(9, 100.)])
    output = Path.cwd() / 'installed_inversion'
    result = run_inversion_workflow('susceptibility', xyz,
        np.array([0,1,0,1,2,1,0,1,0.]), np.ones(9),
        cell_xy=100, cell_z=100, depth=200, iterations=2,
        output_directory=output)
    assert np.isfinite(result.model).all()
    assert all((output/name).is_file() for name in ('model.npz','model.vtk','data.csv','run.json'))
    print('PASS: installed inversion engine and all output artifacts without QGIS/checkout')
print('PASS: installed wheel, all core imports and calculations without QGIS/checkout')
'''
        dependency_paths = [
            p
            for p in os.environ.get("TERRAWORKBENCH_TEST_DEPENDENCY_PATHS", "").split(
                os.pathsep
            )
            if p
        ]
        subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(target), *dependency_paths],
            cwd=root,
            check=True,
        )


if __name__ == "__main__":
    main()
