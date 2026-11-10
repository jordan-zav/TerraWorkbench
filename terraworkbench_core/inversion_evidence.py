"""Small, host-independent building blocks for auditable field validation.

These functions do not infer corrections, noise or geological truth. Callers
must declare the inducing field in the coordinate axes used by their mesh.
"""

import numpy as np


def spatial_holdout(xy, spacing, every=5):
    """One actual observation per bin; every nth occupied bin is held out.

    Returns source row indices and a training mask. Bins are anchored at the
    input minimum. Ties use the first source row. Values never affect selection.
    This is an interleaved spatial holdout, not an independent survey.
    """
    xy = np.asarray(xy, float)
    if xy.ndim != 2 or xy.shape[1] != 2 or not len(xy) or not np.isfinite(xy).all():
        raise ValueError("Provide finite projected XY coordinates")
    if not np.isfinite(spacing) or spacing <= 0 or type(every) is not int or every < 2:
        raise ValueError("Positive spacing and integer holdout interval >= 2 required")
    origin = xy.min(axis=0)
    bins = np.floor((xy-origin)/spacing).astype(np.int64)
    distance = np.sum((xy-(origin+(bins+0.5)*spacing))**2, axis=1)
    order = np.lexsort((np.arange(len(xy)), distance, bins[:, 1], bins[:, 0]))
    sorted_bins = bins[order]
    first = np.r_[True, np.any(np.diff(sorted_bins, axis=0), axis=1)]
    selected = order[first]
    train = np.arange(len(selected)) % every != 0
    if train.sum() < 3 or (~train).sum() < 1:
        raise ValueError("Not enough occupied bins for training and holdout")
    return selected, train


def training_plane(xy, values, train):
    """Fit only training rows and evaluate all rows; return portable recipe."""
    xy, values, train = np.asarray(xy, float), np.asarray(values, float), np.asarray(train)
    if (xy.ndim != 2 or xy.shape[1] != 2 or values.shape != (len(xy),)
            or train.shape != values.shape or train.dtype != bool
            or not np.isfinite(xy).all() or not np.isfinite(values).all() or train.sum() < 3):
        raise ValueError("Aligned finite XY, values and boolean training mask required")
    origin = xy[train].mean(axis=0)
    scale = np.ptp(xy[train], axis=0)
    if np.any(scale == 0):
        raise ValueError("Training locations must span a plane")
    design = np.column_stack([np.ones(len(xy)), (xy-origin)/scale])
    coefficient, _, rank, _ = np.linalg.lstsq(design[train], values[train], rcond=None)
    if rank != 3:
        raise ValueError("Training locations must span a plane")
    return design @ coefficient, dict(origin=origin.tolist(), scale=scale.tolist(),
                                     coefficients=coefficient.tolist(), training_rows=int(train.sum()))


def predict_susceptibility(mesh, active, model, xyz, *, field_amplitude,
                           field_inclination, field_declination):
    """Predict TMI nT without storing a sensitivity matrix (SimPEG/choclo).

    Field declination is measured clockwise from the mesh's positive Y axis,
    not implicitly from true north. Susceptibility is SI; coordinates metres.
    """
    from simpeg import maps
    from simpeg.potential_fields import magnetics

    active, model, xyz = np.asarray(active), np.asarray(model, float), np.asarray(xyz, float)
    if (active.dtype != bool or active.shape != (mesh.nC,)
            or model.shape != (int(active.sum()),) or not np.isfinite(model).all()
            or xyz.ndim != 2 or xyz.shape[1] != 3 or not len(xyz) or not np.isfinite(xyz).all()):
        raise ValueError("Aligned active scalar model and finite XYZ receivers required")
    if (not np.isfinite([field_amplitude, field_inclination, field_declination]).all()
            or field_amplitude <= 0 or abs(field_inclination) > 90):
        raise ValueError("Declare a finite positive inducing field and valid inclination")
    receiver = magnetics.receivers.Point(xyz, components="tmi")
    source = magnetics.sources.UniformBackgroundField(receiver_list=[receiver],
        amplitude=field_amplitude, inclination=field_inclination, declination=field_declination)
    simulation = magnetics.simulation.Simulation3DIntegral(mesh=mesh, active_cells=active,
        survey=magnetics.survey.Survey(source), chiMap=maps.IdentityMap(nP=int(active.sum())),
        engine="choclo", store_sensitivities="forward_only")
    return np.asarray(simulation.dpred(model))
