"""Analytic-source and failure-mode checks for depth interpretation."""
import json
import numpy as np
import pytest
from terraworkbench_core.source_depth import (
    euler_window, euler_grid, euler_profile, werner_profile, spi_profile,
    profile_fft_derivatives, write_depth_catalog,
    grid_fft_derivatives, interpret_grid,
)


def dipole(x, y, z, source=(500030., 6000020., -180.)):
    """Vertical dipole field and analytic derivatives, not fitted by the solver."""
    u, v, w = x-source[0], y-source[1], z-source[2]
    r2 = u*u+v*v+w*w
    q = 2*w*w-u*u-v*v
    field = 1e9*q/r2**2.5
    gx = 1e9*(-2*u/r2**2.5-5*u*q/r2**3.5)
    gy = 1e9*(-2*v/r2**2.5-5*v*q/r2**3.5)
    gz = 1e9*(4*w/r2**2.5-5*w*q/r2**3.5)
    return field, gx, gy, gz


def test_euler_dipole_location_background_and_large_coordinates():
    x, y = np.meshgrid(np.linspace(499800, 500200, 11), np.linspace(5999800, 6000200, 11))
    z = np.full_like(x, 70.)
    f, gx, gy, gz = dipole(x, y, z)
    xyz = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    solution, reason = euler_window(xyz, (f+45000).ravel(),
        np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()]), structural_index=3)
    assert reason is None
    np.testing.assert_allclose([solution[k] for k in ('x', 'y', 'z')], [500030, 6000020, -180], atol=1e-7)
    assert solution['depth'] == pytest.approx(250.)
    assert solution['background'] == pytest.approx(45000.)
    assert solution['relative_depth_error'] < 1e-8


def test_euler_zero_index_solves_contact_offset_not_background():
    x, y = np.meshgrid(np.linspace(-200, 200, 13), np.linspace(-200, 200, 13))
    u, v, h = x-15., y+25., 150.
    rx, ry = u*u+h*h, v*v+h*h
    f = np.arctan(u/h)+.7*np.arctan(v/h)+.2*np.log(rx)+.4*np.log(ry)+900.
    gx, gy = h/rx+.4*u/rx, .7*h/ry+.8*v/ry
    gz = -u/rx-.7*v/ry+.4*h/rx+.8*h/ry
    xyz = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])
    solution, reason = euler_window(xyz, f.ravel(), np.column_stack([a.ravel() for a in (gx, gy, gz)]), structural_index=0)
    assert reason is None
    np.testing.assert_allclose([solution[k] for k in ('x', 'y', 'z')], [15., -25., -150.], atol=1e-8)
    assert solution['background'] is None
    assert solution['contact_offset'] == pytest.approx(1.2)


def test_euler_moving_windows_masks_rejection_and_export(tmp_path):
    x, y = np.linspace(499800, 500200, 11), np.linspace(5999800, 6000200, 11)
    xx, yy = np.meshgrid(x, y)
    f, gx, gy, gz = dipole(xx, yy, 70.)
    f[:3, :3] = np.nan
    result = euler_grid(x, y, 70., f, gx, gy, gz, structural_index=3, window_size=5, stride=2)
    assert result['solutions'] and result['rejected']['support'] > 0
    np.testing.assert_allclose([r['depth'] for r in result['solutions']], 250., atol=1e-7)
    output = tmp_path/'catalog'
    write_depth_catalog(output, result, crs='EPSG:26910')
    assert json.loads((output/'catalog.json').read_text())['crs'] == 'EPSG:26910'
    with pytest.raises(FileExistsError):
        write_depth_catalog(output, result)
    empty = euler_grid(x, y, 70., np.ones_like(f), *[np.zeros_like(f)]*3, structural_index=3, window_size=5)
    assert not empty['solutions'] and empty['rejected']['gradient']
    with pytest.raises(RuntimeError, match='canceled'):
        euler_grid(x, y, 70., f, gx, gy, gz, structural_index=3, canceled=lambda: True)


@pytest.mark.parametrize('degree', [-1, 0, 1, 2])
def test_werner_recovers_thin_sheet_with_polynomial_interference(degree):
    x = np.linspace(499500., 500500., 101)
    u, depth = x-500035., 125.
    field = (9000*u+20000*depth)/(u*u+depth**2)
    if degree >= 0:
        field += 45000.
    if degree >= 1:
        field += .03*(x-500000.)
    if degree >= 2:
        field += .0001*(x-500000.)**2
    result = werner_profile(x, field, window_size=31, stride=5, background_degree=degree)
    assert len(result['solutions']) == 15
    np.testing.assert_allclose([r['depth'] for r in result['solutions']], depth, rtol=1e-5)
    np.testing.assert_allclose([r['distance'] for r in result['solutions']], 500035., atol=1e-3)


def test_werner_gaps_profiles_noise_and_degenerate_data():
    x = np.arange(151.)*10
    f = 20000*100/((x-750)**2+100**2)
    f[70:80] = np.nan
    groups = np.where(x < 500, 1, 2)
    result = werner_profile(x, f, profile_id=groups, window_size=21)
    assert result['rejected']['profile_gap'] and result['rejected']['nodata']
    assert werner_profile(x, np.ones_like(x))['rejected']['signal']
    noisy = f+np.random.default_rng(3).normal(0, 10., len(f))
    strict = werner_profile(x, noisy, window_size=21, max_relative_residual=1e-8)
    assert not strict['solutions']
    with pytest.raises(ValueError, match='increase'):
        werner_profile(x[::-1], f)


@pytest.mark.parametrize('model,factor', [('contact', 1), ('thin_sheet', 2), ('horizontal_cylinder', 3)])
def test_spi_model_factor_at_analytic_wavenumber_peak(model, factor):
    # Analytic complex first derivative proportional to (h + i*x)^(-factor).
    x = np.linspace(-500., 500., 501)
    h, offset = 125., 30.
    complex_gradient = (h+1j*(x-offset))**(-factor)
    derivative = -factor*1j*(h+1j*(x-offset))**(-factor-1)
    result = spi_profile(x, complex_gradient.real, complex_gradient.imag,
        second_x=derivative.real, cross_xz=derivative.imag, source_model=model,
        observation_elevation=50.)
    assert len(result['solutions']) == 1
    solution = result['solutions'][0]
    assert solution['distance'] == pytest.approx(offset)
    assert solution['depth'] == pytest.approx(h)
    assert solution['z'] == pytest.approx(-75.)


def test_spi_finite_differences_gap_masks_and_export(tmp_path):
    x = np.arange(-400., 401.)
    g = 1/(100+1j*x)
    result = spi_profile(x, g.real, g.imag)
    assert result['solutions'][0]['depth'] == pytest.approx(100, rel=2e-4)
    write_depth_catalog(tmp_path/'spi', result)
    assert np.load(tmp_path/'spi'/'wavenumber.npy').shape == x.shape
    gx = g.real.copy()
    gx[390:410] = np.nan
    missing = spi_profile(x, gx, g.imag)
    assert not missing['solutions']
    assert not spi_profile(x, np.zeros_like(x), np.zeros_like(x))['solutions']


def test_fft_derivatives_match_periodic_harmonic_and_reject_nodata():
    x = np.arange(256.)
    wave = 2*np.pi*4/256
    field = np.cos(wave*x)
    d = profile_fft_derivatives(field, 1., padding_cells=0)
    np.testing.assert_allclose(d['dx'], -wave*np.sin(wave*x), atol=1e-12)
    np.testing.assert_allclose(d['dz'], -wave*np.cos(wave*x), atol=1e-12)
    np.testing.assert_allclose(d['dxx'], -wave**2*np.cos(wave*x), atol=1e-12)
    np.testing.assert_allclose(d['dxz'], wave**2*np.sin(wave*x), atol=1e-12)
    field[10] = np.nan
    with pytest.raises(ValueError, match='finite'):
        profile_fft_derivatives(field, 1.)


@pytest.mark.parametrize('direction', ['x', 'y'])
def test_grid_spi_and_werner_keep_map_coordinates(direction):
    along = np.linspace(499500., 500500., 101)
    across = np.arange(4.)*10+6000000
    u, depth = along-500030., 125.
    field = 20000*depth/(u*u+depth**2)+45000.
    g = (depth+1j*u)**-2
    dg = -2j*(depth+1j*u)**-3
    values = np.tile(field, (4, 1))
    first, vertical, second, cross = (np.tile(a, (4, 1)) for a in (g.real, g.imag, dg.real, dg.imag))
    x, y = along, across
    if direction == 'y':
        x, y = across, along
        values, first, vertical, second, cross = (a.T for a in (values, first, vertical, second, cross))
    d = {('dx' if direction == 'x' else 'dy'): first, 'dz': vertical,
         ('dxx' if direction == 'x' else 'dyy'): second,
         ('dxz' if direction == 'x' else 'dyz'): cross}
    spi = interpret_grid('spi', x, y, 50., values, derivative_grids=d,
                         direction=direction, source_model='thin_sheet')
    assert len(spi['solutions']) == 4
    np.testing.assert_allclose([s['depth'] for s in spi['solutions']], depth)
    np.testing.assert_allclose([s[direction] for s in spi['solutions']], 500030.)
    werner = interpret_grid('werner', x, y, 50., values, direction=direction,
                            window_size=31, stride=10)
    assert len(werner['solutions']) == 32
    np.testing.assert_allclose([s['depth'] for s in werner['solutions']], depth, rtol=1e-6)


def test_grid_fft_euler_facade_masks_and_resource_limits():
    x, y = np.arange(64.)*2, np.arange(32.)*3
    xx, yy = np.meshgrid(x, y)
    kx, ky = 2*np.pi/128, 2*np.pi/96
    field = np.cos(kx*xx)+np.sin(ky*yy)
    d = grid_fft_derivatives(field, (3., 2.), padding_cells=(0, 0))
    np.testing.assert_allclose(d['dx'], -kx*np.sin(kx*xx), atol=1e-12)
    np.testing.assert_allclose(d['dy'], ky*np.cos(ky*yy), atol=1e-12)
    np.testing.assert_allclose(d['dz'], -kx*np.cos(kx*xx)-ky*np.sin(ky*yy), atol=1e-12)
    with pytest.raises(ValueError, match='level'):
        interpret_grid('euler', x, y, xx, field, structural_index=3)
    with pytest.raises(ValueError, match='budget'):
        interpret_grid('euler', x, y, 0., field, structural_index=3, max_windows=1)
    with pytest.raises(ValueError, match='uniform'):
        interpret_grid('spi', x**2, y, 0., field)
    field[0, 0] = np.nan
    with pytest.raises(ValueError, match='NoData'):
        grid_fft_derivatives(field, (3., 2.))


def test_euler_rank_depth_and_condition_rejection():
    x, y = np.meshgrid(np.linspace(499800, 500200, 11), np.linspace(5999800, 6000200, 11))
    f, gx, gy, gz = dipole(x, y, 70.)
    xyz = np.column_stack([x.ravel(), y.ravel(), np.full(x.size, 70.)])
    gradients = np.column_stack([a.ravel() for a in (gx, gy, gz)])
    assert euler_window(xyz, f.ravel(), gradients, structural_index=3, depth_bounds=(0, 100))[1] == 'depth'
    assert euler_window(xyz, f.ravel(), gradients, structural_index=3, max_condition=1.)[1] == 'condition'
    gradients[:, 1] = 0
    assert euler_window(xyz, f.ravel(), gradients, structural_index=3)[1] == 'rank'


def test_euler_profile_sheet_and_profile_boundaries():
    x = np.linspace(-500, 500, 101)
    u, h = x-15., 150.
    r2 = u*u+h*h
    f = 20000*h/r2+45000.
    gx, gz = -40000*h*u/r2**2, 20000*(u*u-h*h)/r2**2
    result = euler_profile(x, 50., f, gx, gz, structural_index=1, window_size=21)
    assert result['solutions']
    np.testing.assert_allclose([s['distance'] for s in result['solutions']], 15., atol=1e-7)
    np.testing.assert_allclose([s['z'] for s in result['solutions']], -100., atol=1e-7)
    bounded = euler_profile(x, 50., f, gx, gz, structural_index=1,
                            window_size=21, profile_id=np.where(x < 0, 1, 2))
    assert bounded['rejected']['profile_gap']
    with pytest.raises(ValueError, match='budget'):
        euler_profile(x, 50., f, gx, gz, structural_index=1, max_windows=1)


def test_wrong_euler_index_is_not_reported_as_model_independent_depth():
    x, y = np.meshgrid(np.linspace(499800, 500200, 11), np.linspace(5999800, 6000200, 11))
    f, gx, gy, gz = dipole(x, y, 70.)
    xyz = np.column_stack([x.ravel(), y.ravel(), np.full(x.size, 70.)])
    solution, _ = euler_window(xyz, f.ravel(), np.column_stack([a.ravel() for a in (gx, gy, gz)]),
        structural_index=2, max_relative_depth_error=10., max_relative_residual=10.)
    assert solution is not None
    assert abs(solution['depth']-250.) > 20.


@pytest.mark.parametrize('window', [31, 41, 51])
def test_werner_low_noise_window_sensitivity(window):
    x = np.linspace(-500., 500., 201)
    depth = 125.
    field = 20000*depth/((x-30.)**2+depth**2)+45000.
    field += np.random.default_rng(40).normal(0, .05, len(field))
    result = werner_profile(x, field, window_size=window, stride=5,
        max_horizontal_distance=200., depth_bounds=(50., 250.))
    assert len(result['solutions']) >= 5
    assert np.median([s['depth'] for s in result['solutions']]) == pytest.approx(depth, rel=.05)


def test_raw_grid_through_fft_to_spi_depth():
    x, y = np.linspace(-2000., 2000., 513), np.linspace(-2000., 2000., 129)
    field = np.tile(20000*125./((x-31.25)**2+125.**2), (len(y), 1))
    result = interpret_grid('spi', x, y, 50., field, direction='x',
        source_model='thin_sheet', depth_bounds=(50., 300.), peak_distance=8,
        padding_cells=(32, 64))
    center = [s for s in result['solutions'] if s['profile'] == len(y)//2 and abs(s['x']-31.25) < 20]
    assert len(center) == 1
    assert center[0]['depth'] == pytest.approx(125., rel=.05)
