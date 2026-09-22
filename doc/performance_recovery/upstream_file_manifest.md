# Proposed upstream file set after #211 merges

This is a transplant plan, not a deletion or history rewrite. The performance
branch keeps the complete campaign record. No upstream PR is open or authorized.
First identify the merged #211 revision, create a clean follow-up branch from it,
and transfer only the performance delta in the files below. Check the resulting
diff against merged #211 and rerun supported Linux Python 3.10/3.11/3.12 CI.

## Keep

Production (all five are performance deltas relative to PERF_BASE):

- `toponymy/clustering.py`
- `toponymy/types.py`
- `toponymy/plotting.py`
- `toponymy/utility_functions.py`
- `toponymy/serialization.py`

Tests:

- `tests/test_performance_clustering.py`
- `tests/test_performance_centroids.py`
- `tests/test_performance_persistence.py`

Reproduction tools and concise evidence:

- `doc/performance_recovery/benchmark.py`
- `doc/performance_recovery/run_campaign.py`
- `doc/performance_recovery/check_centroids.py`
- `doc/performance_recovery/check_persistence.py`
- `doc/performance_recovery/check_tree_depth.py`
- `doc/performance_recovery/REPORT.md` (condense historical narrative for upstream)
- `doc/performance_recovery/correction/REPORT.md` (results, validation and reproduction)
- `doc/performance_recovery/upstream_file_manifest.md`
- `doc/performance_recovery/correction/evidence_checksums.json`

Before transplanting, change report links to excluded evidence into immutable
fork-revision links or a checksummed downloadable artifact. Keep source/harness
hashes and commands. Preserve all observations, including slow runs and failed
attempts. The original full record is already available at
[campaign revision 0e0d267](https://github.com/agustinpabon/toponymy/tree/0e0d267eddc469a0ed659108f4241a5be3e97581/doc/performance_recovery).
The correction evidence is retained at
[revision 99b5952](https://github.com/agustinpabon/toponymy/tree/99b5952457c2f35f9c320d581eb6bac3b5635fbe/doc/performance_recovery/correction); preserve it as well. Do not transplant generated evidence and then delete it in later PR
commits: assemble the smaller file set directly on the future clean branch.

## Optional

- `doc/performance_recovery/root_causes.md` (prefer a concise version)
- `doc/performance_recovery/profile_centroids.py`
- `doc/performance_recovery/results/summary.json`
- `doc/performance_recovery/results/summary.md`
- `doc/performance_recovery/correction/measurements/summary.json`

## Exclude from upstream; retain in campaign revision or external artifact

Every campaign file not explicitly kept or optional above is excluded. This
includes, exactly by directory/pattern:

- `doc/performance_recovery/results/manifest.json`
- `doc/performance_recovery/results/raw/*.json` (75 original worker results)
- `doc/performance_recovery/results/worker-logs.json`
- `doc/performance_recovery/results/analysis.json`
- `doc/performance_recovery/results/README.md` (historical artifact instructions)
- `doc/performance_recovery/validation/*` (all historical logs/audits and README)
- `doc/performance_recovery/*-step*.json`
- `doc/performance_recovery/*-profile.txt`
- `doc/performance_recovery/baseline-initial.json`
- `doc/performance_recovery/centroid-phases-base.json`
- `doc/performance_recovery/future_pr.md`
- `doc/performance_recovery/correction/measurements/*` except optional summary
- `doc/performance_recovery/correction/validation/*`
- `doc/performance_recovery/correction/benchmark-run.txt`
- `.gitattributes` changes made only to fold excluded generated evidence

The original 50k-line cache/inventory manifest, per-run raw JSON, machine logs,
dependency audits and bulky profiles remain useful audit evidence but obscure
the small production change. This plan preserves reproducibility through the
harnesses, exact revisions, environment details, checksums and immutable evidence
references without placing every generated artifact in the upstream PR diff.
