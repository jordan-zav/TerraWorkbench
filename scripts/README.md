# Developer commands

Run commands from the repository root using your selected Python environment. QGIS scripts require the QGIS Python interpreter; ordinary tests use pytest. Supply cache and output paths explicitly and use a new output directory for each scientific campaign. Optional environment variables are described by each command's --help.

| Purpose | Commands |
| --- | --- |
| Public source export and verification | export_public.py --output NEW_FOLDER |
| QGIS plugin | package_plugin.py --check-only; package_plugin.py |
| Documentation | check_documentation.py; check_manual.py; build_manual_reference.py --check; build_manual_localization.py --check |
| Numerical benchmarks | benchmark_public_processing.py --cache CACHE --output NEW_FOLDER; benchmark_public_inversion.py --cache CACHE --output NEW_FOLDER |
| Synthetic examples | generate_sample_data.py (explicit regeneration only) |
| Offscreen synthetic captures | capture_manual_ui.py --synthetic --output NEW_FOLDER --profile-dir NEW_PROFILE |
| Independent Core wheel | check_core_install.py |

Benchmarks report execution, numerical comparison and recovery separately. Read [the validation index](../docs/validation/README.md); successful execution does not certify field recovery. Publication/export commands never submit a manuscript or create a release remotely.
