# TerraWorkbench: complete chapter manual

[English](../en/README.md) · [Español](../es/README.md) · [Português](../pt/README.md)

English edition · reviewed 6 November 2026.

This manual develops the available modules from first principles through procedures, contracts and limits. It complements the interface EN/ES/PT practical handbook and existing scientific campaigns. Documentation is not a new field campaign or a declaration that all geophysics is solved.

## How to use it

Read chapters in order to learn the environment, or start with a discipline and return to shared conventions. Chapters 15–17 distinguish model, fit, convergence and recovery. Experimental APIs and specialised integration still pending are identified in context.

Exhaustive signatures are derived from code. Original docstrings retain their technical language; editorial notes, headings and navigation have ES/EN/PT editions. IDs, channel names, keys and equations do not change with translation.

## Chapters

| # | Topic |
| ---: | --- |
| 01 | [What TerraWorkbench is and where to start](01_inicio.md) |
| 02 | [Installation, dependencies and environment](02_instalacion.md) |
| 03 | [Coordinates, units, heights and conventions](03_coordenadas.md) |
| 04 | [Importing text, GRD and geospatial data](04_importacion.md) |
| 05 | [Workspaces, channels, versions and lineage](05_bases_canales.md) |
| 06 | [QC, trajectory, timing and acquisition corrections](06_perfiles_qc.md) |
| 07 | [Crossovers, levelling and interpolation](07_nivelacion_gridding.md) |
| 08 | [Spatial filters, masks and mosaics](08_filtros_espaciales.md) |
| 09 | [FFT, continuation, derivatives and spectral analysis](09_fft_espectros.md) |
| 10 | [Magnetometry, the main field and compact sources](10_magnetometria.md) |
| 11 | [Land gravity, networks and 2D models](11_gravimetria.md) |
| 12 | [Terrain, isostasy, flexure and tensors](12_terreno_isostasia.md) |
| 13 | [Gamma radiometry, spectra and radon](13_radiometria.md) |
| 14 | [Structural attributes and source depth](14_estructura_profundidad.md) |
| 15 | [Gravity and susceptibility modelling and inversion](15_inversion_potencial.md) |
| 16 | [MVI, joint inversion and structural assumptions](16_mvi_conjunta.md) |
| 17 | [Convergence, resolution, uncertainty and validation](17_resolucion_incertidumbre.md) |
| 18 | [DC resistivity, ABMN geometry and PDE](18_electrica_dc.md) |
| 19 | [IP, SIP, Cole–Cole and current history](19_ip_sip.md) |
| 20 | [FDEM, TEM, transients and magnetotellurics](20_em_mt.md) |
| 21 | [Self-potential and reference networks](21_potencial_espontaneo.md) |
| 22 | [GPR, seismic traces and boreholes](22_ondas_sondeos.md) |
| 23 | [Multisource integration and experimental methods](23_integracion_experimentos.md) |
| 24 | [QGIS interface, forms, languages and captures](24_gui_qgis.md) |
| 25 | [Python API, jobs and reproducible workflows](25_api_workflows.md) |
| 26 | [Resources, tests, packaging and maintenance](26_recursos_desarrollo.md) |
| 27 | [Reproducible tutorials from scratch](27_tutoriales.md) |
| 28 | [Scientific evidence, results chapters and publication](28_evidencia_publicacion.md) |

## References and supporting material

- [API reference](../../reference/api/en.md)
- [Structured inventory](../../reference/api/core_inventory.json)
- [Editorial API notes](../../reference/api/notes/en.json)
- [QGIS catalogue](../../reference/catalogues/qgis_en.md)
- [Sources and citation policy](fuentes.md)
- [Executed examples](../_meta/examples.json)
- [Synthetic CC0 captures](../_meta/captures.json)
- [General documentation index](../../README.md)
- [Practical handbook](../../handbook/handbook_en.md)

## Images and reproducibility

Figures use relative links to language-specific resources: two conceptual diagrams, two controlled numerical demonstrations and two actual UI captures, of the bundled synthetic workspace and the chapter reader. No real survey is redistributed in these images. Scripts and examples remain in the repository; Matplotlib is declared in the documentation extra.

Reading needs only the documentation tree; source links require the full checkout. No PDFs are generated. Historical reports remain in their original language with metrics and dates intact.

## What complete means

Every terraworkbench_core Python module has an assigned chapter in shared coverage. All three editions have the same 28 IDs, sections, tables and technical links checked by a parity manifest. This verifies documentation coverage and structural correspondence, not universal scientific validation or stability of every function.

Evaluate each area using contracts, references, tests and results. Historical dates and counts do not certify later revisions.
