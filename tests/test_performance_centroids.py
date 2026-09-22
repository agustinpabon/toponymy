"""Numerical characterization of the #211 centroid reduction order."""

import numpy as np
import pytest

from toponymy.utility_functions import centroids_from_labels


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("strided", [False, True])
def test_centroid_reduction_preserves_base_rounding(dtype, strided):
    # Hex values captured from PERF_BASE 04c300c, without decimal rounding.
    expected = {
        np.float32: [
            "0x1.64d641ffffffbp-5",
            "-0x1.c158193ffffffp-3",
            "-0x1.b702194aaaaabp-3",
            "0x1.f3efead555554p-3",
            "-0x1.e8db50aaaaaa9p-4",
            "-0x1.96f3b84aaaaaap-1",
            "-0x1.a63eac1555553p-3",
            "-0x1.4228b4d555555p-2",
        ],
        np.float64: [
            "0x1.64d63b7160511p-5",
            "-0x1.c1581a4c587a1p-3",
            "-0x1.b7021a4b9c525p-3",
            "0x1.f3efecfac0a27p-3",
            "-0x1.e8db5185dd5bdp-4",
            "-0x1.96f3b79d81f72p-1",
            "-0x1.a63eaaba03faap-3",
            "-0x1.4228b681aff17p-2",
        ],
    }
    rng = np.random.default_rng(211)
    labels = rng.choice([-1, 0, 2], size=32)
    vectors = rng.normal(size=(32, 4)).astype(dtype)
    if strided:
        storage = np.zeros((32, 8), dtype=dtype)
        storage[:, ::2] = vectors
        vectors = storage[:, ::2]
    vectors.flags.writeable = False
    before = vectors.tobytes()
    actual = centroids_from_labels(labels, vectors)
    np.testing.assert_array_equal(
        actual[[0, 2]],
        np.array([float.fromhex(x) for x in expected[dtype]]).reshape(2, 4),
    )
    np.testing.assert_array_equal(actual[1], np.zeros(4))
    assert vectors.tobytes() == before


@pytest.mark.parametrize("labels", [[], [-1, -1], [0, 0]])
def test_centroid_zero_and_empty_shapes(labels):
    labels = np.asarray(labels, dtype=np.int64)
    vectors = np.zeros((len(labels), 5))
    actual = centroids_from_labels(labels, vectors)
    count = int(labels.max()) + 1 if len(labels) else 0
    np.testing.assert_array_equal(actual, np.zeros((count, 5)))


def test_centroid_nonfinite_and_noise_behavior_is_unchanged():
    # This low-level kernel has no public finite-input validator; its callers do.
    vectors = np.array([[np.nan, np.inf, -np.inf, 3.0], [1.0, 1.0, 1.0, 5.0]])
    actual = centroids_from_labels(np.array([0, 0]), vectors)
    np.testing.assert_array_equal(actual, [[np.nan, np.nan, np.nan, 4.0]])
    np.testing.assert_array_equal(
        centroids_from_labels(np.array([-1, 0]), vectors), vectors[1:]
    )
