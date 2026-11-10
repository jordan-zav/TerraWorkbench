# Language coverage and scientific documentation

TerraWorkbench supports English, Spanish and Portuguese. The language preference
controls the plugin interface and Processing labels, not the language of QGIS
itself or third-party documentation.

## Covered presentation

- Authored interface labels and notifications use explicit translations with
  checked placeholders. Runtime tests also inspect algorithm names, help,
  parameter descriptions and enumeration options.
- Registered Core operations have localized descriptive titles and numerical
  domains. Stable operation IDs, parameter identifiers, channel names, JSON
  keys, saved recipes and scientific values are not translated.
- Signature-based forms have authored labels for 266 directly declared argument
  names, units where explicit, native selectors and conservative type checks.
  Required Euler quality and layered-EM geometry options forwarded by wrappers
  are also exposed, without changing the public execution signatures. Remaining
  forwarded options retain an expandable JSON editor. Required physical inputs
  stay empty; no nominal physical values are invented.
- The grid source-depth console separates grid inputs from method controls.
  Selecting Euler, Werner or SPI exposes its real forwarded options, preserves
  method-specific drafts and prevents options from overriding grid geometry.
  Parameter JSON remains flat and compatible with the existing Core API.
- NPZ selectors inspect bounded headers only and show array names, shapes and
  dtypes without loading payloads. Execution still independently validates the
  archive and preserves its queued-input fingerprint. Header inspection is not
  a checksum or a certification of the payload.
- Core progress notifications are translated at the GUI boundary; numerical
  modules remain independent of Qt and language preferences.
- Switching language refreshes the selected filter inspector without losing
  edited parameter values. Editors own copies of Processing parameters so a
  provider refresh cannot invalidate the objects they use for validation.
- Original API developer docstrings remain English, explicitly labeled and
  available through an optional technical-reference control. Original external
  library error details and upstream document titles retain their source text.

## Knowledge base

The searchable practical handbook has 15 equivalent chapters and 25 detailed
method notes in the three languages. Equations, parameter identifiers and primary
links are shared rather than retranslated.
It covers GRD workflows, coordinates, channels, gridding, filters, magnetic and
gravity interpretation, radiometry, source depths, inversion, electrical/EM
methods, waveforms and borehole logs. The earlier long references are preserved
separately; their historical level of detail is not identical across languages.

ui/knowledge_content.py and ui/knowledge_methods.py are the sources for the GUI and portable handbooks
in docs/handbook. scripts/export_handbook.py regenerates those documents;
its --check mode rejects drift. These generated practical handbooks contain no survey data or acquisition details.

The full 28-chapter books live in docs/manuals/es, en and pt and are read by ui/full_manual.py in the Knowledge dialog. Chapter IDs, equations, implementation links and original API identifiers are preserved. Technical docstrings and historical reports retain their original language. scripts/build_manual_localization.py records source and translation hashes; scripts/check_manual.py checks coverage, structural parity and all local documentation links. Real Canadian-workspace screenshots have a separate capture manifest and do not represent a new inversion validation.

## Verification

scripts/check_localization.py checks authored static strings and format fields
without importing QGIS. tests/test_localization.py checks handbook parity and
exact coverage of the registered operation IDs. tests/qgis_localization_smoke.py
constructs real widgets offscreen, changes language on an existing filter, checks
the runtime catalogue and saves screenshots. It checks domains and implementation
metadata as well as labels; whole-string translations are required for descriptive
metadata rather than accepting partial word replacements. Data-driven translation
triples are checked for missing text, broken encoding and placeholder mismatch.
These checks are configured in CI.

tests/qgis_core_forms_smoke.py constructs every registered form in all three
languages, tests required/typed fields, NPZ selectors and error paths, and solves
an analytic Euler case through collected form parameters. tests/qgis_layout_smoke.py
checks rendered button contents, wrapped labels and minimum sizes at two window
sizes and scale factors 1, 1.5 and 2. Explicit ellipsis with full-text tooltips is
used for long scientific selection labels. These are bounded layout checks, not
proof that every combination of OS theme, font and display is flawless.

The GRD workflow smoke test additionally compares reader values, checks source
checksums and output geometry/masks, and confirms equal numerical results under
the three language preferences. UI tests and synthetic tests do not establish
field validation or proprietary-software equivalence.
