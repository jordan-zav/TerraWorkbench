# Numerical reference and survey capacity campaign

Local campaign completed on 26 October 2026 using synthetic data only. This is
evidence for the contracts below, not certification of every Core operation.
Reproducible cases live in tests/test_independent_numerical_references.py,
tests/test_store_crash_recovery.py and scripts/benchmark_survey_capacity.py.

## Independent numerical checks

| Method | Reference and contract | Acceptance |
| --- | --- | --- |
| GRS80 normal gravity | Independent Boule evaluation at ellipsoid height zero, 721 latitudes from -90 to 90 degrees, mGal | absolute difference at most 0.0002 mGal; rounded Core constants are retained |
| 2D Butterworth | scikit-image, unsquared amplitude response, no padding, low/high pass, orders 1/2/4, odd/even raster sizes | relative and absolute tolerance 0.000000000002 |
| Circular median | Explicit sorted pixel-centre disk neighborhoods, radii 1/2/4; clipped edges, ignored missing neighbors, preserved missing centres | exact equality |
| Overlapping radiometric windows | 200,000 independent Poisson trials, explicit fractional overlaps, fixed random seed | mean absolute tolerance 0.08 count and covariance relative tolerance 1.2 percent |

The 17 numerical cases passed. The radiometric experiment checks the declared
Poisson model and fractional-bin approximation; it is not an instrument
calibration. Butterworth uses the ordinary amplitude response rather than the
squared variant, which changes attenuation at the cutoff. SciPy SOS
forward/backward 1D filtering has a different response and boundary contract.

Primary contracts: [Boule normal gravity](https://www.fatiando.org/boule/latest/user_guide/normal_gravity.html),
[scikit-image Butterworth](https://scikit-image.org/docs/stable/api/skimage.filters.html#skimage.filters.butterworth),
[SciPy SOS forward/backward filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).

## Storage and filters at scale

Each case generates a new Parquet source in bounded batches, imports it,
reads one/two/all channels, derives mag minus base, cancels an active derivation,
filters every transect independently, verifies every output sample against an
analytical linear-plus-sinusoid mean, reopens the database and exports a selected
line. Source SHA256 must remain unchanged. Data are synthetic, not a survey.

| Rows | Transects | Input channels | Import seconds | Mean filter seconds | Filter sampled peak RSS MiB | Maximum error nT |
| --- | --- | --- | --- | --- | --- | --- |
| 100,000 | 30 | 13 | 0.124 | 6.18 | 240.8 | 0.0000000000292 |
| 1,000,000 | 30 | 13 | 2.11 | 12.42 | 215.4 | 0.0000000000292 |
| 8,000,000 | 30 | 13 | 17.03 | 79.46 | 296.4 | 0.0000000000292 |
| 3,000,000 | 1 | 5 | 1.46 | 30.74 | 543.6 | 0.0000000000801 |

The filter was a centered five-sample mean. Its complete-window policy produced
exactly four null edge samples per transect: 120 for thirty lines and four for
one line. Input/output alignment crossed Parquet batch and row-group boundaries.
No line boundary was bridged. Reads never exceeded 65,536 rows per batch.

For the eight-million-row case, observed one/two/all-channel read times were
0.279/0.218/1.811 seconds. These sequential reads share OS and Arrow caches, so
they are not controlled cold-cache speed comparisons. The process reached
868.0 MiB sampled RSS during the derivation stage, above the filter-stage peak;
bounded Arrow batches are not a strict bound on total memory. RSS includes the
interpreter and retained allocator memory and excludes OS file cache. Sampling
every 20 ms may miss short peaks. Timings include stage setup and vary by machine.

## Cancellation and interrupted writes

Mid-derivation cancellation was requested after 131,072 rows in the large cases.
Observed request-to-exception latency was 0.00233 seconds for eight million rows
and 0.00227 seconds for three million. No cancelled channel was published; normal
cancellation left no partial file. These observations are not a universal latency
guarantee for other kernels.

The separate abrupt-exit test kills a child writer after its first batch. The
catalog and existing channels remain unchanged and readable; retrying the same
output name succeeds. An unreferenced partial file can remain after a process
crash and is deliberately retained. No automatic cleanup or resumption from that
partial file is claimed. This test passed in addition to the 17 numerical cases.

## Reproduction and limits

Install the storage and validation extras in an existing scientific environment;
the benchmark uses psutil only for process RSS. Invoke the benchmark script with
an unused output directory, rows, transects and extra-channels arguments. Defaults
are 100,000 rows, 30 transects and eight auxiliary channels. Use 8,000,000 rows
for the survey case and 3,000,000 rows with one transect for the run-limit case.
Each output directory receives report.json checkpoints, sources and results.
Nothing is overwritten or automatically cleaned. CI runs the 100,000-row case;
the multi-million cases are measured local evidence, not a CI timing gate.

This campaign does not validate every filter, text-import format, inversion,
coordinate transformation or end-to-end survey reduction at eight million rows.
SurveyStore.correct_magnetic still caps its entire correction workspace at three
million rows; passing filter_channel on eight million rows does not remove that
separate limit. Large-CSV inference, concurrent writers, power-loss durability,
instrument models and independently validated real-survey comparisons remain
separate work. No numerical kernel was changed to make these new tests pass.
