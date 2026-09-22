#!/usr/bin/env python3
"""Compare optimized membership materialization with the frozen PR #211 source.

This is a correctness check, not a timing workload. The baseline serialization
module is pure Python; no Numba functions are copied or compiled under aliases.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import types

import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
PERF_BASE = "04c300c6a0fe1117531a64e6a7966b436eadfce7"
STORAGE_TYPES = (
    sparse.csr_matrix,
    sparse.csc_matrix,
    sparse.coo_matrix,
    sparse.csr_array,
    sparse.csc_array,
    sparse.coo_array,
)


def load_baseline(revision):
    source = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{revision}:toponymy/serialization.py"],
        text=True,
    )
    module = types.ModuleType("toponymy._perf_base_serialization")
    sys.modules[module.__name__] = module
    exec(compile(source, "PERF_BASE:serialization.py", "exec"), module.__dict__)
    return module.TopicModel


def compare_case(baseline, optimized, matrix, table, n_documents):
    before = baseline(table, {}, [matrix], np.ones((n_documents, 2)))
    after = optimized(table, {}, [matrix], np.ones((n_documents, 2)))
    assert list(before.topics) == list(after.topics)
    for key in before.topics:
        left, right = before.topics[key], after.topics[key]
        np.testing.assert_array_equal(left.members, right.members)
        assert left.members.dtype == right.members.dtype
        assert left.members.flags.owndata == right.members.flags.owndata
        assert left.features == right.features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=PERF_BASE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from toponymy.serialization import TopicModel

    baseline = load_baseline(args.base)
    checks = 0
    for seed in range(40):
        rng = np.random.default_rng(seed)
        n_documents = int(rng.integers(0, 65))
        n_columns = int(rng.integers(1, 12))
        labels = rng.integers(-1, n_columns, size=n_documents)
        rows = np.flatnonzero(labels >= 0)
        columns = labels[rows]
        order = rng.permutation(len(rows))
        data = np.full(len(rows), 255)
        for storage in STORAGE_TYPES:
            matrix = storage(
                sparse.coo_array(
                    (data[order], (rows[order], columns[order])),
                    shape=(n_documents, n_columns),
                )
            )
            ids = rng.permutation(np.arange(n_columns, dtype=np.int64) * 100003 + 7)
            table = pd.DataFrame(
                {"layer": np.zeros(n_columns, dtype=np.int64), "cluster": ids}
            )
            compare_case(baseline, TopicModel, matrix, table, n_documents)
            checks += 1
    report = {
        "perf_base": args.base,
        "seed_range": [0, 39],
        "cases": checks,
        "formats": [storage.__name__ for storage in STORAGE_TYPES],
        "equivalence": [
            "keys and iteration order",
            "members values and order",
            "member dtype",
            "member ownership",
            "features",
        ],
        "status": "passed",
    }
    payload = json.dumps(report, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
