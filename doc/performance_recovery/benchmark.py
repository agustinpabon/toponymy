#!/usr/bin/env python3
"""Local reconstruction, NOT the unavailable sealed Protocol v2.0.3 harness.

Use one interpreter for all revisions; --repo controls source imports. Examples::

    python benchmark.py prepare --size 2048 --archive /tmp/legacy-2048.zip
    python benchmark.py run --arm base --repo /path/to/base --size 2048 \
        --archive /tmp/legacy-2048.zip --output /tmp/base-2048.json

Warm runs use two warmups and nine measured repetitions by default. Repetitions
in one process are correlated: launch independent processes for replication.
Cold runs require exactly one operation and perform no operation warmup. Imports
and input preparation are excluded, but every requested constructor, fit, tree
build, and archive read (including its validation) is inside the timed call.
An existing Numba cache and the OS page cache are NOT cleared by this harness.

OLD has no PrecomputedClusterer. Its disclosed changed-work reference constructs
ClusterLayerText objects with centroids and a tree. It does not provide the new
ownership/validation contracts. Only base/optimized precomputed runs execute the
same API contract. Legacy reads also have deliberately stronger NEW validation.
Synthetic archives implement the common serial 0.1 layout, are generated once
before measurement, and must be reused unchanged for all arms. The repository's
actual legacy fixture is measured separately when --fixture is provided.
"""

import argparse
import base64
from functools import cache
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import zipfile

THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "NUMBA_NUM_THREADS",
)
OPERATIONS = (
    "centroids",
    "precomputed",
    "cluster_tree",
    "topic_hierarchy",
    "legacy_read",
)


def command_output(arguments):
    result = subprocess.run(arguments, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def workload(size, dimensions, seed):
    import numpy as np

    rng = np.random.default_rng(seed)
    vectors = rng.standard_normal((size, dimensions)).astype(np.float64)
    # Approximately 32 documents per fine cluster, with at least four clusters.
    # Cap below OLD's legacy UID limit, independently of any benchmark size.
    n_clusters = min(512, max(4, size // 32))
    fine = np.arange(size, dtype=np.int64) % n_clusters
    rng.shuffle(fine)
    noise = rng.random(size) < 0.05
    labels = [np.where(noise, -1, fine // factor) for factor in (1, 4, 16)]
    return vectors, labels


def expected_tree(labels):
    """Simple independent containment oracle, never used in timed operations."""
    import numpy as np

    tree = {}
    for lower, values in enumerate(labels):
        for label in np.unique(values[values >= 0]):
            members = np.flatnonzero(values == label)
            parent = (len(labels), 0)
            for upper in range(lower + 1, len(labels)):
                candidates = np.unique(labels[upper][members])
                if len(candidates) == 1 and candidates[0] >= 0:
                    parent = (upper, int(candidates[0]))
                    break
            tree.setdefault(parent, []).append((lower, int(label)))
    return tree


def normalized_tree(tree):
    return [
        [list(parent), [list(child) for child in sorted(children)]]
        for parent, children in sorted(tree.items())
    ]


def uid(key):
    combined = (int(key[0]) << 10) | (int(key[1]) + 1)
    return base64.urlsafe_b64encode(combined.to_bytes(3, "big")).rstrip(b"=").decode()


def prepare_archive(args):
    """Write deterministic common legacy bytes without using either reader."""
    import numpy as np
    import pandas as pd
    from scipy import sparse

    vectors, labels = workload(args.size, args.dimensions, args.seed)
    files = {}
    for name, value in (
        ("embedding_vectors.npy", vectors),
        ("reduced_vectors.npy", vectors[:, :2]),
    ):
        stream = io.BytesIO()
        np.save(stream, value, allow_pickle=False)
        files[name] = stream.getvalue()
    rows = []
    for layer, values in enumerate(labels):
        indices = np.flatnonzero(values >= 0)
        matrix = sparse.csr_matrix(
            (np.full(len(indices), 255, dtype=np.uint8), (indices, values[indices])),
            shape=(len(values), int(values.max()) + 1),
        )
        stream = io.BytesIO()
        sparse.save_npz(stream, matrix)
        files[f"cluster_matrices/layer_{layer}.npz"] = stream.getvalue()
        for label in np.unique(values[values >= 0]):
            rows.append(
                {
                    "uid": uid((layer, label)),
                    "layer": layer,
                    "cluster": int(label),
                    "name": f"Topic {layer}:{label}",
                    "size": int(np.count_nonzero(values == label)),
                    "keyphrases": [f"keyword-{label}", "shared"],
                }
            )
    tables = {
        "document_df.parquet": pd.DataFrame(
            {
                "item_num": np.arange(args.size),
                "text": [f"Document {index}" for index in range(args.size)],
            }
        ),
        "topic_df.parquet": pd.DataFrame(rows),
    }
    for name, table in tables.items():
        stream = io.BytesIO()
        table.to_parquet(stream, index=False)
        files[name] = stream.getvalue()
    tree = {
        uid(parent): [uid(child) for child in children]
        for parent, children in expected_tree(labels).items()
    }
    files["cluster_tree.json"] = json.dumps(tree, sort_keys=True).encode()
    files["metadata.json"] = json.dumps(
        {
            "serial_version": "0.1",
            "n_layers": len(labels),
            "has_reduced": True,
        },
        sort_keys=True,
    ).encode()
    path = Path(args.archive).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to replace common archive: {path}")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    print(json.dumps({"archive": str(path), "sha256": file_digest(path)}))


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(array):
    import numpy as np

    array = np.asarray(array)
    digest = hashlib.sha256(str((array.dtype.str, array.shape)).encode())
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def archive_reference(path):
    """Inspect common persisted data independently, outside reader timing."""
    import numpy as np
    import pandas as pd
    from scipy import sparse

    with zipfile.ZipFile(path) as archive:
        vectors = np.load(io.BytesIO(archive.read("embedding_vectors.npy")))
        table = pd.read_parquet(io.BytesIO(archive.read("topic_df.parquet")))
        metadata = json.loads(archive.read("metadata.json"))
        matrices = [
            sparse.load_npz(
                io.BytesIO(archive.read(f"cluster_matrices/layer_{index}.npz"))
            )
            for index in range(metadata["n_layers"])
        ]
        documents = pd.read_parquet(io.BytesIO(archive.read("document_df.parquet")))
        reduced = (
            np.load(io.BytesIO(archive.read("reduced_vectors.npy")))
            if metadata.get("has_reduced", False)
            else None
        )
        raw_tree = json.loads(archive.read("cluster_tree.json"))

        def decode(identifier):
            number = int.from_bytes(
                base64.urlsafe_b64decode(identifier + "=" * (-len(identifier) % 4)),
                "big",
            )
            return number >> 10, (number & 0x3FF) - 1

        tree = {
            decode(parent): [decode(child) for child in children]
            for parent, children in raw_tree.items()
        }
        return vectors, table, matrices, documents, reduced, tree


def check_archive(model, reference):
    import numpy as np
    import pandas as pd

    vectors, table, matrices, documents, reduced, tree = reference
    np.testing.assert_array_equal(model.embedding_vectors, vectors)
    if reduced is None:
        assert model.reduced_vectors is None
    else:
        np.testing.assert_array_equal(model.reduced_vectors, reduced)
    pd.testing.assert_frame_equal(model.document_df, documents)
    assert normalized_tree(model.cluster_tree) == normalized_tree(tree)
    assert len(model.cluster_layers) == len(matrices)
    for actual, expected in zip(model.cluster_layers, matrices):
        assert actual.shape == expected.shape
        assert (actual != expected).nnz == 0
    actual_table = model.topic_df.sort_values(["layer", "cluster"])
    expected_table = table.sort_values(["layer", "cluster"])
    for column in ("layer", "cluster", "name", "size"):
        if column in expected_table:
            assert actual_table[column].tolist() == expected_table[column].tolist()
    for actual, expected in zip(actual_table.keyphrases, expected_table.keyphrases):
        assert list(actual) == list(expected)
    membership = []
    for row in expected_table.to_dict("records"):
        members = matrices[int(row["layer"])].getcol(int(row["cluster"])).nonzero()[0]
        if hasattr(model, "topics"):
            np.testing.assert_array_equal(
                model.topics[(int(row["layer"]), int(row["cluster"]))].members,
                members,
            )
            actual_size = actual_table[
                (actual_table.layer == row["layer"])
                & (actual_table.cluster == row["cluster"])
            ]["size"].iloc[0]
            assert actual_size == len(members)
        membership.append([int(row["layer"]), int(row["cluster"]), members.tolist()])
    return {
        "vectors": array_digest(vectors),
        "membership": json_digest(membership),
        "tree": json_digest(normalized_tree(model.cluster_tree)),
        "topic_names": json_digest(actual_table.name.tolist()),
    }


def archive_checker(path, expected_vectors=None):
    # Only the independent verification oracle is memoized. It is first read
    # AFTER an operation completes and is never passed into the timed reader.
    @cache
    def reference():
        result = archive_reference(path)
        if expected_vectors is not None:
            import numpy as np

            np.testing.assert_array_equal(result[0], expected_vectors)
        return result

    def facts():
        vectors = reference()[0]
        return {
            "path": str(path),
            "sha256": file_digest(path),
            "bytes": path.stat().st_size,
            "observations": int(vectors.shape[0]),
            "dimensions": int(vectors.shape[1]),
        }

    return lambda model: check_archive(model, reference()), facts


def make_operations(args, clustering, serialization, vectors, labels, old):
    from types import SimpleNamespace
    from toponymy.plotting import construct_topic_hierarchy

    expected = normalized_tree(expected_tree(labels))

    # Plotting accepts already fitted clustering state. Its workload begins at
    # that public API, separately from the fully timed precomputed fit above.
    plot_tree = expected_tree(labels)
    needs_plot_input = "topic_hierarchy" in (args.operations or OPERATIONS)
    plot_layers = (
        [SimpleNamespace(cluster_labels=values) for values in labels]
        if old
        else clustering.build_cluster_layers(labels) if needs_plot_input else []
    )
    plot_input = SimpleNamespace(cluster_tree_=plot_tree, cluster_layers_=plot_layers)
    names = [
        [f"Topic {layer}:{label}" for label in range(int(values.max()) + 1)]
        for layer, values in enumerate(labels)
    ]

    def expected_hierarchy(node):
        import numpy as np

        layer, label = node
        children = plot_tree.get(node, [])
        if layer == len(labels):
            name, size = "Root", len(vectors)
        else:
            name = names[layer][label]
            # Historical plotting reports every leaf size as one, even when
            # it has more members. Preserve and disclose that changed contract.
            size = (
                1
                if old and not children
                else int(np.count_nonzero(labels[layer] == label))
            )
        result = {"name": name, "size": size}
        if children:
            result["children"] = [expected_hierarchy(child) for child in children]
        return result

    hierarchy_reference = expected_hierarchy((len(labels), 0))

    def check_hierarchy(result):
        assert result == hierarchy_reference
        return {"hierarchy": json_digest(result)}

    def check_tree(tree):
        assert normalized_tree(tree) == expected
        return {"tree": json_digest(expected)}

    def check_centroids(result):
        import numpy as np

        means = np.array(
            [
                vectors[labels[0] == label].mean(axis=0)
                for label in range(int(labels[0].max()) + 1)
            ]
        )
        np.testing.assert_allclose(result, means, rtol=1e-12, atol=1e-14)
        return {
            "exact": array_digest(result),
            "rounded_12_decimals": array_digest(np.round(result, 12)),
            "max_absolute_reference_error": float(np.max(np.abs(result - means))),
        }

    if old:
        from toponymy.cluster_layer import ClusterLayerText

        def precomputed():
            layers = [
                ClusterLayerText(
                    values, clustering.centroids_from_labels(values, vectors), index
                )
                for index, values in enumerate(labels)
            ]
            return layers, clustering.build_cluster_tree(labels)

    else:

        def precomputed():
            fitted = clustering.PrecomputedClusterer(labels).fit(vectors)
            return fitted.cluster_layers_, fitted.cluster_tree_

    def check_precomputed(result):
        import numpy as np

        layers, tree = result
        assert len(layers) == len(labels)
        for layer, values in zip(layers, labels):
            np.testing.assert_array_equal(layer.cluster_labels, values)
            if old:
                means = np.array(
                    [
                        vectors[values == label].mean(axis=0)
                        for label in range(int(values.max()) + 1)
                    ]
                )
                np.testing.assert_allclose(
                    layer.centroid_vectors, means, rtol=1e-12, atol=1e-14
                )
            else:
                for cluster in layer:
                    np.testing.assert_array_equal(
                        cluster.members, np.flatnonzero(values == cluster.label)
                    )
                assert not layer.labels.flags.writeable
        return {**check_tree(tree), "labels": [array_digest(x) for x in labels]}

    operations = {
        "centroids": (
            lambda: clustering.centroids_from_labels(labels[0], vectors),
            check_centroids,
        ),
        "precomputed": (precomputed, check_precomputed),
        "cluster_tree": (lambda: clustering.build_cluster_tree(labels), check_tree),
        "topic_hierarchy": (
            lambda: construct_topic_hierarchy(plot_input, names),
            check_hierarchy,
        ),
    }
    archives = {}
    for name, path in (("legacy_read", args.archive), ("legacy_fixture", args.fixture)):
        if path:
            path = Path(path).resolve()
            check, facts = archive_checker(
                path,
                vectors if name == "legacy_read" else None,
            )
            operations[name] = (
                lambda path=path: serialization.TopicModel.from_file(path),
                check,
            )
            archives[name] = facts
    return operations, archives


def measure(operation, verify, args, name):
    for _ in range(args.warmups if args.mode == "warm" else 0):
        verify(operation())
    samples = []
    checks = []
    for _ in range(args.repetitions if args.mode == "warm" else 1):
        start = time.perf_counter_ns()
        result = operation()
        elapsed = time.perf_counter_ns() - start
        samples.append(elapsed / 1e9)
        checks.append(verify(result))
        del result
    assert all(
        check == checks[0] for check in checks
    ), "Output varies across repetitions"
    measurement = {
        "seconds": samples,
        "median_seconds": statistics.median(samples),
        "minimum_seconds": min(samples),
        "output": checks[0],
    }
    if args.profile_dir:
        import cProfile
        import pstats

        directory = Path(args.profile_dir)
        directory.mkdir(parents=True, exist_ok=True)
        profiler = cProfile.Profile()
        verify(profiler.runcall(operation))
        profiler.dump_stats(str(directory / f"{args.arm}-{args.size}-{name}.prof"))
        with (directory / f"{args.arm}-{args.size}-{name}.txt").open("w") as stream:
            pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(
                60
            )
    if args.memory:
        import tracemalloc

        tracemalloc.start()
        result = operation()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        verify(result)
        measurement["separate_tracemalloc_bytes"] = {"retained": current, "peak": peak}
    return measurement


def run(args):
    for name in THREAD_VARIABLES:
        os.environ[name] = str(args.threads)
    repo = Path(args.repo).resolve()
    cache_directory = os.environ.get("NUMBA_CACHE_DIR")
    initial_cache_files = (
        sorted(
            str(path.relative_to(cache_directory))
            for path in Path(cache_directory).rglob("*")
            if path.is_file()
        )
        if cache_directory
        else None
    )
    sys.path.insert(0, str(repo))
    start = time.perf_counter()
    import toponymy
    from toponymy import clustering, serialization

    import_seconds = time.perf_counter() - start
    assert Path(toponymy.__file__).resolve().is_relative_to(repo)
    old = not hasattr(clustering, "PrecomputedClusterer")
    vectors, labels = workload(args.size, args.dimensions, args.seed)
    operations, archives = make_operations(
        args, clustering, serialization, vectors, labels, old
    )
    selected = args.operations or list(OPERATIONS)
    if args.fixture and args.operations is None:
        selected += ["legacy_fixture"]
    if args.mode == "cold" and len(selected) != 1:
        raise ValueError("Cold measurements require exactly one --operations value")
    missing = set(selected) - operations.keys()
    if missing:
        raise ValueError(f"Missing archive argument for {sorted(missing)}")
    dependencies = {
        distribution.metadata["Name"]: distribution.version
        for distribution in importlib.metadata.distributions()
    }
    report = {
        "methodology": "local reconstruction; sealed inputs/protocol unavailable",
        "harness_sha256": file_digest(__file__),
        "arm": args.arm,
        "repo": str(repo),
        "git_sha": command_output(["git", "-C", str(repo), "rev-parse", "HEAD"]),
        "git_status": command_output(["git", "-C", str(repo), "status", "--short"]),
        "module_path": toponymy.__file__,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "cpu": (
            command_output(["sysctl", "-n", "machdep.cpu.brand_string"])
            if sys.platform == "darwin"
            else platform.processor()
        ),
        "logical_cpu_count": os.cpu_count(),
        "dependencies": dependencies,
        "thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
        "numba_cache_dir": os.environ.get("NUMBA_CACHE_DIR"),
        "cache_condition": args.cache_condition,
        "initial_numba_cache_files": initial_cache_files,
        "import_seconds": import_seconds,
        "mode": args.mode,
        "warmups": args.warmups if args.mode == "warm" else 0,
        "repetitions": args.repetitions if args.mode == "warm" else 1,
        "input": {
            "size": args.size,
            "dimensions": args.dimensions,
            "seed": args.seed,
            "vectors_sha256": array_digest(vectors),
            "labels_sha256": [array_digest(x) for x in labels],
            "clusters_per_layer": [int(x.max()) + 1 for x in labels],
        },
        "contracts": {
            "hierarchy_ambiguity": "Both build_cluster_tree and plotting.construct_topic_hierarchy "
            "are measured separately because the sealed operation mapping is unavailable",
            "topic_hierarchy": "Starts with fitted cluster state; OLD leaf size=1, "
            "NEW leaf size=membership count. Each is checked against its own contract",
            "precomputed": "OLD: layer objects+centroids+tree; NEW: constructor+fit "
            "including owned memberships, label/vector validation and tree",
            "legacy_read": "same archive bytes; NEW performs stronger validation "
            "and eager Topic materialization",
            "memory": "separate tracemalloc call; Python-tracked allocations, not RSS",
        },
        "measurements": {
            name: measure(*operations[name], args, name) for name in selected
        },
        "archives": {
            name: facts() for name, facts in archives.items() if name in selected
        },
    }
    try:
        import resource
    except ImportError:
        report["process_lifetime_peak_rss_bytes"] = None
    else:
        report["process_lifetime_peak_rss_bytes"] = resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    report["process_lifetime_peak_rss_scope"] = (
        "Whole worker including imports, input setup, timed calls, verification, "
        "optional profiling and separate tracemalloc measurement; not operation-only"
    )
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(f"Refusing to replace measurement: {output}")
        output.write_text(encoded + "\n")
        print(
            json.dumps(
                {
                    "output": str(output.resolve()),
                    "medians": {
                        name: value["median_seconds"]
                        for name, value in report["measurements"].items()
                    },
                }
            )
        )
    else:
        print(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    execute = commands.add_parser("run")
    for command in (prepare, execute):
        command.add_argument("--size", type=int, default=2048)
        command.add_argument("--dimensions", type=int, default=64)
        command.add_argument("--seed", type=int, default=211)
        command.add_argument("--archive", required=command is prepare)
    execute.add_argument("--repo", required=True)
    execute.add_argument("--arm", required=True)
    execute.add_argument("--fixture")
    execute.add_argument(
        "--operations", nargs="+", choices=(*OPERATIONS, "legacy_fixture")
    )
    execute.add_argument("--mode", choices=("warm", "cold"), default="warm")
    execute.add_argument("--warmups", type=int, default=2)
    execute.add_argument("--repetitions", type=int, default=9)
    execute.add_argument("--threads", type=int, default=1)
    execute.add_argument("--memory", action="store_true")
    execute.add_argument(
        "--cache-condition",
        default="uncontrolled existing Numba and filesystem caches",
    )
    execute.add_argument("--profile-dir")
    execute.add_argument("--output")
    args = parser.parse_args()
    if args.size < 128 or args.dimensions < 2:
        parser.error("this reconstruction requires size >= 128 and dimensions >= 2")
    if args.command == "run" and (
        args.warmups < 0 or args.repetitions < 1 or args.threads < 1
    ):
        parser.error("warmups must be nonnegative; repetitions and threads positive")
    prepare_archive(args) if args.command == "prepare" else run(args)


if __name__ == "__main__":
    main()
