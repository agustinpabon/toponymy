"""Ownership and containment regressions for canonical clustering construction."""

from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from sklearn.base import clone

import toponymy.clustering as clustering
from toponymy.clustering import (
    PrecomputedClusterer,
    build_cluster_layers,
    validate_cluster_tree,
)
from toponymy.plotting import construct_topic_hierarchy


@st.composite
def partitions(draw):
    size = draw(st.integers(0, 30))
    depth = draw(st.integers(0, 5))
    values = st.sampled_from([-1, 0, 19, 2**40, np.iinfo(np.int64).max])
    return [
        np.asarray(draw(st.lists(values, min_size=size, max_size=size)), dtype=np.int64)
        for _ in range(depth)
    ]


def containment_oracle(labels):
    partitions = [
        {
            int(label): set(np.flatnonzero(layer == label).tolist())
            for label in set(layer.tolist())
            if label >= 0
        }
        for layer in labels
    ]
    expected = {}
    for lower, partition in enumerate(partitions):
        for label, members in partition.items():
            parent = (len(labels), 0)
            for upper in range(lower + 1, len(partitions)):
                candidates = [
                    key for key, group in partitions[upper].items() if members <= group
                ]
                if candidates:
                    parent = (upper, candidates[0])
                    break
            expected[(lower, label)] = parent
    return expected


@settings(max_examples=100, derandomize=True, deadline=1000, database=None)
@given(partitions())
def test_fit_matches_membership_and_containment_oracles(labels):
    fitted = PrecomputedClusterer().fit(labels)
    assert len(fitted.cluster_layers_) == len(labels)
    for original, layer in zip(labels, fitted.cluster_layers_):
        np.testing.assert_array_equal(layer.labels, original)
        assert [cluster.label for cluster in layer] == sorted(
            label for label in set(original.tolist()) if label >= 0
        )
        for cluster in layer:
            np.testing.assert_array_equal(
                cluster.members, np.flatnonzero(original == cluster.label)
            )
    assert {
        child: parent
        for parent, children in fitted.cluster_tree_.items()
        for child in children
    } == containment_oracle(labels)
    validate_cluster_tree(fitted.cluster_tree_, fitted.cluster_layers_)


def test_fit_groups_each_partition_once(monkeypatch):
    """One canonical grouping supplies both layer membership and the tree."""
    calls = []
    original = clustering._group_labels

    def count_grouping(labels):
        calls.append(labels.copy())
        return original(labels)

    monkeypatch.setattr(clustering, "_group_labels", count_grouping)
    labels = [[19, 19, -1, 8], [2, 3, -1, 3], [0, 0, -1, 0]]
    fitted = PrecomputedClusterer(labels).fit(np.ones((4, 2)))
    assert len(calls) == len(labels)
    validate_cluster_tree(fitted.cluster_tree_, fitted.cluster_layers_)


@pytest.mark.parametrize(
    "factory",
    [build_cluster_layers, lambda x: PrecomputedClusterer().fit(x).cluster_layers_],
)
def test_constructed_arrays_are_owned_readonly_and_independent(factory):
    original = np.array([19, 8, -1, 19, 8, -1])
    sources = [original[::2], original[1::2]]
    snapshots = [layer.copy() for layer in sources]
    first, second = factory(sources), factory(sources)
    original[:] = 0
    arrays = []
    for result in (first, second):
        for source, layer in zip(snapshots, result):
            np.testing.assert_array_equal(layer.labels, source)
            arrays.extend([layer.labels, *(cluster.members for cluster in layer)])
    for index, array in enumerate(arrays):
        assert array.flags.owndata
        assert not array.flags.writeable
        assert not np.shares_memory(array, original)
        assert all(not np.shares_memory(array, other) for other in arrays[index + 1 :])


def test_constructor_fit_clone_and_refit_do_not_share_owned_arrays():
    labels = [np.array([19, -1, 8, 19])]
    configured = PrecomputedClusterer(labels)
    labels[0][:] = -1
    configured.fit(np.ones((4, 2)))
    first = configured.cluster_layers_[0]
    copied = clone(configured).fit(np.ones((4, 2)))
    configured.fit(np.ones((4, 2)))
    second = configured.cluster_layers_[0]
    arrays = [
        configured.labels[0],
        first.labels,
        second.labels,
        copied.labels[0],
        copied.cluster_layers_[0].labels,
    ]
    for index, array in enumerate(arrays):
        np.testing.assert_array_equal(array, [19, -1, 8, 19])
        assert all(not np.shares_memory(array, other) for other in arrays[index + 1 :])
    replacement = [np.array([8, 8, -1, -1])]
    configured.set_params(labels=replacement)
    configured.fit(np.ones((4, 2)))
    replacement[0][:] = 0
    np.testing.assert_array_equal(configured.cluster_layers_[0].labels, [8, 8, -1, -1])
    np.testing.assert_array_equal(first.labels, [19, -1, 8, 19])
    assert configured.cluster_tree_ == {(1, 0): [(0, 8)]}


@pytest.mark.parametrize(
    "invalid",
    [[[0.5]], [[-2]], [[2**64]], [[0], [0, 0]], [np.zeros((1, 1), dtype=int)]],
)
def test_reassigned_estimator_labels_are_revalidated(invalid):
    configured = PrecomputedClusterer([[0]]).fit(np.ones((1, 2)))
    configured.set_params(labels=invalid)
    with pytest.raises(ValueError):
        configured.fit(np.ones((1, 2)))
    np.testing.assert_array_equal(configured.cluster_layers_[0].labels, [0])


@pytest.mark.parametrize(
    "tree",
    [
        {},
        {(2, 0): [(0, 19), (0, 19), (0, 8), (1, 2), (1, 3)]},
        {(1, 2): [(0, 19)], (2, 0): [(0, 8), (1, 2), (1, 3)]},
        {(0, 19): [(1, 2)]},
        {(2, 0): [(0, 999)]},
        {(2, 0): [(False, 19)]},
    ],
)
def test_fit_still_rejects_supplied_malformed_trees(tree):
    configured = PrecomputedClusterer([[19, 19, -1, 8], [2, 3, -1, 3]])
    configured.set_params(cluster_tree=tree)
    with pytest.raises(ValueError):
        configured.fit(np.ones((4, 2)))


@pytest.mark.parametrize(
    "labels", [[], [[]], [[-1, -1]], [[19, -1, 8, 19], [2, -1, 2, 2]]]
)
def test_widget_hierarchy_matches_generic_layers_and_counts_noise(labels):
    fitted = PrecomputedClusterer().fit(labels)
    names = [
        {cluster.label: f"L{index}: {cluster.label}" for cluster in layer}
        for index, layer in enumerate(fitted.cluster_layers_)
    ]
    generic = SimpleNamespace(
        cluster_tree_=fitted.cluster_tree_,
        cluster_layers_=[
            SimpleNamespace(cluster_labels=np.asarray(layer)) for layer in labels
        ],
    )
    hierarchy = construct_topic_hierarchy(fitted, names)
    assert hierarchy == construct_topic_hierarchy(generic, names)
    assert hierarchy["size"] == (len(labels[0]) if labels else 0)


def test_widget_hierarchy_retains_malformed_display_tree_rejection():
    fitted = PrecomputedClusterer([[19, 8]]).fit()
    fitted.cluster_tree_ = {(0, 19): [(0, 8)]}
    with pytest.raises(ValueError, match="lower layers"):
        construct_topic_hierarchy(fitted, [{19: "A", 8: "B"}])


def test_widget_hierarchy_preserves_generic_iterable_compatibility():
    generic = SimpleNamespace(
        cluster_tree_={(1, 0): [(0, 19), (0, 8)]},
        cluster_layers_=iter([SimpleNamespace(cluster_labels=iter([19, -1, 8, 19]))]),
    )
    assert construct_topic_hierarchy(generic, [{19: "A", 8: "B"}]) == {
        "name": "Root",
        "size": 4,
        "children": [{"name": "A", "size": 2}, {"name": "B", "size": 1}],
    }
