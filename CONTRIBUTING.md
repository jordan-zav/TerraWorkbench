# Contributing to TerraWorkbench

Report bugs and proposed improvements through [GitHub Issues](https://github.com/jordan-zav/TerraWorkbench/issues). Include the source revision, plugin version, OS, QGIS/Python versions, relevant dependency versions, exact steps and the traceback. Provide a small synthetic or redistributable example, its CRS/units, expected result and actual result. Do not upload confidential surveys or credentials. For scientific changes, describe assumptions, references, limitations and independent checks.

From the repository root, with the relevant dependencies installed:

~~~sh
python -m pytest -q
python -m ruff check .
python scripts/package_plugin.py --check-only
python scripts/check_documentation.py
~~~

Use the Ruff configuration in [pyproject.toml](pyproject.toml). The optional dependency groups and [requirements](requirements/README.md) describe the environments; QGIS smoke tests require QGIS and are separate from host-free tests. On a compatible Windows installation, the existing QGIS commands are:

~~~powershell
$qgisRoot = & .\scripts\find_qgis.ps1
& "$qgisRoot\bin\python-qgis-ltr.bat" tests\qgis_smoke_test.py
& "$qgisRoot\bin\python-qgis-ltr.bat" tests\qgis_inversion_smoke.py
~~~

Follow [repository structure](docs/development/repository_structure.md): numerical processing, storage contracts and workflow APIs belong in <code>terraworkbench_core/</code>, without QGIS/Qt/UI imports; host integration belongs in <code>qgis_plugin/</code>, presentation in <code>ui/</code> and Processing adapters in <code>algorithms/</code>. Keep <code>compat/</code> as compatibility routing, preserve stable script/test entry points and delegate numerical operations to the Core instead of duplicating them in the plugin. Review local contributor instructions (<code>AGENTS.md</code>) when available in your checkout; that local file may be untracked.

Document validation actually performed, including failed checks and limits. Keep source datasets intact, retain licences/attribution, and discuss changes to public IDs, saved recipes or scientific assumptions before implementation. Maintainer: Jordan Zavaleta, [jordanzav@gisgeo.dev](mailto:jordanzav@gisgeo.dev).
