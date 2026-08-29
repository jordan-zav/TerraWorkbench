# Embedded QPIP components

TerraWorkbench embeds and modifies the dependency-progress components from
[QPIP](https://github.com/opengisch/qpip), copyright OPENGIS.ch and QPIP
contributors, under GNU GPL version 3.

Imported from the local QPIP fork at commit
`25986708677cff42381802a9a09e11a6d8610780` (2026-08-28), including the
per-dependency download/install progress work. The integration is intentionally
scoped to TerraWorkbench's own `requirements.txt`: it does not register a
second QGIS plugin, patch QGIS plugin loading or manage dependencies for other
plugins.

Modified files are marked through TerraWorkbench naming, UI text and this notice.
The complete upstream GPLv3 text is distributed as `LICENSE.qpip`.
