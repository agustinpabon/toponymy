#!/usr/bin/env python3
"""Sequential depth and optional clustering-scale correction diagnostic.

Example (output must not exist)::

    python doc/performance_recovery/check_tree_depth.py \
        --repo . --output /tmp/tree-correction --include-scale

Exports exact BASE/prior revisions and snapshots corrected source into temporary
directories; it never checks out, edits or installs a revision. Three independent
processes per arm/case rotate arm order. Each uses two warmups, nine timed calls,
then three separate tracemalloc calls. No test/profile should run concurrently.
All samples and process exits are retained, including failures. Depth inputs are
identical valid partitions (n=8192, 64 IDs); scale inputs and timed operations use
the existing benchmark.py unchanged. This is warm local evidence, not the sealed
Linux experiment. tracemalloc measures Python-tracked allocations, not total RSS.
"""

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time

import benchmark

BASE = "04c300c6a0fe1117531a64e6a7966b436eadfce7"
BEFORE = "0e0d267eddc469a0ed659108f4241a5be3e97581"
ARMS = ("base", "before", "after")
DEPTHS = (1, 3, 8, 16, 32, 64)
SIZES = (128, 512, 2048, 8192, 32768)


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


def worker(args):
    sys.path.insert(0, str(Path(args.repo).resolve()))
    import numpy as np
    import toponymy
    from toponymy import clustering

    assert Path(toponymy.__file__).resolve().is_relative_to(Path(args.repo).resolve())
    if args.kind == "depth":
        labels = [np.arange(8192, dtype=np.int64) % 64 for _ in range(args.case)]
        expected = {}
        for lower in range(args.case):
            for label in range(64):
                parent = (lower + 1, label) if lower + 1 < args.case else (args.case, 0)
                expected.setdefault(parent, []).append((lower, label))

        def verify(tree):
            assert list(tree.items()) == list(expected.items())
            return {"ordered_tree": [[list(k), v] for k, v in tree.items()]}

        operations = {
            "cluster_tree": (lambda: clustering.build_cluster_tree(labels), verify)
        }
        inputs = {"n": 8192, "depth": args.case, "clusters": 64}
    else:
        vectors, labels = benchmark.workload(args.case, 64, 211)
        options = argparse.Namespace(
            operations=["precomputed", "cluster_tree"], archive=None, fixture=None
        )
        operations, _ = benchmark.make_operations(
            options, clustering, None, vectors, labels, False
        )
        operations = {name: operations[name] for name in options.operations}
        inputs = {
            "n": args.case,
            "depth": 3,
            "seed": 211,
            "vectors_sha256": benchmark.array_digest(vectors),
        }
    inputs["labels_sha256"] = [benchmark.array_digest(x) for x in labels]
    measurements = {}
    options = argparse.Namespace(
        mode="warm", warmups=2, repetitions=9, memory=False, profile_dir=None
    )
    for name, (operation, verify) in operations.items():
        measurements[name] = benchmark.measure(operation, verify, options, name)
        import gc
        import tracemalloc

        memory = []
        for _ in range(3):
            gc.collect()
            tracemalloc.start()
            result = operation()
            retained, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            verify(result)
            del result
            memory.append({"retained": retained, "peak": peak})
        measurements[name]["memory_bytes"] = memory
    dependencies = {
        d.metadata["Name"]: importlib.metadata.version(d.metadata["Name"])
        for d in importlib.metadata.distributions()
    }
    save(
        Path(args.output),
        {
            "inputs": inputs,
            "measurements": measurements,
            "environment": {
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
                "cpu": (
                    benchmark.command_output(
                        ["sysctl", "-n", "machdep.cpu.brand_string"]
                    )
                    if sys.platform == "darwin"
                    else platform.processor()
                ),
                "dependencies": dependencies,
                "threads": {
                    name: os.environ.get(name) for name in benchmark.THREAD_VARIABLES
                },
            },
        },
    )


def snapshots(repo, root):
    identities = {}
    for arm in ARMS:
        destination = root / arm
        destination.mkdir()
        revision = BASE if arm == "base" else BEFORE
        if arm == "after":
            shutil.copytree(
                repo / "toponymy",
                destination / "toponymy",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.nbc", "*.nbi"),
            )
            revision = benchmark.command_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"]
            )
        else:
            archive = subprocess.check_output(
                ["git", "-C", str(repo), "archive", revision, "toponymy"]
            )
            with tarfile.open(fileobj=io.BytesIO(archive)) as archive_file:
                archive_file.extractall(destination, filter="data")
        files = {
            str(p.relative_to(destination)): benchmark.file_digest(p)
            for p in sorted((destination / "toponymy").rglob("*.py"))
        }
        identities[arm] = {
            "revision": revision,
            "python_files": files,
            "source_sha256": hashlib.sha256(
                json.dumps(files, sort_keys=True).encode()
            ).hexdigest(),
        }
    identities["after"]["working_diff"] = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "HEAD", "--", "toponymy"], text=True
    )
    return identities


def summarize(records):
    rows = []
    cases = sorted({(r["kind"], r["case"]) for r in records})
    for kind, case in cases:
        selected = [r for r in records if (r["kind"], r["case"]) == (kind, case)]
        assert len(selected) == 9
        for record in selected:
            assert record["inputs"] == selected[0]["inputs"]
        for operation in selected[0]["measurements"]:
            reference = selected[0]["measurements"][operation]["output"]
            for record in selected:
                assert record["measurements"][operation]["output"] == reference
            row = {"kind": kind, "case": case, "operation": operation}
            for arm in ARMS:
                observations = [
                    r["measurements"][operation] for r in selected if r["arm"] == arm
                ]
                times = [statistics.median(x["seconds"]) for x in observations]
                peaks = [
                    statistics.median(m["peak"] for m in x["memory_bytes"])
                    for x in observations
                ]
                row[arm] = {
                    "seconds": statistics.median(times),
                    "peak_bytes": statistics.median(peaks),
                    "process_seconds": times,
                    "process_peak_bytes": peaks,
                }
            row["after_vs_base"] = row["after"]["seconds"] / row["base"]["seconds"]
            row["after_vs_before"] = row["after"]["seconds"] / row["before"]["seconds"]
            rows.append(row)
    return rows


def campaign(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    harness = Path(__file__).resolve()
    records = []
    manifest = {
        "harness_sha256": benchmark.file_digest(harness),
        "benchmark_sha256": benchmark.file_digest(harness.with_name("benchmark.py")),
        "warmups": 2,
        "timed_repetitions": 9,
        "memory_repetitions": 3,
        "processes_per_arm_case": 3,
        "processes": [],
    }
    with tempfile.TemporaryDirectory(prefix="toponymy-correction-") as temporary:
        root = Path(temporary)
        manifest["sources"] = snapshots(repo, root)
        cases = [("depth", x) for x in DEPTHS]
        if args.include_scale:
            cases += [("scale", x) for x in SIZES]
        for kind, case in cases:
            for replication in range(3):
                for arm in ARMS[replication:] + ARMS[:replication]:
                    name = f"{kind}-{case}-r{replication + 1}-{arm}"
                    raw = output / f"{name}.json"
                    command = [
                        sys.executable,
                        str(harness),
                        "--worker",
                        "--repo",
                        str(root / arm),
                        "--kind",
                        kind,
                        "--case",
                        str(case),
                        "--output",
                        str(raw),
                    ]
                    environment = dict(
                        os.environ,
                        PYTHONDONTWRITEBYTECODE="1",
                        LITELLM_LOCAL_MODEL_COST_MAP="True",
                        NUMBA_CACHE_DIR=str(root / "caches" / name),
                    )
                    environment.update({key: "1" for key in benchmark.THREAD_VARIABLES})
                    start = time.time()
                    result = subprocess.run(
                        command, env=environment, capture_output=True, text=True
                    )
                    process = {
                        "name": name,
                        "command": command,
                        "started": start,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                    manifest["processes"].append(process)
                    # Persist every exit immediately, including an unsuccessful attempt.
                    save(output / f"{name}.process.json", process)
                    if result.returncode:
                        save(output / "manifest.json", manifest)
                        raise RuntimeError(
                            f"Worker failed; retained evidence: {output / name}"
                        )
                    record = json.loads(raw.read_text())
                    record.update(
                        kind=kind, case=case, arm=arm, replication=replication + 1
                    )
                    if "environment" not in manifest:
                        manifest["environment"] = record["environment"]
                    assert record["environment"] == manifest["environment"]
                    records.append(record)
                    print(f"Completed {name}", flush=True)
    save(output / "summary.json", summarize(records))
    manifest["observations"] = len(records)
    manifest["files"] = {
        p.name: benchmark.file_digest(p)
        for p in sorted(output.iterdir())
        if p.is_file()
    }
    save(output / "manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--include-scale", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--kind", choices=("depth", "scale"))
    parser.add_argument("--case", type=int)
    args = parser.parse_args()
    worker(args) if args.worker else campaign(args)


if __name__ == "__main__":
    main()
