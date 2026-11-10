# 27. Reproducible tutorials from scratch

[English](../en/27_tutoriales.md) · [Español](../es/27_tutoriales.md) · [Português](../pt/27_tutoriales.md)

## What these examples contain

Programs in examples/manual use artificial data for controlled numerical checks. They create new outputs under a chosen folder without survey downloads or credentials. Their numbers teach contracts, not recommended survey parameters. The public manual captures use the bundled CC0 synthetic survey and record source, rows and locale separately from scientific benchmarks.

From the repository, with Core and required extras installed:

    python examples/manual/workspace.py --output CARPETA_NUEVA
    python examples/manual/fft.py --output OTRA_CARPETA_NUEVA
    python examples/manual/workflow.py --output TERCERA_CARPETA_NUEVA

Each destination must be new to preserve previous runs. Choose resource paths suitable for your machine. Do not copy another user's literal folder name or overwrite their existing workspace.

## Tutorial A. A database and channels

The [workspace example](../../../examples/manual/workspace.py) creates artificial lines with projected coordinates, signal and known offset. It imports CSV, assigns geometry, subtracts channels, publishes an evaluation selection and exports CSV/lineage.

Review row count, corrected values against the known expression and original-file hash. Opening the workspace in the GUI checks pagination/channel selection. The CRS describes artificial demonstration coordinates, not a field site.

## Tutorial B. FFT with a known response

The [FFT example](../../../examples/manual/fft.py) creates two periodic wavelengths, upward-continues them and compares attenuation with exp(−kh). It exports arrays/metrics. It needs neither IGRF nor QGIS because it is already a synthetic level-grid signal.

Complete periodic support separates operator demonstration from edge filling. Real-data preparation/masks need separate review. Trying heights does not validate variable-terrain processing.

## Tutorial C. Registered operations and a workflow

The [workflow example](../../../examples/manual/workflow.py) queries the registry, computes an MT half-space with a known response and executes the public gravity-layer recipe. It reloads jobs and verifies saved results, separating scientific calculation from publication.

Property recovery with exact geometry and no noise is a small control, not free 3D inversion or geological survey resolution.

## Tutorial D. GUI captures

With QGIS Python, the [visual-evidence tool](../../../scripts/capture_manual_ui.py) supports --synthetic, isolates profile/preferences and calls the offscreen API. The public capture imports sample_data/synthetic without downloading surveys or running inversions. It never controls the user's keyboard, mouse or windows; retain input hashes, row counts and language.

## Final checks

Examples emit readable summaries and metric JSON. The [execution record](../_meta/examples.json) identifies environment, source and observed criteria. Rerun relevant examples when kernels or environments change; a historical date is not a fresh execution.

---

[Contents](README.md) · [Previous](26_recursos_desarrollo.md) · [Next](28_evidencia_publicacion.md)
