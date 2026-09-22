"""Characterize membership materialization before optimizing archive loading."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from toponymy.serialization import TopicModel

STORAGE_TYPES = [
    sparse.csr_matrix,
    sparse.csc_matrix,
    sparse.coo_matrix,
    sparse.csr_array,
    sparse.csc_array,
    sparse.coo_array,
]


def membership(storage, *, rows=None, columns=None, values=None):
    """Build noncanonical storage without silently summing duplicate entries."""
    rows = np.array([4, 1, 0, 3, 1] if rows is None else rows)
    columns = np.array([2, 2, 0, 0, 0] if columns is None else columns)
    values = np.array([255, 255, 255, 255, 0] if values is None else values)
    format_name = storage((0, 0)).format
    if format_name == "coo":
        return storage((values, (rows, columns)), shape=(5, 3))
    major, minor = (rows, columns) if format_name == "csr" else (columns, rows)
    # Descending minor indices exercise unsorted compressed representations.
    order = np.lexsort((-minor, major))
    counts = np.bincount(major, minlength=5 if format_name == "csr" else 3)
    indptr = np.r_[0, np.cumsum(counts)]
    return storage((values[order], minor[order], indptr), shape=(5, 3))


def model_for(matrix, *, gappy=False):
    labels = [2, 0] if gappy else [2**40, 99, 7]
    table = pd.DataFrame(
        {
            "layer": [0] * len(labels),
            "cluster": labels,
            "name": [str(x) for x in labels],
        }
    )
    return TopicModel(table, {}, [matrix], np.ones((5, 2)))


def borrowed_arrays(matrix):
    if matrix.format == "coo":
        return matrix.data, matrix.row, matrix.col
    return matrix.data, matrix.indices, matrix.indptr


@pytest.mark.parametrize("storage", STORAGE_TYPES)
@pytest.mark.parametrize("gappy", [False, True])
def test_materialization_orders_members_without_mutating_borrowed_storage(
    storage, gappy
):
    matrix = membership(storage)
    arrays = borrowed_arrays(matrix)
    snapshots = [array.copy() for array in arrays]
    for array in arrays:
        array.flags.writeable = False
    model = model_for(matrix, gappy=gappy)
    expected = {0: [0, 3], 2: [1, 4]} if gappy else {7: [0, 3], 99: [], 2**40: [1, 4]}

    assert list(model.topics) == [(0, label) for label in expected]
    for label, members in expected.items():
        topic = model.topics[(0, label)]
        assert topic.members.tolist() == members
        assert not topic.members.flags.writeable
        assert not any(np.shares_memory(topic.members, array) for array in arrays)
    assert model.cluster_layers[0] is matrix
    for before, after, snapshot in zip(arrays, borrowed_arrays(matrix), snapshots):
        assert before is after
        assert not after.flags.writeable
        np.testing.assert_array_equal(after, snapshot)


@pytest.mark.parametrize("storage", STORAGE_TYPES)
@pytest.mark.parametrize("values", [[0, 0], [0, 255], [255, 255]])
def test_duplicate_coordinates_are_rejected_including_explicit_zeros(storage, values):
    matrix = membership(storage, rows=[0, 0], columns=[0, 0], values=values)
    model = model_for(matrix)
    with pytest.raises(ValueError, match="duplicate coordinates"):
        model.topics
    assert model._topics is None


@pytest.mark.parametrize("storage", STORAGE_TYPES)
def test_membership_partition_rejection_is_atomic(storage):
    matrix = membership(storage, rows=[1, 1], columns=[0, 2], values=[1, 255])
    model = model_for(matrix)
    with pytest.raises(ValueError, match="multiple topics"):
        model.topics
    assert model._topics is None


@pytest.mark.parametrize("storage", STORAGE_TYPES)
def test_gappy_table_cannot_omit_a_populated_column(storage):
    model = model_for(membership(storage), gappy=True)
    model._topic_df = model._topic_df[model._topic_df["cluster"] == 0]
    with pytest.raises(ValueError, match="does not describe"):
        model.topics
    assert model._topics is None


@pytest.mark.parametrize("storage", [sparse.csr_matrix, sparse.csc_matrix])
@pytest.mark.parametrize(
    "defect",
    [
        "negative-index",
        "large-index",
        "first-pointer",
        "last-pointer",
        "short-pointer",
        "short-data",
    ],
)
def test_invalid_compressed_arrays_are_rejected_without_rebinding_borrowed_arrays(
    storage, defect
):
    matrix = membership(storage)
    if defect == "negative-index":
        matrix.indices[0] = -1
    elif defect == "large-index":
        matrix.indices[0] = matrix.shape[1 if matrix.format == "csr" else 0]
    elif defect == "first-pointer":
        matrix.indptr[0] = 1
    elif defect == "last-pointer":
        matrix.indptr[-1] = len(matrix.data) + 1
    elif defect == "short-pointer":
        matrix.indptr = matrix.indptr[:-1]
    else:
        matrix.data = matrix.data[:-1]
    arrays = borrowed_arrays(matrix)
    snapshots = [array.copy() for array in arrays]
    model = model_for(matrix)
    with pytest.raises(ValueError):
        model.topics
    assert model._topics is None
    for before, after, snapshot in zip(arrays, borrowed_arrays(matrix), snapshots):
        assert before is after
        np.testing.assert_array_equal(after, snapshot)


@pytest.mark.parametrize("storage", STORAGE_TYPES)
def test_materialized_topics_snapshot_membership_but_leave_public_matrices_borrowed(
    storage,
):
    matrix = membership(storage)
    model = model_for(matrix)
    first_topic = model.topics[(0, 7)]
    matrix.data[:] = 0
    assert first_topic.members.tolist() == [0, 3]
    assert model.cluster_layers[0] is matrix
    assert model.cluster_layers[0].count_nonzero() == 0
    first_topic.name = "Edited"
    assert model.topic_df.loc[model.topic_df["cluster"] == 7, "name"].item() == "Edited"


@pytest.mark.parametrize("storage", STORAGE_TYPES)
def test_failed_topic_row_materialization_can_be_retried_without_partial_state(storage):
    model = model_for(membership(storage))
    model._topic_df["features_json"] = ["[]", "{}", "{}"]
    with pytest.raises(ValueError, match="features must be an object"):
        model.topics
    assert model._topics is None
    model._topic_df["features_json"] = "{}"
    assert model.topics[(0, 2**40)].members.tolist() == [1, 4]


@pytest.mark.parametrize("storage", STORAGE_TYPES)
@pytest.mark.parametrize("stored_zero", [False, True])
def test_absent_topic_table_distinguishes_empty_storage_from_explicit_zeros(
    storage, stored_zero
):
    matrix = (
        membership(storage, rows=[0], columns=[0], values=[0])
        if stored_zero
        else storage((5, 3))
    )
    model = TopicModel(None, {}, [matrix], np.ones((5, 2)))
    if stored_zero:
        with pytest.raises(ValueError, match="require a topic table"):
            model.topics
        assert model._topics is None
    else:
        assert model.topics == {}


@pytest.mark.parametrize("storage", STORAGE_TYPES)
@pytest.mark.parametrize("value", [-1, np.nan, np.inf, -np.inf])
def test_invalid_membership_values_are_rejected_before_materialization(storage, value):
    matrix = membership(storage, rows=[0], columns=[0], values=[value])
    model = model_for(matrix)
    with pytest.raises(ValueError, match="invalid membership values"):
        model.topics
    assert model._topics is None


@pytest.mark.parametrize("storage", STORAGE_TYPES)
def test_empty_topic_columns_materialize_readonly_empty_members(storage):
    model = model_for(storage((5, 3)))
    assert list(model.topics) == [(0, 7), (0, 99), (0, 2**40)]
    for topic in model.topics.values():
        assert topic.members.size == 0
        assert not topic.members.flags.writeable


@pytest.mark.parametrize("storage", [sparse.coo_matrix, sparse.coo_array])
@pytest.mark.parametrize(
    "axis,value", [("row", -1), ("row", 5), ("col", -1), ("col", 3)]
)
def test_mutated_coo_coordinates_cannot_escape_membership_validation(
    storage, axis, value
):
    matrix = membership(storage)
    getattr(matrix, axis)[0] = value
    model = model_for(matrix)
    with pytest.raises(ValueError):
        model.topics
    assert model._topics is None


@pytest.mark.parametrize("storage", STORAGE_TYPES)
def test_member_storage_preserves_legacy_dtype_and_independent_ownership(storage):
    matrix = membership(storage)
    if matrix.format == "coo":
        matrix.coords = tuple(values.astype(np.int64) for values in matrix.coords)
    else:
        matrix.indices = matrix.indices.astype(np.int64)
        matrix.indptr = matrix.indptr.astype(np.int64)
    model = model_for(matrix)
    expected_dtype = np.dtype(np.int32 if sparse.isspmatrix(matrix) else np.int64)
    for topic in model.topics.values():
        assert topic.members.dtype == expected_dtype
        assert topic.members.flags.owndata
        topic.members.flags.writeable = True
    model.topics[(0, 7)].members[0] = 2
    assert model.topics[(0, 2**40)].members.tolist() == [1, 4]
    assert matrix.toarray()[0, 0] == 255


@pytest.mark.parametrize(
    "storage",
    [sparse.csr_matrix, sparse.csr_array, sparse.coo_matrix, sparse.coo_array],
)
def test_gappy_columns_do_not_require_dense_column_index_storage(storage):
    column = 2**40
    if storage((0, 0)).format == "csr":
        matrix = storage(([255], [column], [0, 0, 0, 0, 0, 1]), shape=(5, column + 1))
    else:
        matrix = storage(([255], ([4], [column])), shape=(5, column + 1))
    table = pd.DataFrame({"layer": [0], "cluster": [column]})
    model = TopicModel(table, {}, [matrix], np.ones((5, 2)))
    assert model.topics[(0, column)].members.tolist() == [4]
    assert model.topics[(0, column)].members.dtype == np.dtype(
        np.int32 if sparse.isspmatrix(matrix) else np.int64
    )


def test_empty_coo_array_preserves_compressed_conversion_member_dtype():
    matrix = sparse.coo_array(
        (
            np.array([], dtype=np.uint8),
            (np.array([], dtype=np.int64), np.array([], dtype=np.int64)),
        ),
        shape=(5, 3),
    )
    model = model_for(matrix)
    assert all(
        topic.members.dtype == np.dtype(np.int32) for topic in model.topics.values()
    )
