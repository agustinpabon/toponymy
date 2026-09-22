# Frozen local benchmark evidence

This directory contains the final reconstruction campaign's unedited manifest,
raw worker JSON, worker stdout/stderr, and generated summaries. It is not the
unavailable sealed Protocol v2.0.3 result set.

- `manifest.json`: exact revisions/source hashes, commands, execution order,
  initial/final Numba cache inventories, process times, errors, and completion
  status. There are five archive-generation jobs and 75 measurement workers.
- `raw/warm-*.json`: 45 processes, three per arm/size; two warmups and nine timed
  calls per operation, plus a separately instrumented memory call.
- `raw/cold-*.json`: 30 processes, one per arm/operation/cache condition;
  import time and one first operation call are recorded separately.
- `summary.json` / `summary.md`: median of three warm-process medians and
  cross-worker equivalence checks.
- `analysis.json`: records successful postprocessing after correcting a check
  that incorrectly required the tested project's own distribution metadata to
  match across revisions. OLD/BASE metadata is 0.5.2 and OPT is 0.6.0.dev0;
  imported source identities were verified independently. Every third-party
  version matches. The original manifest deliberately retains `status: failed`
  for this summary-only error; all 80 subprocesses succeeded. No raw file,
  workload, or timed sample was changed or discarded.
- `worker-logs.json`: losslessly consolidated stdout/stderr of every worker
  and archive-generation command, with original filenames and content hashes.
  This avoids adding 160 mostly empty log files to the review. Original log
  paths in the manifest refer to the execution location.

The manifest's absolute paths are historical execution locations. They need
not exist to inspect the evidence. Reproduction accepts explicit checkout,
interpreter, artifact, and cache paths; see the parent report and runner help.
The optimized source/HEAD remained frozen throughout measurement, although
documentation/results were being prepared as uncommitted files. Those status
entries are intentionally preserved rather than rewritten to look clean.

Generated archives and Numba binary caches are omitted to keep this evidence
reviewable. Archive sizes/hashes and cache inventories are retained, and the
committed harness can regenerate archives. The real legacy fixture remains
the existing `tests/data/mock-20ng.tm.zip`; it was not edited or copied here.
Raw measurements and cache inventories are marked as generated data for review
folding; the report, summaries, harness, production code, and tests stay visible.

Inputs, independent output verification, and imports are outside operation
timing. Archive extraction, public validation, membership materialization, and
construction/fit remain inside their respective timed operations. Independent
archive reference reads happen after the first target read. OS filesystem
caches were not cleared. Warm repetitions within a process are correlated;
cold results have only one observation per condition.

To recompute the corrected summaries from these raw files without rerunning
measurements, choose a new destination (the summarizer refuses overwrites):

```sh
python - <<'PY'
import json
from pathlib import Path
import sys

sys.path.insert(0, "doc/performance_recovery")
from run_campaign import summarize

source = Path("doc/performance_recovery/results").resolve()
destination = Path("/tmp/toponymy-summary-recheck")
destination.mkdir()
manifest = json.loads((source / "manifest.json").read_text())
specifications = [
    {**spec, "output": str(source / "raw" / Path(spec["output"]).name)}
    for spec in manifest["specifications"]
]
summarize(destination, specifications)
PY
```
