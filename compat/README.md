# Compatibility imports

This folder retains the scientific adapters used before the repository split.
They delegate to terraworkbench_core and contain no duplicate numerical logic.

The QGIS package registers lazy aliases for historical qualified imports such
as TerraWorkbench.spectral and TerraWorkbench.provider. Those aliases resolve
to the canonical compat/, qgis_plugin/ or ui/ modules, including their private
attributes, without importing Qt or scientific engines eagerly.

For old standalone scripts that used short imports from a checkout, activate
the aliases explicitly:

~~~python
from compat.redirects import install_legacy_imports
install_legacy_imports()
import basic_processing
~~~

New standalone code should import terraworkbench_core directly. The standalone
wheel continues to include only terraworkbench_core, without the plugin or
this compatibility layer.
