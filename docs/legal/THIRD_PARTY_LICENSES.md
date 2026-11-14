# Third-party software

Physical profile distance additionally uses PyProj (MIT license), backed by
PROJ, for declared CRS units and ellipsoidal horizontal distance. It is an
explicit QGIS runtime requirement and the standalone coordinates extra;
the package is not bundled in the plugin archive.

The TerraWorkbench source code is licensed under GNU GPL version 3 or later. The
scientific libraries below are separate runtime projects installed into the
active QGIS user profile.

## Embedded QPIP-derived components

TerraWorkbench distributes modified copies of QPIP's dependency progress parser
and installation dialog. QPIP is copyright OPENGIS.ch and contributors and is
licensed under GNU GPL version 3. The embedded code is scoped to TerraWorkbench;
it does not bundle the complete QPIP plugin. See
embedded_qpip/NOTICE.md and embedded_qpip/LICENSE.qpip for provenance and
the complete license text.

All current runtime licenses are compatible with distribution of TerraWorkbench under GPLv3. Their copyright notices and complete license texts remain those supplied by each upstream package.

## Core scientific stack

The survey workspace uses Apache Arrow / PyArrow (Apache-2.0) for Parquet and
CSV I/O, and Python's standard-library SQLite interface for its catalogue.
PyArrow is installed as an explicit runtime dependency, not bundled in the ZIP.

The basic spatial processors directly use SciPy's RBFInterpolator
(thin_plate_spline, affine polynomial), ndimage.convolve and
ndimage.uniform_filter, with NumPy array operations. Their definitions are
independent; no proprietary gridding or filter code is bundled. SciPy is an
explicit runtime requirement; backend attribution is exposed in process info.

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
| ppigrf | 2.1.0 | MIT |
| defusedxml | 0.7.1 | Python Software Foundation License |
| Geosoft GX Developer for Python | 2024.2.x | BSD-2-Clause; Windows-only optional GDB reader |

The Geosoft package supplies its own GX public runtime and is used only to read
and export single-file Geosoft GeoDatabase data into open CSV/QGIS formats. It
does not require a separately installed desktop application. TerraWorkbench pins the 2024.2 series to retain
compatibility with the NumPy versions shipped by supported QGIS releases. The
package's upstream copyright and BSD notice remain installed with its wheel.

## 3D inversion stack

These packages are declared in canonical requirements/base.txt for the embedded
manager. requirements/inversion.txt also lists the inversion-only subset for
manual or isolated environments. TerraWorkbench imports them lazily so the 2D
code paths remain isolated at runtime.

| Package | Tested version | Declared license |
|---|---:|---|
| SimPEG | 0.25.2 | MIT |
| discretize | 0.12.0 | MIT |
| geoana | 0.8.1 | MIT |
| pymatsolver | 0.4.0 | MIT |
| libdlf | 0.3.0 | MIT |
| Choclo | 0.3.2 | BSD-3-Clause |

## Supporting packages installed with the core

Joblib, threadpoolctl, fsspec, Toolz, Cloudpickle and Click declare BSD-3-Clause licenses. Partd declares a BSD license. Locket and Platformdirs retain their upstream licenses and notices.

## Optional future integrations

The optional GDB archive converter prepares the official GX 2024.2 full redistributable only after explicit download approval in the dependency manager. Native binaries remain outside the plugin ZIP and repository. The archive design and terms distinguish the BSD wrapper license from vendor entitlement and third-party restrictions. The setup retains copyright, license and third-party notices beside the downloaded runtime; it does not accept Seequent identity or subscription terms for the user.

PyVista, GemPy, pyGIMLi, empymod and UBC-GIF are not bundled or required by the current release. Each integration must receive a separate license review before distribution. UBC-GIF executables must never be redistributed; a future connector may only work with a licensed copy installed separately by the user.

## Redistribution rule

If a future release vendors any third-party package inside the plugin archive, its complete upstream copyright notice, license text and notices must be copied into the distributed archive. This file alone does not replace those required license texts.

## Tellus A9 radiometric line data

Product: GSI_Tellus_A9_RAD_DATA_2022.zip, provided by Geological Survey Ireland. Product-specific CC BY 4.0 confirmation was received on 11 November 2026. [Source data](https://gsi.geodata.gov.ie/downloads/Geophysics/Data/GSI_Tellus_A9_RAD_DATA_2022.zip) · [GSI data licence](https://gsi.ie/data-and-maps/) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Contains Irish Public Sector Data (Geological Survey Ireland) licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) licence

The public benchmark retrieves the pinned source archive from its publisher; it does not bundle raw line data. It imports the supplied corrected concentrations and derives U/Th ratios, terrestrial dose and normalized RGB, preserving the source units and labels. These products do not reconstruct detector calibration or validate full atmospheric-radon correction. The attribution is retained in benchmark source metadata, results and workspace metadata.

Example from the repository root, using an existing verified cache and a new output folder:

    python examples/manual/tellus_a9.py --cache CACHE_DIRECTORY --output NEW_OUTPUT_DIRECTORY

Network retrieval is opt-in through the example flag --allow-download. The numerical checks and data checksum are unchanged by the licensing restoration.

## PSI gamma-ray spectra

The public processing benchmark uses the data_v1_1_0.zip spectra of David
Breitenmoser, Alberto Stabilini, Malgorzata Magdalena Kasprzak and Sabine Mayer,
Paul Scherrer Institute, under CC BY 4.0. Credit both the
[dataset, Zenodo 20032395](https://doi.org/10.5281/zenodo.20032395) and the
[associated Nature Communications article](https://doi.org/10.1038/s41467-026-78464-2),
as confirmed by the dataset author. The source registry and benchmark report
retain this citation pair. These spectra are benchmark inputs, separate from
the Tellus A9 concentration workflow; no raw PSI archive is bundled in the
plugin ZIP.

The full 2024.2 archive includes the Seequent Evo dependencies omitted by the minimal package. Its managed components declare Microsoft .NET 6 Core and Windows Desktop frameworks, obtained separately under Microsoft terms. No .NET runtime is bundled in the plugin.

## Microsoft .NET 6 portable

TerraWorkbench downloads the Microsoft .NET Runtime and Windows Desktop Runtime 6.0.36 x64 ZIPs with consent when preparing GDB support. The ZIPs are verified against the [Microsoft release metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/6.0/releases.json) and extracted into the active QGIS profile. The runtime distribution includes the [MIT license](https://github.com/dotnet/runtime/blob/v6.0.36/LICENSE.TXT) and third-party notices, which are retained with the extracted files.
