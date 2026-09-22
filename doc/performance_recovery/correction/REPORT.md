# Targeted audit correction report

This correction starts from performance branch head
`0e0d267eddc469a0ed659108f4241a5be3e97581`, which is stacked on PERF_BASE
`04c300c6a0fe1117531a64e6a7966b436eadfce7`. It addresses only the independent
audit findings marked medium or low. It does not open an upstream PR, merge
upstream/main, rewrite previous campaign commits or remove the existing full
campaign evidence.

Corrected implementation commit: `93a66220fdd41b634daaaa895028ba66a038cd0b`.
Full correction evidence commit: [`99b5952`](https://github.com/agustinpabon/toponymy/tree/99b5952457c2f35f9c320d581eb6bac3b5635fbe/doc/performance_recovery/correction). Measurements snapshot
working source before these commits; `measurements/manifest.json` records the
exact source hashes, diff from the previous HEAD and both harness hashes.

## Production change

`build_cluster_tree()` still validates and canonicalizes public labels at the
public boundary, but now passes grouping metadata to `_tree_from_grouping()` as
a generator. `_tree_from_grouping()` consumes its grouping input once, so each
standalone grouping can be collected after its lower layer has been processed.

`PrecomputedClusterer._set_labels()` still materializes the grouping list once
because the fitted path uses the same canonical grouping metadata for both
`ClusterLayer` construction and `ClusterTree` construction. That preserves the
large precomputed clustering speedup from the original campaign.

The persistence change is documentation/test clarification only: the explicit
COO coordinate bounds guard remains. Persisted malformed COO NPZ archives were
already rejected by SciPy during loading. Some directly mutated in-memory COO
objects that PERF_BASE silently accepted are now rejected earlier.

## Verification scope

The benchmark verifier now checks returned clustering state more directly:
complete ordered cluster IDs, cluster counts, exact labels, exact members,
layer indices, tree entry order, owned arrays, read-only arrays and no sharing
with source labels. The clustering digests now come from returned labels and
members rather than only from input labels.

Persistence verification remains intentionally scoped. It compares vectors,
document dataframes, sparse matrix shapes and values, normalized trees, topic
table identity/name/size/keyphrases and reconstructed members. Its compact
digest covers vectors, memberships, trees and topic names. It is not a universal
digest of every mutable `TopicModel` or `Topic` field.

## Depth diagnostic methodology

`check_tree_depth.py` compares three arms in fresh source snapshots without
checking out the working tree:

- `base`: PERF_BASE `04c300c6a0fe1117531a64e6a7966b436eadfce7`
- `before`: original performance branch head
  `0e0d267eddc469a0ed659108f4241a5be3e97581`
- `after`: corrected working tree source copied into a temporary snapshot

Depth cases use valid identical partitions with `n=8192` and 64 cluster IDs at
depths 1, 3, 8, 16, 32 and 64. Each arm/depth has three independent processes.
Timing uses two warmups and nine timed calls per process. Memory uses three
separate tracemalloc calls after timing; tracemalloc is not active during the
timed calls. All 99 process records are retained in `measurements/`.
This includes 1296 timed observations and 432 separate memory observations; all
workers succeeded. Arm order rotates by replication. Memory calls use explicit
collection before tracing; inputs, output verification and imports are outside
timing, while public validation and all construction are inside. Numerical
threads are fixed to one and each process uses a fresh temporary Numba cache.
OS caches are not flushed. No tests/profiles ran alongside measurements.

Ordered depth-tree entries and children match exactly across all arms and an
explicit nearest-parent oracle. Scale inputs retain the existing seed 211,
float64 64-dimensional vectors, shared noise and three nested label layers.
All dependencies and input hashes match across arms. These are local Mac results,
not pooled with the earlier campaign or sealed Linux measurements. Three process
replications are a limited local experiment, not broad statistical evidence.

## Standalone tree depth results

Median seconds and median Python-tracked peak bytes are process medians from
the retained raw observations.

| Depth | BASE peak | BEFORE peak | AFTER peak | AFTER vs BEFORE peak | BASE s | BEFORE s | AFTER s | AFTER vs BEFORE s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 477,647 | 280,384 | 280,936 | 1.002x | 0.000275 | 0.000273 | 0.000281 | 1.027x |
| 3 | 773,663 | 547,472 | 577,048 | 1.054x | 0.000928 | 0.000859 | 0.000873 | 1.016x |
| 8 | 1,180,343 | 1,291,984 | 983,744 | 0.761x | 0.002513 | 0.002405 | 0.002364 | 0.983x |
| 16 | 1,827,391 | 2,475,800 | 1,630,792 | 0.659x | 0.005078 | 0.004848 | 0.004864 | 1.003x |
| 32 | 3,121,463 | 4,843,408 | 2,924,864 | 0.604x | 0.010534 | 0.010245 | 0.010008 | 0.977x |
| 64 | 5,709,631 | 9,578,648 | 5,513,032 | 0.576x | 0.022734 | 0.020582 | 0.020681 | 1.005x |

The depth-dependent memory regression is materially corrected at deeper
hierarchies. Runtime remains effectively unchanged relative to the original
optimized branch and remains close to, or below, BASE in this diagnostic.
Depth 3 peak allocation rises 5.4% relative to BEFORE, while depth 64 falls 42.4%
and is below BASE. This fixes unnecessary depth-dependent retention; it does not
promise lower allocation at every depth or measure total native memory/RSS.

## Precomputed and standalone tree scale check

The existing five-size warm scale check was rerun for precomputed clustering
and standalone tree construction. Ratios are AFTER / BASE.

| n | Precomputed BASE s | Precomputed AFTER s | AFTER / BASE | Tree BASE s | Tree AFTER s | AFTER / BASE |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 0.000247 | 0.000086 | 0.349x | 0.000045 | 0.000044 | 0.977x |
| 512 | 0.000490 | 0.000144 | 0.294x | 0.000071 | 0.000073 | 1.031x |
| 2048 | 0.001639 | 0.000413 | 0.252x | 0.000235 | 0.000234 | 0.996x |
| 8192 | 0.006545 | 0.001458 | 0.223x | 0.001052 | 0.001008 | 0.958x |
| 32768 | 0.020385 | 0.006105 | 0.299x | 0.005120 | 0.004998 | 0.976x |

The correction does not destroy the original precomputed clustering recovery:
the local reductions remain roughly 65% to 78% versus BASE across this scale
matrix. Standalone tree runtime remains noisy and close to BASE; no broad tree
speedup is claimed.

Before/after medians (seconds), from the same retained correction experiment:

| n | Precomputed BEFORE | Precomputed AFTER | Tree BEFORE | Tree AFTER |
|---|---:|---:|---:|---:|
| 128 | 0.000083166 | 0.000086292 | 0.000045000 | 0.000044083 |
| 512 | 0.000124791 | 0.000143833 | 0.000067459 | 0.000073459 |
| 2048 | 0.000351292 | 0.000412500 | 0.000219042 | 0.000233750 |
| 8192 | 0.001446167 | 0.001458125 | 0.001005500 | 0.001008458 |
| 32768 | 0.006140500 | 0.006104792 | 0.004978084 | 0.004998125 |

The precomputed path's source is identical before/after. At n=2048 its median
increases 17.4%, with overlapping process ranges: BEFORE
0.000351292/0.000408583/0.000329375; AFTER
0.000412500/0.000434959/0.000346667. Every sample is retained. This small experiment
does not establish a causal regression in that unchanged path; the substantial
improvement relative to concurrent BASE remains. OLD was not rerun for this
targeted correction; its weaker-contract comparisons remain in the original report.

## Validation

Focused correction tests pass locally:

- `tests/test_performance_clustering.py`
- `tests/test_performance_persistence.py`
- clustering contract/characterization/adapter/result-consumer tests
- centroid performance tests
- archive, persistence, Lance, migration, name-state and rendering tests

The depth regression test was first run against the eager grouping version and
failed at depths 3–64; after the production change all six depths passed.
The package smoke initially stopped at its source-origin assertion because
macOS `/var` resolves to `/private/var`. Resolving both paths fixed the diagnostic;
it was not a checkout import or product failure. Both attempts are retained.

| Check | Result |
|---|---|
| Focused clustering/centroid/persistence/archive suite | 512 passed |
| Corrective performance test files | 169 passed |
| Complete default suite with coverage | 1665 passed, 1 EVoC failure, 43 skipped, 3 deselected |
| Coverage | 90.3991% (5028/5562 statements) |
| Exact EVoC test, fresh diagnostic caches | BASE and AFTER fail identically; see below |
| Centroid differential | 216 cases; exact byte/dtype/shape/input-immutability checks pass |
| Persistence differential | 240 cases; scoped member/features checks pass |
| New malformed persisted COO tests on untouched BASE | 8 passed; rejection occurs in SciPy loading |
| Black (production/doc plus three focused test files) | Passed |
| Compilation | 35 Python files passed |
| Five-module mypy comparison | 19 diagnostics each; same messages after removing line numbers |
| mypy types/utility_functions/plotting | Passed |
| Wheel and sdist build | Passed; inherited setuptools discovery warnings |
| Noneditable installed wheel smoke | Depth-64 clustering, real legacy fixture, ZIP/Lance round trips passed |
| Dependency audit | 79 advisory rows in 9 inherited packages; no dependencies changed |

The default suite is not claimed green. Inherited typing/dependency diagnostics
are not fixed or suppressed by this performance correction.

Supported Linux/Python CI after integration with merged #211 is still required
before claiming full validation. No test threshold or default selection changed.

## EVoC assessment

No EVoC production code or threshold is changed. The original campaign retained
an earlier failure on both BASE and OPT:

- AMI `0.7327008099963787 < 0.75`
- 199/1000 assigned

The independent audit later could not reproduce that failure. It observed, for
both untouched BASE and OPT:

- AMI `0.9627363594320391`
- 691/1000 assigned
- eight final clusters
- identical native/adapter label hashes

That held under fixed-one-thread and default-thread settings, fresh Numba
caches and temporary copies of existing EVoC caches. The earlier event remains
unresolved; it is not labeled as established stochastic or platform behavior.
Source tracing identified no path from these performance changes to the
differing native EVoC result.

The correction rerun subsequently reproduced the earlier failure again:
1665 tests passed and only the EVoC quality test failed in the complete suite.
Separate exact-test runs on untouched BASE and corrected OPT both failed at
AMI approximately 0.732701, with 199/1000 assigned and 15 final clusters. Both
had label SHA256
`e95cd6adc250248e45440a8b72e5262e36e2b28383e7fba36b210fc65f31d98c`.
The original native/adapter equality assertion passed before the AMI assertion.
The capture helper reports symmetric AMI with arguments reversed, differing in
the last floating-point bits; the unchanged test assertion reports
`0.7327008099963787`. Both raw outputs are retained. These new failing observations
do not invalidate the auditor's intervening passing observations or establish
why results differ. No attempt was discarded or threshold weakened.

## Reproduction and upstream scope

Use a single provisioned environment and a checkout containing both historical
Git objects and the corrected working source:

```sh
python doc/performance_recovery/check_tree_depth.py --repo . \
  --output /tmp/toponymy-correction-new --include-scale
```

The output directory must be new. This exports/copies source to temporary
directories without changing Git or installing a revision. To recompute the
summary, load each worker JSON, add its `kind`, integer `case`, integer
`replication` and `arm` from its filename, and call `check_tree_depth.summarize`.
It uses every worker and requires nine observations per case. The manifest
contains raw-file hashes, source identities, commands and environment details.

Exact validation commands and exit codes are in `validation/commands.json`;
machine-specific driver scripts and logs are retained alongside it. They use
the unchanged default pytest selection, temporary caches, and numerical threads
fixed to one. Disabling the cache provider and Azure report-output plugin only
controls diagnostic files. Compilation writes temporary bytecode. Package build
and noneditable installed-wheel smoke use temporary directories outside source.
Text-log trailing whitespace may be stripped for Git hygiene; raw benchmark JSON
is unchanged.

Reviewer coordination limitation: the review agent wrote this report draft and
supplemental `validation/*-current.txt` logs despite a read-only assignment.
Those duplicate checks are retained separately and are not the primary evidence
in the validation table. Primary logs (`full.txt`, `evoc-after.txt`, etc.) and
the recorded command driver were preserved. No benchmark ran concurrently with
these tests. The reviewer reported replacing one failed build-wrapper log during
its retry; that supplemental attempt cannot be independently reconstructed and
is not used to establish package validation. The primary failed/successful smoke
attempts remain separate. The parent reconciled the report against its primary
logs; the reviewer's partial review is not claimed as a completed final audit.

[The upstream manifest](../upstream_file_manifest.md) lists the small proposed
transplant set. Full generated evidence stays in immutable campaign revisions
or an external checksummed artifact. No existing evidence or history is deleted.

## Self-audit

The correction does not move work outside the measured/public call, introduce a
global cache, add benchmark-size branches, weaken public validation, defer tree
construction, restore OLD's dense-ID implementation or change tree semantics.
The standalone API still validates public labels before grouping. Supplied
cluster trees still receive full validation through the fitted public path.

The pre-commit secret hook emitted broken-pipe diagnostics while scanning large
generated records but permitted the commit. Its high-signal patterns were also
checked independently with Python regex across all 249 changed/new files through
the evidence commit, with no findings. The hook/configuration was not bypassed
or modified; this is a scoped scan, not a universal security guarantee.
