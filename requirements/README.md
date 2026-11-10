# Plugin requirements

- base.txt declares the QGIS scientific/runtime dependencies.
- inversion.txt records the optional inversion subset for compatible Python.
- benchmark.txt declares independent benchmark reference libraries.

The embedded manager resolves requirements relative to the installed plugin root. Standalone Core dependencies and optional extras are defined separately in pyproject.toml. Use an isolated environment and install only the extras needed for your workflow; no machine-specific launcher is required.
