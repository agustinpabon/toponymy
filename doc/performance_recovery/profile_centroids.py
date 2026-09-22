#!/usr/bin/env python3
"""Diagnostic decomposition of PERF_BASE centroids; not a primary benchmark.

The count/scale, double-division accumulation, and clipping/restoration loops
retain PERF_BASE arithmetic. Each phase is a separate Numba call. Fresh zeroed
inputs or copied partial results are prepared OUTSIDE its timed call. Therefore
phase sums do not estimate end-to-end latency: there are additional dispatches
and different cache/allocation conditions. The allocation phase includes the
label maximum, three zero allocations, and dispatch. Dispatch has an independent
empty-kernel estimate; it is not subtracted from any reported measurement.

The actual kernel performs no public validation or input copying. Neither is
silently charged to it here. Every phase is warmed twice. The assembled phase
output must equal the selected PERF_BASE kernel bit for bit before timings run.
"""

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time

from benchmark import THREAD_VARIABLES, command_output, workload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Clean PERF_BASE checkout")
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--dimensions", type=int, default=64)
    parser.add_argument("--seed", type=int, default=211)
    parser.add_argument("--repetitions", type=int, default=31)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    for name in THREAD_VARIABLES:
        os.environ[name] = "1"
    sys.path.insert(0, str(Path(args.repo).resolve()))
    import numba
    import numpy as np
    from toponymy.utility_functions import centroids_from_labels

    @numba.njit
    def allocate(labels, dimensions):
        n_clusters = labels.max() + 1 if len(labels) else 0
        result = np.zeros((n_clusters, dimensions))
        counts = np.zeros(n_clusters)
        scales = np.zeros((n_clusters, dimensions))
        return result, counts, scales

    @numba.njit
    def count_scale(labels, vectors, counts, scales):
        for i in range(labels.shape[0]):
            cluster_num = labels[i]
            if cluster_num >= 0:
                counts[cluster_num] += 1
                for j in range(vectors.shape[1]):
                    scales[cluster_num, j] = max(
                        scales[cluster_num, j], abs(np.float64(vectors[i, j]))
                    )

    @numba.njit
    def accumulate(labels, vectors, counts, scales, result):
        for i in range(labels.shape[0]):
            cluster_num = labels[i]
            if cluster_num >= 0:
                for j in range(vectors.shape[1]):
                    if scales[cluster_num, j] > 0:
                        result[cluster_num, j] += (
                            vectors[i, j] / scales[cluster_num, j] / counts[cluster_num]
                        )

    @numba.njit
    def restore(result, scales):
        for i in range(result.shape[0]):
            result[i] = np.minimum(1.0, np.maximum(-1.0, result[i])) * scales[i]

    @numba.njit
    def dispatch():
        return None

    vectors, layers = workload(args.size, args.dimensions, args.seed)
    labels = layers[0]
    result, counts, scales = allocate(labels, args.dimensions)
    count_scale(labels, vectors, counts, scales)
    accumulate(labels, vectors, counts, scales, result)
    accumulated = result.copy()
    restore(result, scales)
    reference = centroids_from_labels(labels, vectors)
    np.testing.assert_array_equal(result, reference)
    assert result.tobytes() == reference.tobytes()

    # Setup returns each phase's arguments before the clock starts. Independent
    # zeros/copies prevent earlier repetitions from accumulating into state.
    phases = {
        "end_to_end_perf_base": (
            centroids_from_labels,
            lambda: (labels, vectors),
        ),
        "label_max_and_zero_allocations": (
            allocate,
            lambda: (labels, args.dimensions),
        ),
        "count_and_scale": (
            count_scale,
            lambda: (labels, vectors, np.zeros_like(counts), np.zeros_like(scales)),
        ),
        "double_division_accumulation": (
            accumulate,
            lambda: (labels, vectors, counts, scales, np.zeros_like(result)),
        ),
        "clip_and_restore": (restore, lambda: (accumulated.copy(), scales)),
        "empty_numba_dispatch": (dispatch, lambda: ()),
    }
    measurements = {}
    for name, (operation, setup) in phases.items():
        for _ in range(2):
            operation(*setup())
        samples = []
        for _ in range(args.repetitions):
            arguments = setup()
            start = time.perf_counter_ns()
            value = operation(*arguments)
            elapsed = time.perf_counter_ns() - start
            samples.append(elapsed / 1e9)
            del value
        measurements[name] = {
            "seconds": samples,
            "median_seconds": statistics.median(samples),
        }
    report = {
        "methodology": __doc__,
        "git_sha": command_output(
            [
                "git",
                "-C",
                args.repo,
                "rev-parse",
                "HEAD",
            ]
        ),
        "python": sys.version,
        "numba": numba.__version__,
        "numpy": np.__version__,
        "module_path": sys.modules[centroids_from_labels.__module__].__file__,
        "input": {"size": args.size, "dimensions": args.dimensions, "seed": args.seed},
        "warmups": 2,
        "repetitions": args.repetitions,
        "thread_environment": {name: os.environ[name] for name in THREAD_VARIABLES},
        "copying": "No input copying is performed by the actual kernel",
        "validation": "No public-boundary validation is performed by the actual kernel",
        "phase_equivalence": "Bitwise equality with PERF_BASE verified before timing",
        "measurements": measurements,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {name: value["median_seconds"] for name, value in measurements.items()}
        )
    )


if __name__ == "__main__":
    main()
