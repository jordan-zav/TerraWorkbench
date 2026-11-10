# Reproducing the frozen campaign

[Paper index](README.md)

## Source and environment

Use an isolated checkout of the execution commit recorded in [campaign.json](results/replay-v1/campaign.json). The protocol was committed before the replay. Keep ongoing development and original datasets in their existing locations. Frozen source changes are rejected; checking out a later Core and silently calling the result version 1.0 is not a valid replay.

The [environment observation](results/replay-v1/environment.json) lists the evaluated Python, operating system and dependency closure. It was observed from the same unchanged SDK after analysis and is distinct from the pre-run code freeze. It is not a solved cross-platform lockfile or a promise of bitwise-identical native libraries. Reuse a compatible SDK and compare numerical results with the declared tolerances. requirements/base.txt and the relevant optional inversion dependencies describe the installation families; use the recorded exact versions for the closest environment match.

Use the configured project launcher, external shared caches and a new per-run directory. TEMP and TMP should be set per session. Substitute CACHE and NEW_RUN below with your own cache and new execution paths.

## Inputs

The six public primary inputs are registered by URL, byte count and SHA256. Existing cache bytes are verified and never silently replaced. Populate an empty cache using the existing fetch API, without running a numerical method:

    import json
    from pathlib import Path
    from scripts.benchmark_public_processing import fetch
    sources = json.loads(Path("scripts/public_processing_sources.json").read_text())
    for key in ("bushveld", "southern_africa", "lightning", "topography", "britain", "tellus"):
        fetch(Path("CACHE"), sources[key])

The primary replay is offline after this preparation. Secondary tutorial inputs are retrieved or reused by the pinned acceptance fetcher, which verifies archives, extracted members and licence bytes. Downloaded Python notebooks or remote code are never executed. Retain source attribution and publisher terms; publicly downloadable does not by itself establish a particular redistribution licence.

## Execution

    python scripts/paper_campaign.py check
    python scripts/paper_campaign.py run --cache CACHE --output NEW_RUN

The output directory must not exist. The runner checks the frozen source before and after execution, retains failures and continues to the independent second task group where possible. The process exits unsuccessfully if a registered group fails. A failed run is evidence and must not be deleted or relabelled as successful.

Generate tables and the real-data figure into a new report directory:

    python scripts/paper_artifacts.py --run NEW_RUN --cache CACHE --output NEW_REPORT

The report uses relative links intended for a results subdirectory under this publication folder; when using a standalone report location, bring the parent indexes with it or navigate directly to its files. Do not compare exact PNG hashes across different Matplotlib versions as a scientific acceptance test.

After analysis, the metadata observer can record dependency versions and integrity hashes in the report directory. It does not install or alter packages:

    python scripts/capture_paper_environment.py --results NEW_REPORT

The [artifact manifest](results/replay-v1/artifact_manifest.json) uses exact PNG bytes and LF-normalized UTF-8 text. Historical CSV values are keyed by record and JSON pointer. Their rows are diagnostics, not independent experiment counts or a denominator for a pooled success percentage.

## Amendments

Keep version 1.0 and its source commit. For a changed method, dataset, parameter, split or threshold, create a new version/file with parent-freeze hash and reason before executing the amended experiment. Record failed and superseded runs in addition to the final selected result. New blind validation requires genuinely reserved data not used to select the recipe; this familiar-data replay does not provide that claim.
