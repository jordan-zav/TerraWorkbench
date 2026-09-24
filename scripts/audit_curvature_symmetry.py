"""Audit orientation independently of Oasis; write reproducible JSON evidence."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridding_methods import MinimumCurvatureGridder, _briggs_constraints, _bending_energy


def exact_surface(points, values, axis):
    """Direct reference for the same equations, without iterative stopping."""
    extended = np.arange(axis[0]-2, axis[-1]+3)
    a, z, anchors = _briggs_constraints(points, values, extended, extended)
    q = _bending_energy(len(extended), len(extended), 0.)
    free = np.ones(q.shape[0], dtype=bool)
    free[anchors] = False
    qc, ac = q.tocoo(), a.tocoo()
    keep = free[qc.row]
    matrix = coo_matrix((np.r_[qc.data[keep], ac.data],
                        (np.r_[qc.row[keep], anchors[ac.row]],
                         np.r_[qc.col[keep], ac.col])), shape=q.shape).tocsc()
    rhs = np.zeros(q.shape[0])
    rhs[anchors] = z
    u = spsolve(matrix, rhs)
    residual = np.max(abs(matrix@u-rhs)/abs(matrix.diagonal()))
    return u.reshape(len(extended), len(extended))[2:-2, 2:-2], float(residual)


def audit(size, iterations):
    axis = np.arange(size+1.)
    yy, xx = np.mgrid[1:size:2, 1:size:2]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    points = points+np.random.default_rng(482).uniform(-.3, .3, points.shape)
    values = 10*np.exp(-((points[:, 0]-3)**2+(points[:, 1]-4)**2)/9)+np.sin(points[:, 0])
    direct = {}
    iterative = {}
    for name, p, undo in (
        ('identity', points, lambda a: a),
        ('reflect_x', np.column_stack((size-points[:, 0], points[:, 1])), lambda a: a[:, ::-1]),
        ('rotate_90', np.column_stack((size-points[:, 1], points[:, 0])), lambda a: np.rot90(a, 1)),
    ):
        result, residual = exact_surface(p, values, axis)
        direct[name] = undo(result)
        rounded, _ = exact_surface(p, values, np.arange(int(np.ceil(size/4))*4+1.))
        rounded = undo(rounded[:size+1, :size+1])
        iterative[name] = {'direct_residual': residual,
                           'rounded_domain_rmse_to_physical': float(np.sqrt(np.mean((rounded-direct[name])**2))),
                           'runs': []}
        for count in iterations:
            model = MinimumCurvatureGridder(p, values, 1., coarse_grid=4,
                                            tolerance=1e-9, pass_tolerance=100.,
                                            max_iterations=count)
            result = undo(model.grid(axis, axis))
            iterative[name]['runs'].append({
                'iterations_limit': count,
                'rmse_to_direct': float(np.sqrt(np.mean((result-direct[name])**2))),
                'rmse_to_rounded_direct': float(np.sqrt(np.mean((result-rounded)**2))),
                'grid': result.tolist(), 'final_level': model.metadata['levels'][-1]})
    for name, entry in iterative.items():
        entry['direct_symmetry_max_error'] = float(np.max(abs(direct[name]-direct['identity'])))
        for run, base in zip(entry['runs'], iterative['identity']['runs']):
            run['symmetry_max_error'] = float(np.max(abs(np.array(run['grid'])-np.array(base['grid']))))
    return iterative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {str(size): audit(size, [100, 5000]) for size in (8, 10)}
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for size, orientations in report.items():
        for name, entry in orientations.items():
            print(size, name, 'direct symmetry', entry['direct_symmetry_max_error'],
                  [(r['iterations_limit'], r['symmetry_max_error'], r['rmse_to_direct'],
                    r['final_level']['converged']) for r in entry['runs']], flush=True)


if __name__ == '__main__':
    main()
