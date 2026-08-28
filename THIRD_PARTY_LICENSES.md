# Third-party software

The TerraWorkbench source code is licensed under GNU GPL version 3 or later. The libraries below are separate projects used at runtime and are not included in the plugin source package. They are installed independently into the Python environment used by QGIS.

All current runtime licenses are compatible with distribution of TerraWorkbench under GPLv3. Their copyright notices and complete license texts remain those supplied by each upstream package.

## Core scientific stack

| Package | Tested version | Declared license |
|---|---:|---|
| Harmonica | 0.7.0 | BSD-3-Clause |
| Verde | 1.9.0 | BSD-3-Clause |
| Choclo | 0.3.2 | BSD-3-Clause |
| Xarray | 2026.7.0 | Apache-2.0 |
| xrft | 1.0.1 | MIT |
| NumPy | 2.4.6 | BSD-3-Clause with bundled permissive components |
| SciPy | 1.17.1 | BSD-3-Clause with bundled runtime components |
| pandas | 3.0.3 | BSD-3-Clause |
| Scikit-learn | 1.9.0 | BSD-3-Clause |
| Numba | 0.67.0 | BSD |
| llvmlite | 0.49.0 | BSD-2-Clause and Apache-2.0 with LLVM exception |
| Pooch | 1.9.0 | BSD-3-Clause |
| Dask | 2026.8.0 | BSD-3-Clause |

## Supporting packages installed with the core

Joblib, threadpoolctl, fsspec, Toolz, Cloudpickle and Click declare BSD-3-Clause licenses. Partd declares a BSD license. Locket and Platformdirs retain their upstream licenses and notices.

## Optional future integrations

PyVista, GemPy, SimPEG, pyGIMLi, empymod and UBC-GIF are not bundled or required by the current release. Each integration must receive a separate license review before distribution. UBC-GIF executables must never be redistributed; a future connector may only work with a licensed copy installed separately by the user.

## Redistribution rule

If a future release vendors any third-party package inside the plugin archive, its complete upstream copyright notice, license text and notices must be copied into the distributed archive. This file alone does not replace those required license texts.
