"""Compare centroid bytes against PERF_BASE over finite adversarial inputs."""

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import numba


def load_kernel(repo, name):
    path = Path(repo) / "toponymy/utility_functions.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kernel = module.centroids_from_labels
    # Diagnostic aliases must never write to the production module's Numba
    # cache: later canonical imports cannot restore an aliased environment.
    return numba.jit(cache=False, **kernel.targetoptions)(kernel.py_func)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--optimized", required=True)
    args = parser.parse_args()
    baseline = load_kernel(args.base, "centroid_reference")
    optimized = load_kernel(args.optimized, "centroid_candidate")
    cases = 0
    for dtype in (np.float32, np.float64, np.int64, np.uint64):
        for seed in range(3):
            rng = np.random.default_rng(seed)
            for n in (0, 1, 2, 7, 31, 128):
                labels = rng.choice([-1, 0, 2, 5], size=n)
                if np.issubdtype(dtype, np.floating):
                    exponent = (-42, 37) if dtype == np.float32 else (-310, 306)
                    vectors = (
                        rng.uniform(-1, 1, size=(n, 7))
                        * 10.0 ** rng.uniform(*exponent, size=(n, 7))
                    ).astype(dtype)
                    if n:
                        vectors[:, 0] = np.finfo(dtype).max
                        vectors[:, 1] = np.nextafter(dtype(0), dtype(1))
                else:
                    low = -(2**60) if dtype == np.int64 else 0
                    vectors = rng.integers(low, 2**60, size=(n, 7), dtype=dtype)
                for values in (vectors, np.asfortranarray(vectors), vectors[:, ::-1]):
                    before = values.tobytes()
                    values.flags.writeable = False
                    expected = baseline(labels, values)
                    actual = optimized(labels, values)
                    np.testing.assert_array_equal(actual, expected)
                    assert actual.dtype == expected.dtype
                    assert actual.tobytes() == expected.tobytes()
                    assert values.tobytes() == before
                    assert not values.flags.writeable
                    cases += 1
    print(
        json.dumps(
            {
                "cases": cases,
                "status": "passed",
                "comparison": "exact bytes, dtype, shape, input immutability",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
