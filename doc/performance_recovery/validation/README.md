# Historical validation evidence

The original checks below ran locally on macOS arm64 / Python 3.12.13. The production code
under test is the code in measured commit
`b2dedf32f5294e90328b0b02879b8153bc0bf357`. No CI settings, existing tests,
quality thresholds, or dependency constraints were changed.

## Original default suite: one recorded failure on both revisions

| Revision | Passed | Failed | Skipped | Deselected |
|---|---:|---:|---:|---:|
| PERF_BASE `04c300c6a0fe1117531a64e6a7966b436eadfce7` | 1488 | 1 | 43 | 3 |
| Optimized | 1645 | 1 | 43 | 3 |

Both original runs failed only
`test_evoc_refactor_default_hierarchy_quality_matches_original_threshold`
in `tests/test_clustering_quality.py`: adjusted mutual information is
`0.7327008099963787`, below the unchanged `0.75` threshold, with 199 of 1000
observations assigned. This occurs with EVoC 0.3.1 on this host. It is evidence
that the event affected both revisions in those runs. Its cause remains
unresolved; stochastic or platform behavior has not been established.

The subsequent independent audit passed the exact test on untouched BASE and
OPT: AMI `0.9627363594320391`, 691/1000 assigned, eight final clusters and
identical native/adapter label hashes. Fixed-one/default threads, fresh Numba
caches, and temporary copies of existing EVoC caches all passed. The auditor's
optimized complete suite passed with 1646 passed, 43 skipped and 3 deselected.
Source tracing identified no path from these performance changes to the differing
native EVoC result. These observations do not erase the retained earlier failures.
Linux Python 3.10/3.11/3.12 CI after integration with merged #211 remains required
before claiming full validation. New correction checks are reported separately in
[the correction report](../correction/REPORT.md).

The correction run has since reproduced the earlier failure again: 1665 passed,
one EVoC failure, 43 skipped and 3 deselected. Separate exact-test BASE/OPT runs
both fail with the same 199 assigned observations and identical label hashes.
The intervening independent passing audit remains part of the evidence; the
cause of the difference remains unresolved.

The default project selection is `-m 'not external'`. The 43 skips retain the
repository's normal opt-in model/service/platform requirements. No extra
exclusion was added for the failing test. Optimized line coverage is
90.3991% (5028/5562 statements); see `coverage.json`.

## Additional checks

| Check | Result |
|---|---|
| Clustering focused suite, including new trusted-path properties | 169 passed |
| Centroid focused suite, including existing extreme-value contracts | 108 passed |
| Persistence focused suite, including archive/Lance compatibility and new sparse cases | 277 passed |
| Extended existing clustering/prompt property profile | 85 passed; 3000 clustering and 2000 parser examples |
| Centroid PERF_BASE differential | 216 cases, exact bytes/dtype/shape and input immutability |
| Persistence PERF_BASE differential | 240 cases, six matrix/array storage formats, exact member ordering/dtype/ownership/features |
| Black, project command and three new test files | Passed |
| Python compilation | Passed |
| mypy, five changed production modules | 19 diagnostics in each revision, same normalized messages |
| mypy, `types.py`, `utility_functions.py`, `plotting.py` | Passed |
| Wheel and source distribution build | Passed, inherited setuptools discovery warnings |
| Installed wheel from outside source checkout | Import, clustering, legacy ZIP read, ZIP and Lance round trips passed |
| Sphinx HTML, warnings as errors, offline intersphinx override | Passed |

The five-module mypy check used `--follow-imports=silent
--ignore-missing-imports`; it is not a claim of whole-project typing coverage.
Remaining diagnostics concern existing optional/override annotations and Path
annotations in clustering/serialization. The repository does not define a
mypy CI command. The exact focused command used in PR #211 was unavailable.
Black checked all 32 Python files under `toponymy/` and `doc/` plus the three
added test files. It skipped notebooks because its optional Jupyter formatter
extra was absent; no notebook was changed by this branch.

## Reproduction commands

From the optimized checkout, with its dependency environment provisioned:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True python -m pytest --cov=toponymy --cov-report=term --cov-report=json:/tmp/toponymy-coverage.json
TOPONYMY_PROPERTY_PROFILE=extended LITELLM_LOCAL_MODEL_COST_MAP=True python -m pytest -q tests/test_clustering_contracts.py tests/test_prompt_contracts.py
python doc/performance_recovery/check_centroids.py --base /path/to/base --optimized /path/to/optimized
python doc/performance_recovery/check_persistence.py --base 04c300c6a0fe1117531a64e6a7966b436eadfce7 --output /tmp/persistence-equivalence.json
python -m black --check --diff --target-version py310 toponymy/ doc/
python -m black --check tests/test_performance_clustering.py tests/test_performance_centroids.py tests/test_performance_persistence.py
python -m compileall -q toponymy doc/performance_recovery
python -m mypy --follow-imports=silent --ignore-missing-imports toponymy/clustering.py toponymy/types.py toponymy/utility_functions.py toponymy/plotting.py toponymy/serialization.py
python -m build --no-isolation
```

For the base suite, run the same interpreter from a clean detached PERF_BASE
worktree, without optimized source on `PYTHONPATH`. The centroid differential
accepts checkout paths; the persistence differential accepts a base Git revision
and loads that serialization source against the optimized shared types. Those
types' public constructors are unchanged. The centroid checker deliberately
disables disk caching for dynamically loaded Numba functions.

The documentation check used Sphinx's Python API with
`confoverrides={"intersphinx_mapping": {}}`, `warningiserror=True`, and
`freshenv=True`. This disables only external documentation inventory fetches
for an offline local build. It does not modify repository configuration.
An arm64 Pandoc 3.11 binary from the official release was used because the
downloaded `pypandoc-binary` wheel contained an incompatible executable.

## Environment recovery and failed attempts

The initial full run had 15 failures: missing `ipykernel`, the existing
Cohere 7.0.4 below the project's 7.0.8 requirement, and the EVoC failure.
Installing the project-locked ipykernel 7.2.0 and Cohere 7.0.8 in the isolated
campaign environment fixed the dependency-related failures. Their installation
temporarily shadowed compatible tokenizers/Hugging Face versions; those were
restored to tokenizers 0.22.2 and huggingface-hub 0.36.2 before final validation
and benchmarks. No dependency files were edited.

An early ad hoc centroid differential imported Numba code under a dynamic
module name and wrote five task-generated cache files into the base checkout.
A subsequent base suite exposed seven cache import errors. Those five files
were quarantined, the committed checker was made cache-free, and a clean
detached PERF_BASE worktree was used for the final base suite. Its final result
is the single EVoC failure above; none of the cache errors remain. This was a
diagnostic tooling error, not an optimization result.

The existing checkout's dependency directory was borrowed read-only using a
`.pth` file in a dedicated virtual environment after a frozen environment
sync stalled. Additional validation tools were installed only in the dedicated
environment. Every final benchmark arm used that same interpreter and active
dependency versions. This is a documented local environment, not a claim that
the complete lockfile was freshly provisioned.

The dependency audit is recorded separately in `dependency-audit.json`.
The final result is 79 advisory rows, 42 distinct IDs, in nine inherited
packages. The initial audit had 81 rows in ten packages; the validation-tool
environment update removed two AnyIO findings. Both snapshots are retained.
Inherited advisories are not performance regressions; they remain a limitation
and are not covered by a claim of a vulnerability-free environment. The
production diff adds no network, model-download, image-decoding, or dependency
installation surfaces. A separate code/security review found no blocking
findings in the final diff, including the trusted sparse grouping boundary.

Text validation logs have trailing whitespace removed for repository hygiene;
reported results and diagnostic lines are otherwise preserved. Benchmark raw
JSON and the original measurement manifest remain byte-for-byte copies.
