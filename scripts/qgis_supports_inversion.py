"""Return success when the QGIS Python can install the inversion stack."""

import sys


raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
