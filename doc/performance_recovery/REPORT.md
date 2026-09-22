# Runtime performance recovery after PR #211

Campaign date: 2026-09-22. Branch: `perf/v06-runtime-recovery`.

The performance changes preserve #211's ownership model and public validation
boundaries. They remove repeated grouping/materialization work and reduce
centroid kernel overhead without changing its arithmetic order. Production
changes are confined to five modules; the existing test suite and CI
configuration are unchanged.

**Validation is not fully green on this host.** The complete optimized suite
has 1645 passes and one EVoC quality failure; untouched PERF_BASE has 1488
passes and the identical failure/score. The 157 added tests pass, coverage is
90.4%, and the focused, extended-property, package, and documentation checks
pass. The unchanged baseline failure must be resolved or reproduced on the
supported CI matrix before claiming complete success.

## Git identities and scope

| Role | Commit |
|---|---|
| OLD, also upstream/main at campaign start | `ca9cfedab141338fac57a8a0de1c4d947d8e9330` |
| PERF_BASE, current PR #211 HEAD verified through GitHub and remote refs | `04c300c6a0fe1117531a64e6a7966b436eadfce7` |
| Optimized HEAD measured and validated | `b2dedf32f5294e90328b0b02879b8153bc0bf357` |

The branch starts exactly at PERF_BASE, in an isolated worktree reusing the
existing repository. Upstream/main was not merged into it. Subsequent commits
collect results/documentation and correct a summary-only metadata check; the
benchmark workload and production source remain unchanged. Their hashes
are frozen in the campaign manifest. The final delivery commit can therefore
differ from the measured HEAD without changing the measured implementation.

Production files changed:

- `toponymy/clustering.py`: canonical grouping reused by layer/tree builders.
- `toponymy/types.py`: two private constructors with explicit proven invariants.
- `toponymy/plotting.py`: membership counts reused for canonical cluster layers.
- `toponymy/utility_functions.py`: centroid division checks and row temporaries reduced.
- `toponymy/serialization.py`: grouped sparse membership and topic-row materialization.

Three `tests/test_performance_*.py` files add regression/property coverage.
Everything else is campaign evidence or reproducible diagnostic tooling under
`doc/performance_recovery/`. No dependency, CI, public API, or archive format
changes are included.

## Published result versus local evidence

The sealed source report is `doc/benchmark_results.rst`, Protocol v2.0.3.
It describes AMD Rome/Linux/Python 3.12.0, two warmups, and medians of three
process medians. Its raw harness and sealed tables were explicitly kept outside
the repository and could not be located in history, PR discussion, or the
available local artifact directories. Its recorded NEW predecessor,
`58e0a84b6863e7307a90c78597130679dc185787`, was not available as a Git object.
This campaign does not claim to verify that predecessor's code identity or
reproduce its exact sealed workload.

The published n=2048 values supplied for investigation are:

| Operation | Published OLD seconds | Published #211 NEW seconds |
|---|---:|---:|
| Centroids | 0.000246 | 0.000937 |
| Precomputed clustering | 0.000717 | 0.004033 |
| Topic hierarchy | 0.000233 | 0.000362 |
| Legacy persistence read | 0.023619 | 0.034508 |

No optimized value is inserted into that table: comparing this Mac's timings
directly with the sealed Linux numbers would be misleading. The local
reconstruction below uses the same machine, interpreter, inputs, harness, and
archive bytes for all three revisions. BASE versus OPTIMIZED exercises the
same contracts. OLD comparisons require the qualifications below.

## Root causes and changes

The pre-change investigation and profiles are in [root_causes.md](root_causes.md).
It was committed before production changes; profile cumulative times overlap
and must not be added together.

### Precomputed clustering and hierarchy

#211 repeatedly copied/validated labels, grouped them independently for layers
and trees, sorted already ordered members in public constructors, reconstructed
partitions, and validated its freshly generated tree. `_group_labels` also
called `np.unique(..., return_index=True)` after stable sorting, sorting the
same values again. The profiled 20-call precomputed path spent 0.022 of 0.034
seconds inside layer construction; 0.008 seconds included repeated grouping.

The optimized fit validates and owns labels once, derives one canonical
grouping per layer, and immediately feeds both layers and the tree. Adjacent
boundaries replace the second label sort. Private constructors only consume
that freshly established partition; they retain independently owned, read-only
member arrays and owned, read-only labels. They are not public bypass switches.
No metadata persists across calls, and estimator parameters are revalidated on
every fit. Public object constructors retain their checks. User-supplied trees
still undergo full validation and copying.

Generated trees still attach each cluster to its nearest completely containing
upper cluster, skipping crossings and partial noise. Construction proves unique
membership, valid nodes, increasing layer direction, and containment, so a
second public tree validation pass is unnecessary. Non-contiguous and maximum
int64 IDs are never used as allocation sizes in this path. Empty and all-noise
layers retain their behavior.

The requested reference to OLD's Numba hierarchy builder identifies
`build_cluster_tree` as the primary hierarchy measurement. Its standalone API
still validates/groups its own input; it benefits from the cheaper grouping.
OLD's dense-ID/partial-containment implementation was not restored.

The additional display hierarchy operation, `construct_topic_hierarchy`, uses
canonical `ClusterLayer` member counts instead of rescanning every observation
with `Counter`. Generic/iterator inputs retain the original counting path.
Root size still includes noise, and display-tree checks remain intact.

### Centroids

OLD summed raw vectors and divided once. #211 first computes a magnitude for
each cluster/coordinate, accumulates `value / scale / count`, clips to the
mathematical mean range, and restores the magnitude. This protects against
overflow and preserves subnormal constant coordinates. The extra pass and
division work is real contract cost, not simply allocation overhead.

Diagnostic per-phase medians at n=2048 were 3.500 microseconds for allocation,
18.167 for count/scale, 75.625 for accumulation, 5.792 for restoration, and
0.042 for an empty dispatcher call; the whole kernel was 99.917 microseconds.
These independently called kernels have different setup/dispatch boundaries,
so their times are not additive decompositions of the whole measurement.
There is no Python validation or input copy inside this kernel.

The change uses Numba's NumPy division error model: a visited row has a positive
count and a scale is used only after its positive check. Redundant generated
division-by-zero guards are therefore unnecessary. Scalar clipping/restoration
also avoids temporary row arrays. Division order, clipping, dtype behavior,
and accumulation order are retained. There is no fastmath, reciprocal
multiplication, raw-sum shortcut, or magnitude-specific dispatch.

Exact byte/dtype/shape comparison against PERF_BASE passed 216 cases spanning
float32/float64/int64/uint64, three memory layouts, noise, empty arrays, and
extreme/subnormal finite coordinates. Separate tests preserve non-finite
behavior and exact hexadecimal reference results. The stronger numerical
contract remains more expensive than OLD.

### Legacy persistence

OLD returned a mostly deserialized object. #211 additionally performs archive,
metadata, sparse, topic, state, and containment validation and eagerly builds
Topics. In the actual legacy fixture profile, 4.309 of 6.183 seconds across 20
loads were extraction, including 3.329 seconds of decompression. Repeated CSR
column slices and nonzero extraction cost another 0.390 and 0.308 seconds.

After all existing sparse validation, the optimized path groups nonzero COO
coordinates by column and row once and copies each topic's ordered members.
It materializes dataframe records once and groups/sorts those records by layer.
Member arrays retain their independent ownership, read-only flags, ordering,
and SciPy matrix-versus-array index dtype behavior, including empty COO arrays.
Grouping storage depends on populated columns rather than the largest label.

Sparse shape/data checks, finite/nonnegative values, `check_format`, duplicate
coordinates including explicit zeros, and partition checks remain. An explicit
mutated-COO coordinate bounds check preserves rejection previously performed
by downstream conversion/slicing. Table identity/UID/coverage, metadata,
name/history state, tree containment, and eager validation remain. ZIP member
path, duplicate-entry, inventory, extraction, and filesystem checks are
unchanged. A 240-case differential across CSR/CSC/COO matrices and arrays
matches PERF_BASE member values, order, dtype, ownership, and features.

## Local measurement method

Host: Apple M3, eight logical CPUs, 16 GiB RAM, macOS 27 arm64; Python 3.12.13.
Core versions: NumPy 2.4.6, SciPy 1.17.1, Numba 0.65.1, llvmlite 0.47.0,
pandas 3.0.3, scikit-learn 1.8.0, fast_hdbscan 0.3.2, EVoC 0.3.1.
All active distribution versions, thread settings, import paths, CPU, source
and harness hashes, and raw measurements are recorded per worker.

The dedicated environment borrowed the existing dependency directory read-only
and installed missing validation tools locally. Environment repairs and
limitations are documented in [validation/README.md](validation/README.md).
All arms use exactly the same interpreter. BLAS/OpenMP/Numba thread variables
are set to one. No tests or profiles run alongside measurements; the machine
is a local desktop, not a pinned or otherwise fully controlled benchmark host.

The reconstruction uses seed 211, float64 standard-normal vectors with 64
dimensions, approximately 5% shared noise, and three nested label layers.
The fine cluster count is `min(512, max(4, n // 32))`, then divided by 4 and 16
for higher layers. The 512 cap keeps all shared archives below OLD's legacy UID
limit; it is part of the disclosed harness input, not production behavior.
Sizes are 128, 512, 2048, 8192, and 32768. Archives are deterministically
generated once in the common legacy 0.1 layout and reused byte-for-byte.
The real `tests/data/mock-20ng.tm.zip` fixture is measured separately.

Each warm arm/size runs in three independent processes, with arm order rotated
across replications. Each process performs two warmups and nine timed calls.
The reported estimator is the median of the three process medians. Nine calls
within one process are correlated observations, not nine independent trials.
Three process replications support a local result, not broad statistical
superiority. Every observation is retained, including slow ones.

Constructor plus fit is timed for precomputed clustering; standalone tree
building starts with labels; display hierarchy starts with fitted layers;
archive loading directly times `TopicModel.from_file`, including extraction,
validation, and eager materialization. Inputs and independent output oracles
are outside timing. No oracle is passed into production. Centroid outputs are
checked by exact BASE/OPT digests and against an independent mean reference.

OLD has no `PrecomputedClusterer`; its disclosed reference constructs old layer
objects, centroids, and tree. It is a changed-work comparison. OLD persistence
lacks the new integrity/materialization contract, and OLD display hierarchy
reports leaf sizes of one. Those OLD outputs are checked against their own
historical contracts, not silently made equivalent. Common persisted data is
checked across all arms; BASE/OPT outputs must match exactly.

Cold n=2048 runs use one process per operation/arm/cache condition. One starts
with an empty Numba directory; a second uses the directory left by the first
process. OLD kernels with `cache=False` still compile in both processes.
Imports are measured separately; OS file caches are not flushed. This is
exploratory first-call evidence, not a cold-start superiority claim.

Memory is a separate `tracemalloc` call after timing, not instrumentation
inside timed samples. It measures Python-tracked allocations, not total native
memory. Whole-worker peak RSS includes imports, compilation, setup, checks,
and all operations; it cannot be assigned to one operation.

## Results

All 75 measurement workers and five archive-generation jobs completed with
zero exit status. Exact BASE/OPT outputs match across every size, replication,
and cache condition; common persisted outputs match across all three arms.
The original summary check failed because it treated the tested Toponymy
distribution as a shared dependency: OLD/BASE inherited installed metadata
`0.5.2`, while the optimized checkout's build metadata says `0.6.0.dev0`.
All third-party dependency versions match. Imported source paths and Git/source
hashes, not installed metadata, identify the code actually measured.

The corrected summary excludes only the tested project from dependency
equality and reports its observed metadata explicitly. No timed code or sample
changed and no measurements were rerun or discarded. The original failed
manifest is preserved; [results/analysis.json](results/analysis.json) records
the successful corrected analysis and hashes of every raw file. Toponymy's
version metadata is assigned at import and is not used by the timed operations.

### Warm n=2048

Seconds; ratios are OPTIMIZED / comparator, so below one means shorter runtime.

| Operation | OLD | #211 | OPTIMIZED | vs #211 | vs OLD |
|---|---:|---:|---:|---:|---:|
| Centroids | 0.000086416 | 0.000102916 | 0.000092875 | 0.902 | 1.075 |
| Precomputed clustering* | 0.000464292 | 0.001655000 | 0.000383792 | 0.232 | 0.827 |
| Topic hierarchy / tree | 0.000137542 | 0.000242625 | 0.000234500 | 0.967 | 1.705 |
| Legacy persistence read* | 0.007027500 | 0.015891375 | 0.011903667 | 0.749 | 1.694 |

*OLD contracts differ as described above; these are reference times, not an
equal-work OLD-versus-NEW claim. BASE/OPT use the same contract.

At n=2048, precomputed clustering is 76.8% lower and synthetic legacy loading
25.1% lower than BASE by this estimator; centroids are 9.8% lower. The tree
median is 3.3% lower, but process ranges overlap substantially, so there is
no convincing standalone tree speedup at this size.

### Additional consumers and actual legacy fixture

| Operation | OLD | #211 | OPTIMIZED | vs #211 | vs OLD |
|---|---:|---:|---:|---:|---:|
| Display hierarchy, n=2048* | 0.000314958 | 0.000344333 | 0.000055459 | 0.161 | 0.176 |
| Actual legacy ZIP, n=18170, d=768* | 0.270373584 | 0.327527084 | 0.295630500 | 0.903 | 1.093 |

The actual fixture contains 18,170 observations and 768 dimensions, with
70,519,384 compressed bytes. Its 9.7% reduction is smaller than the synthetic
case because extraction/decompression dominates. Display hierarchy is an
additional operation, not a relabeling of the requested tree benchmark.

### Scale behavior

| n / Operation | OLD s | #211 s | OPTIMIZED s | vs #211 | vs OLD |
|---|---:|---:|---:|---:|---:|
| 128 / Centroids | 0.000007333 | 0.000008625 | 0.000006708 | 0.778 | 0.915 |
| 128 / Precomputed clustering* | 0.000039791 | 0.000261750 | 0.000101167 | 0.387 | 2.542 |
| 128 / Topic hierarchy / tree | 0.000010875 | 0.000047250 | 0.000044125 | 0.934 | 4.057 |
| 128 / Legacy persistence read* | 0.005280042 | 0.008305708 | 0.007374708 | 0.888 | 1.397 |
| 512 / Centroids | 0.000022125 | 0.000025792 | 0.000023333 | 0.905 | 1.055 |
| 512 / Precomputed clustering* | 0.000105625 | 0.000499333 | 0.000115416 | 0.231 | 1.093 |
| 512 / Topic hierarchy / tree | 0.000032750 | 0.000074750 | 0.000063958 | 0.856 | 1.953 |
| 512 / Legacy persistence read* | 0.005353167 | 0.008669375 | 0.006983625 | 0.806 | 1.305 |
| 2048 / Centroids | 0.000086416 | 0.000102916 | 0.000092875 | 0.902 | 1.075 |
| 2048 / Precomputed clustering* | 0.000464292 | 0.001655000 | 0.000383792 | 0.232 | 0.827 |
| 2048 / Topic hierarchy / tree | 0.000137542 | 0.000242625 | 0.000234500 | 0.967 | 1.705 |
| 2048 / Legacy persistence read* | 0.007027500 | 0.015891375 | 0.011903667 | 0.749 | 1.694 |
| 8192 / Centroids | 0.000356542 | 0.000468750 | 0.000408834 | 0.872 | 1.147 |
| 8192 / Precomputed clustering* | 0.002332791 | 0.006735334 | 0.001486541 | 0.221 | 0.637 |
| 8192 / Topic hierarchy / tree | 0.001062500 | 0.001030250 | 0.001018417 | 0.989 | 0.959 |
| 8192 / Legacy persistence read* | 0.017356292 | 0.047845083 | 0.026988375 | 0.564 | 1.555 |
| 32768 / Centroids | 0.001484000 | 0.001891750 | 0.001786417 | 0.944 | 1.204 |
| 32768 / Precomputed clustering* | 0.010271333 | 0.021182291 | 0.006393959 | 0.302 | 0.623 |
| 32768 / Topic hierarchy / tree | 0.005677792 | 0.005445750 | 0.005285292 | 0.971 | 0.931 |
| 32768 / Legacy persistence read* | 0.055257250 | 0.159723208 | 0.080498500 | 0.504 | 1.457 |

Precomputed reductions persist at every measured size (61.3–77.9%).
Synthetic persistence reductions grow from 11.2% at n=128 to 49.6% at n=32768
as repeated per-topic slicing becomes more costly. Centroid median reductions
range from 5.6% to 22.2%. Standalone tree differences are small at larger sizes
and have overlapping process ranges; no robust large-scale superiority is
claimed for that operation. OLD remains faster for some small-size trees and
numerical/persistence cases because its contracts do less work.

At n=2048 the three process-median ranges (BASE / OPT, seconds) are:

| Operation | BASE process-median range | OPT process-median range |
|---|---:|---:|
| Centroids | 0.000101041–0.000103833 | 0.000090375–0.000096000 |
| Precomputed clustering* | 0.001640083–0.001801208 | 0.000378958–0.000564292 |
| Topic hierarchy / tree | 0.000232208–0.000244250 | 0.000221125–0.000275625 |
| Legacy persistence read* | 0.015609541–0.017475583 | 0.010937292–0.012082208 |

These ranges are descriptive, not confidence intervals. All individual timed
samples and process medians are retained in [results/raw](results/raw).

### Separate memory measurements

Median of three separately traced peak allocations, bytes:

| n / Operation | OLD | #211 | OPTIMIZED |
|---|---:|---:|---:|
| 2048 / Centroids | 34112 | 66480 | 66480 |
| 2048 / Precomputed clustering* | 136384 | 396627 | 246900 |
| 2048 / Topic hierarchy / tree | 91872 | 183573 | 135536 |
| 2048 / Legacy persistence read* | 1264048 | 1353139 | 1353179 |
| 32768 / Centroids | 267072 | 528816 | 528816 |
| 32768 / Precomputed clustering* | 1765184 | 6130604 | 3748950 |
| 32768 / Topic hierarchy / tree | 1419616 | 2878781 | 2105118 |
| 32768 / Legacy persistence read* | 18669832 | 20756261 | 20756659 |

Precomputed peaks fall about 38% and standalone tree peaks about 26–27% at
these sizes. Centroid peak storage is unchanged; persistence peaks are
effectively unchanged. This does not establish total native-memory reduction.
Whole-worker RSS ranged from 1121–1728 MB for OLD, 302–1085 MB for BASE, and
276–1059 MB for OPT; imports/compilation and fixture checks make those unsuitable
for attributing an operation-specific improvement.

### Cold / cache behavior

One first operation call, seconds; imports excluded and shown separately.
These single observations cannot establish cold-performance superiority.

| Operation / Numba cache | OLD | #211 | OPTIMIZED | vs #211 | vs OLD |
|---|---:|---:|---:|---:|---:|
| Centroids / empty | 0.332646792 | 1.230541583 | 0.515842250 | 0.419 | 1.551 |
| Centroids / primed | 0.972733042 | 0.086623292 | 0.088870750 | 1.026 | 0.091 |
| Precomputed* / empty | 1.640998166 | 0.002092958 | 0.000815708 | 0.390 | 0.000 |
| Precomputed* / primed | 1.035928125 | 0.002516834 | 0.000611125 | 0.243 | 0.001 |
| Tree / empty | 1.441936417 | 0.000432791 | 0.000522958 | 1.208 | 0.000 |
| Tree / primed | 0.006519542 | 0.000664917 | 0.000433792 | 0.652 | 0.067 |
| Display* / empty | 0.000738958 | 0.000553583 | 0.000207333 | 0.375 | 0.281 |
| Display* / primed | 0.000755916 | 0.000573209 | 0.000226667 | 0.395 | 0.300 |
| Legacy read* / empty | 0.223996708 | 0.107553000 | 0.052846333 | 0.491 | 0.236 |
| Legacy read* / primed | 0.086067458 | 0.059850959 | 0.052874041 | 0.883 | 0.614 |

Import-time ranges across these five operations, seconds:

| Arm | Empty Numba directory | Previously populated directory |
|---|---:|---:|
| old | 52.167–75.438 | 9.580–17.946 |
| base | 0.885–1.589 | 0.859–1.128 |
| optimized | 0.694–0.874 | 0.825–0.852 |

OLD performs substantial work at import, visible here rather than hidden in
the operation comparison. #211 already removed that runtime coupling; this
branch preserves it. A primed directory does not imply a warmed dispatcher:
the process is new, and uncached kernels still compile. Some cold ratios
reverse or vary sharply; no optimization was selected to exploit those single
observations. In particular, optimized primed centroid time is slightly higher
than BASE, and empty-cache standalone tree time is higher in this sample.

The complete warm table is also available as [results/summary.md](results/summary.md).
The manifest and raw JSON preserve commands, dependencies, hashes, cache
inventories, and every observation.

### Incremental checks

Before accepting each optimization, its focused tests and relevant warm
benchmark were run, with a separate memory measurement. These are diagnostic
single-process medians (two warmups, nine calls), recorded while changes were
still uncommitted, not independent final campaign estimates. Their raw files
are the `*-step-base.json` / `*-step.json` pairs in this directory.

| Step / operation | BASE seconds | Candidate seconds | BASE peak bytes | Candidate peak bytes |
|---|---:|---:|---:|---:|
| Clustering / precomputed | 0.001525583 | 0.000315208 | 396987 | 248245 |
| Clustering / tree | 0.000229250 | 0.000204333 | 183637 | 135536 |
| Clustering / display hierarchy | 0.000329959 | 0.000046000 | 10236 | 8132 |
| Centroids | 0.000092666 | 0.000090000 | 66480 | 66480 |
| Persistence / synthetic legacy | 0.012202334 | 0.008185208 | 1357497 | 1356902 |
| Persistence / actual legacy fixture | 0.256487125 | 0.243950167 | 126525808 | 126526097 |

Small peak differences in persistence are allocation noise, not evidence of
reduced total memory. The final frozen campaign is the basis for conclusions.

## Validation and self-audit

See [validation/README.md](validation/README.md) and its raw logs for the full
check inventory. The sole full-suite failure is the same on base and optimized:
EVoC AMI `0.7327008099963787 < 0.75`, with 199/1000 observations assigned.
Five-module mypy reports the same 19 existing diagnostics in both revisions;
the three other changed modules pass. Dependency advisories are inherited and
documented separately. Neither typing nor dependency auditing is claimed clean.
The final audit reports 79 advisory rows (42 distinct advisory IDs) in nine
inherited packages. The initial 81-row audit is also retained; a validation-tool
dependency update removed the two AnyIO findings before final measurements.

The added trusted-path tests cover source mutation, independent owned arrays,
clone/refit, reassigned invalid estimator parameters, supplied malformed trees,
crossing hierarchies, gappy/max-int64 labels, empty/all-noise layers, iterator
compatibility, exact centroid arithmetic, malformed sparse structures,
duplicate/zero coordinates, giant sparse column IDs, retry after rejection,
topic-table consistency, and matrix/array dtype details. Existing malformed
ZIP, path traversal, duplicate inventory, metadata, tree, and persistence
compatibility tests remain in the complete suite.

Self-audit and independent code/security review found no benchmark-specific
production branches, n=2048 cases, environment-specific production changes,
global result caches, deferred validation, or shifted timed work. Private
grouping metadata exists only within a call after validation. Public input
checks were retained; generated-state invariants replaced redundant checks
only where construction establishes them. No tests, thresholds, dependency
constraints, or CI settings were weakened. Differential tests and benchmark
output checks support equivalence; they are not a proof over every conceivable
malformed archive.

Rejected ideas: restoring OLD's dense-ID tree, raw centroid summation, reordered
or reciprocal divisions, fastmath, mutable persistent grouping caches, borrowed
topic member views, skipping sparse duplicate/check_format checks, lazy archive
validation, and changing ZIP inventory/extraction logic. Each risks a protected
contract or changes substantially more code than the profile justifies.
Repeated public history/name-state validation is retained because it is small
and public model state can be mutated.

## Reproduce and deliver

`run_campaign.py` accepts explicit OLD/BASE/OPT source paths and an interpreter.
Artifact and cache roots must be new. For example, after preparing detached
OLD and PERF_BASE checkouts and installing the shared dependencies:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True python doc/performance_recovery/run_campaign.py \
  --repos /path/to/old /path/to/base /path/to/optimized \
  --python /path/to/shared-venv/bin/python \
  --output /tmp/toponymy-new-campaign \
  --cache-root /tmp/toponymy-new-campaign-cache
```

The manifest records the exact commands actually run, execution order,
source hashes, cache inventories, worker elapsed time, and errors. The runner
rejects source/HEAD/harness changes during measurement, differing third-party dependencies
or inputs, and BASE/OPT output mismatches. The raw result archive excludes
regenerable ZIPs and Numba binaries; their hashes and inventories are retained.

This is a stacked branch while #211 is open. No upstream PR or merge is
authorized. The future PR title/body is in [future_pr.md](future_pr.md).
After #211 merges, fetch upstream/main, identify how its history was integrated,
rebase only commits after PERF_BASE, verify the resulting diff contains only
this follow-up, and rerun relevant full validation and performance checks.
Opening the upstream PR still requires explicit authorization.
