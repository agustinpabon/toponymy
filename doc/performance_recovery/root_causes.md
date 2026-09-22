# Root-cause investigation (before production changes)

PERF_BASE: `04c300c6a0fe1117531a64e6a7966b436eadfce7`, PR #211 head
verified using GitHub API and `git ls-remote` on 2026-09-22. PR is open.
OLD: `ca9cfedab141338fac57a8a0de1c4d947d8e9330` (also current upstream/main).
Original checkout was clean; campaign uses the separate `toponymy-perf`
worktree on `perf/v06-runtime-recovery`.

## Evidence and limitations

`doc/benchmark_results.rst` records Protocol v2.0.3, two warmups, medians of
three process medians, sequential matched OLD/NEW arms, separate cold/cache
conditions and AMD Rome/Linux/Python 3.12.0. It explicitly excludes the raw
harness and sealed tables from the source tree. Searches of the repository,
history, PR comments and local Developer/Documents/Downloads/Desktop/dev
locations did not locate that harness. The reported measured NEW predecessor
`58e0a84b6863e7307a90c78597130679dc185787` is not a local object and the fork
does not serve it by SHA. No claim of independently verifying its code identity
or reproducing its exact inputs is made.

Local reconstruction is therefore supplemental evidence, not a replacement
sealed result. Local machine: Apple M3, 8 logical CPUs, 16 GiB RAM,
macOS 27, Python 3.12.13. Preliminary profiles used the existing environment:
NumPy 2.4.6, SciPy 1.17.1, Numba 0.65.1, pandas 3.0.3, sklearn 1.8.0.
These profiles are diagnostic and not unprofiled benchmark observations.

The four `*-base-profile.txt` files contain 20 warmed calls each. Synthetic
labels used seed 1729, n=2048, d=64, 32/8/2 nested cluster IDs, noise every
17th row. Persistence profile uses the unmodified actual legacy fixture
`tests/data/mock-20ng.tm.zip`. The reproducible campaign harness records its
own exact inputs and environment separately.

## Precomputed clustering

Constructor, fit, build_cluster_layers, ClusterLayer construction and
build_cluster_tree all copy/validate labels. Every generated Cluster copies,
sorts and revalidates members already produced by stable grouping. ClusterLayer
reconstructs the partition to validate objects just generated from that
partition. The tree then groups the same labels again and validate_cluster_tree
rechecks containment already proved by construction.

20 profiled calls took 0.034 s: build_cluster_layers 0.022 s, Cluster
construction 0.011 s, grouping across both consumers 0.008 s and tree validation
0.006 s (nested times are not additive). Proposed boundary: owned validated
labels, one stable grouping, immediate private construction of layers/tree;
discard transient metadata. Keep public constructors and supplied-tree
validation. Do not trust persistent caches or mutable estimator parameters.

## Hierarchy

The published phrase is not enough to unambiguously distinguish label-to-tree
construction from plotting.construct_topic_hierarchy, so the local harness
will measure both explicitly. OLD's Numba label-to-tree implementation relies
on dense IDs and does not enforce complete containment. Restoring it would
regress sparse-ID and crossing/noise semantics.

20 standalone build_cluster_tree calls took 0.006 s, including 0.004 s grouping.
_group_labels stably sorts labels then calls np.unique with return_index,
causing a second sort of already sorted labels. Adjacent boundaries can provide
the same IDs/offsets. Reuse this grouping within precomputed construction.

20 display hierarchy calls took 0.010 s, including 0.007 s in Counter's
observation scan. Validated ClusterLayer memberships already supply sizes;
use those sizes for that type, preserve the generic compatibility path, and
count the entire corpus including noise at the root. Retain display tree checks.

## Centroids

OLD sums raw vectors then divides by count. #211 first finds independent
per-cluster/per-coordinate magnitudes, then accumulates value/scale/count,
then clips the scaled result to [-1,1] and restores magnitudes. This avoids
overflow and preserves constant subnormal coordinates, unlike raw sums or
premature division by count. There is no Python validation or input copy
inside this Numba kernel. It allocates result, counts, scales, and temporary
row arrays during final restoration. Dispatch is once per operation.

Preliminary isolated kernel experiments retain division order and compare
outputs exactly. Merely fusing the final row operations has negligible benefit
on this host; NumPy's Numba division error model plus fused scalar restoration
shows a modest improvement. Both divisors are provably positive when used:
scales are explicitly checked, and counts were incremented for each visited
non-noise row. Any candidate must retain nonfinite behavior, no fastmath,
and equality on extreme magnitudes, strides and supported dtypes. Raw-sum and
reciprocal-multiplication shortcuts are rejected because they change rounding
or overflow/underflow behavior. Remaining arithmetic cost may be necessary.

## Legacy persistence

OLD deserializes and returns without eager integrity validation or Topic
materialization. #211 validates ZIP paths/duplicates, JSON keys/configuration,
declared layer/full inventory, finite aligned arrays, sparse structure,
duplicates and partitions, topic identities, prompts/state and tree containment.
These are real new contracts and must stay in the timed load.

20 loads of the real legacy fixture took 6.183 profiled seconds: extraction
4.309 s (zlib decompression 3.329 s), eager topics 1.106 s. There are 5,380
per-topic CSR column slices, costing 0.390 s plus nonzero extraction 0.308 s.
Topic rows are materialized once for identity checks and again for construction.
One validated sparse traversal and one row materialization can avoid those
conversions without relaxing acceptance. Sparse check_format, duplicate checks
(including explicit zeros), partition checks and borrowed-array preservation
remain essential. ZIP inventory/rglob work is small; changing it risks
platform-dependent path semantics and is not justified by this profile.
Repeated history/name-state validation is small and is safer to retain for
public mutable state unless a clearly scoped internal boundary is introduced.
