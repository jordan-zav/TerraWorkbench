# Test entry points

Run <code>python -m pytest -q</code> from the repository root in an environment with the declared optional dependencies. Missing optional libraries may cause explicit skips; record them in validation reports. The scientific tests retain their original acceptance criteria and negative controls.

QGIS smoke scripts require the QGIS Python interpreter and <code>QT_QPA_PLATFORM=offscreen</code>, with a fresh isolated profile. They are separate from the ordinary pytest suite. Run scripts/check_manual.py for generated source, figures and language parity, and scripts/package_plugin.py --check-only for release resource validation.

tests/test_public_export.py checks the public manifest boundary, forbidden content and export validation. Public CI is defined in [.github/workflows/public-ci.yml](../.github/workflows/public-ci.yml). Supply temporary directories through your environment; no local resource launcher is required. The development archive retains editorial-only checks outside the public manifest.
