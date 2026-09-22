# Future upstream PR preparation

Do not open this PR while #211 is unmerged. This file is a prepared draft,
not evidence of a published PR. The performance branch is stacked exactly on
`04c300c6a0fe1117531a64e6a7966b436eadfce7`.

Title:

`perf: reduce runtime overhead while preserving v0.6 ownership contracts`

Body:

---

The v0.6 ownership refactor repeatedly grouped and revalidated freshly built
cluster state, and persistence reconstructed sparse memberships one topic
column at a time. This follow-up shares transient canonical grouping between
cluster layers and trees and groups validated sparse memberships once during
eager loading. Private construction paths retain owned, read-only arrays;
public input, supplied-tree, archive, and sparse integrity checks remain.

It also reuses member counts for display hierarchies and reduces redundant
Numba division checks and centroid restoration temporaries. Centroid arithmetic
order and extreme-value behavior are preserved exactly; no fastmath, global
cache, lazy validation, or benchmark-specific path is introduced.

Local measurements cover OLD, the exact #211 baseline, and this implementation
at n=128/512/2048/8192/32768, plus separate first-call cache conditions. The
original sealed harness was unavailable, so these are explicitly documented
local reconstructions. OLD's precomputed and persistence contracts differ;
BASE/OPT outputs are checked for exact equivalence. Full methodology, raw
timings, memory evidence, root causes, and limitations are in
`doc/performance_recovery/REPORT.md`.

At n=2048, the median of three warm-process medians falls from 1.655 ms to
0.384 ms for precomputed clustering, 15.891 ms to 11.904 ms for synthetic
legacy loading, and 0.103 ms to 0.093 ms for centroids. The real legacy fixture
falls from 327.527 ms to 295.631 ms. Standalone tree medians are close with
overlapping process ranges, so no clear gain is claimed there. Precomputed
and synthetic persistence improvements persist across all five measured sizes.

Validation on macOS arm64 / Python 3.12.13:

- 157 added tests pass; focused clustering, centroid, and persistence suites pass.
- Extended existing properties pass; 216 centroid and 240 persistence
  differential cases match #211.
- Complete default suite: 1645 passed, 43 skipped, 3 deselected, **one failure**.
  Untouched #211 has the identical EVoC quality failure (AMI 0.73270081 versus
  0.75, 199/1000 assigned); no threshold or test selection was changed.
- Coverage 90.4%; Black, compilation, wheel/sdist, installed-wheel ZIP/Lance
  smoke checks, and offline Sphinx build pass.
- Focused mypy has the same 19 existing diagnostics as #211; inherited
  dependency advisories remain documented.

The existing EVoC failure requires resolution or reproduction on the supported
CI matrix before claiming full green validation. This draft's results must be
updated after rebasing onto merged #211 and rerunning validation.

---

After #211 merges, fetch upstream/main, inspect whether the merge preserved or
rewrote the baseline history, and transplant only the commits following
PERF_BASE. Review the resulting diff and rerun relevant tests/benchmarks.
Request explicit authorization before opening the upstream PR. Do not merge
#211 or this branch as part of the performance campaign.
