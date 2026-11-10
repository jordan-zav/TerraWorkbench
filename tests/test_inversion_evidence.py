import numpy as np
import pytest

from terraworkbench_core.inversion_evidence import spatial_holdout, training_plane


def test_selection_uses_actual_rows_and_is_deterministic():
    x, y = np.meshgrid(np.arange(8.)*100, np.arange(7.)*100)
    xy = np.column_stack([x.ravel(), y.ravel()])
    selected, train = spatial_holdout(xy, 100)
    assert len(selected) == len(xy)
    assert (~train).sum() == 12
    again, same = spatial_holdout(xy, 100)
    np.testing.assert_array_equal(again, selected)
    np.testing.assert_array_equal(same, train)


def test_plane_recovers_known_trend_without_held_out_leakage():
    x, y = np.meshgrid(np.arange(8.), np.arange(7.))
    xy = np.column_stack([x.ravel()+500000, y.ravel()+6000000])
    values = 12+2*x.ravel()-3*y.ravel()
    train = np.arange(len(xy)) % 5 != 0
    changed = values.copy()
    changed[~train] += 1e8
    fitted, recipe = training_plane(xy, changed, train)
    np.testing.assert_allclose(fitted, values, atol=1e-9)
    assert recipe['training_rows'] == train.sum()
    with pytest.raises(ValueError):
        training_plane(np.ones((8, 2)), np.ones(8), np.ones(8, bool))


def test_forward_predictions_preserve_field_and_receiver_order():
    pytest.importorskip('simpeg')
    pytest.importorskip('choclo')
    from discretize import TensorMesh
    from terraworkbench_core.inversion_evidence import predict_susceptibility

    mesh = TensorMesh([[(100., 2)], [(100., 2)], [(100., 2)]], origin=[-100, -100, -200])
    active = np.ones(mesh.nC, bool)
    model = np.arange(1., mesh.nC+1)/1000
    xyz = np.array([[50., 10., 100.], [-70., 40., 130.], [0., -20., 90.]])
    field = dict(field_amplitude=57000., field_inclination=74., field_declination=21.)
    predicted = predict_susceptibility(mesh, active, model, xyz, **field)
    reversed_rows = predict_susceptibility(mesh, active, model, xyz[::-1], **field)
    np.testing.assert_allclose(reversed_rows, predicted[::-1], rtol=1e-12)
    double = predict_susceptibility(mesh, active, model*2, xyz, **field)
    np.testing.assert_allclose(double, predicted*2, rtol=1e-12)
    other_field = predict_susceptibility(mesh, active, model, xyz, **{**field, 'field_declination':-40.})
    assert not np.allclose(other_field, predicted)


def test_executed_inversion_parameter_labels_exist_in_all_languages():
    from ui.core_parameter_schema import parameter_label

    for name in ['cell_xy','cell_z','depth','padding','iterations','lower','upper',
                 'field_amplitude','field_inclination','field_declination','cg_maxiter','cg_rtol']:
        for locale in ['en','es','pt']:
            assert parameter_label(name, locale).strip()
