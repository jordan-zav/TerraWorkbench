# TerraWorkbench ESI replay v1: reproducibility package

This package accompanies the software article on TerraWorkbench submitted to Earth Science Informatics. It contains the evaluated source, the frozen replay protocol and the archived results of the replay reported in the article.

## Relation to the software release

- Software release: TerraWorkbench 1.0.0, https://doi.org/10.5281/zenodo.24119094 and https://github.com/jordan-zav/TerraWorkbench.
- Evaluated source: development revision a4bc358c85975a7ef8284f77cf977c769ba956be (6 November 2026). The replay protocol was frozen against this revision before execution.
- The frozen implementation comprises 99 files (90 Core modules, 7 scripts and 2 protocol records). All 99 are included here byte for byte, normalised to LF, and are verified by the check command below.
- Compared with release 1.0.0, 96 of these 99 files are identical. The three that differ are terraworkbench_core/inversion.py, which gained an additional MVI summary audit after the freeze and is not used by the results reported in the article, and two benchmark files (scripts/benchmark_public_processing.py and scripts/public_processing_sources.json), whose public 1.0.0 versions omit a third-party dataset pending confirmation of its terms. Use this package, not release 1.0.0, to replay the article results.

## Contents

- terraworkbench_core/: Core modules at the evaluated revision.
- scripts/: replay runner (paper_campaign.py), report builder (paper_artifacts.py), benchmark adapters, source registries and the environment observer (capture_paper_environment.py, added after the run; it only reads metadata).
- docs/publication/: protocol (protocol.md, protocol-v1.json), source freeze (freeze-v1.json), dataset registry (data_registry.json), reproduction guide (reproduce.md), claims register, an index (README.md) and the archived results in results/replay-v1.
- docs/validation/records/: historical development records indexed by the runner. They are diagnostics, not new blind validation.
- requirements/ and pyproject.toml: dependency families at the evaluated revision. The exact observed versions are in docs/publication/results/replay-v1/environment.json.
- REDACTIONS.json: see Privacy edits.
- SHA256SUMS.txt: SHA-256 of every file in this package.

## Data

No original third-party data are redistributed. The six public primary inputs are registered in docs/publication/data_registry.json and scripts/public_processing_sources.json by URL, byte count and SHA-256, and are downloaded from their publishers. Each dataset keeps its own licence and attribution, which are separate from the software licence. Figures and tables in results/replay-v1 are derived products and cite their sources.

## Reproducing

Use Python 3.11 with the dependencies listed in requirements/ (closest match: environment.json). From the package root:

    python scripts/paper_campaign.py check

This verifies that all 99 frozen files match the freeze. The full replay, the input download and the report generation are described in docs/publication/reproduce.md. The runner records the git revision of the working tree, so run it inside a Git repository (for example, git init, git add -A and git commit in a copy of this folder). The revision recorded in that case identifies your local copy; the source identity is established by the freeze hashes.

## Privacy edits

Two historical records (docs/validation/records/lagged_irls_20261102.json and mvi_stability_20261102.json) contained the maintainer's local session root and workstation name. These strings were replaced by placeholders; all values and run identifiers are unchanged. REDACTIONS.json lists the SHA-256 of each original file. The runner's historical registry hashes these records, so for these two files a fresh registry will differ from the archived historical_registry.json only in their hashes. The sentence on maintainer resource locations was also removed from reproduce.md, and docs/publication/README.md and docs/publication/results/README.md were written for this package as indexes of the included records. No other file was modified.

## Licence and citation

Source code and documentation: GPL-3.0-or-later (see LICENSE). Cite this package by its Zenodo DOI, and the software by https://doi.org/10.5281/zenodo.24119094.

Author: Jordan Zavaleta, Facultad de Ingeniería Geológica, Minera y Metalúrgica, Universidad Nacional de Ingeniería, Lima, Peru. ORCID 0009-0006-7662-1999.
