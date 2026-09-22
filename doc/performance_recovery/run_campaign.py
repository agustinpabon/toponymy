#!/usr/bin/env python3
"""Run the reconstruction sequentially; do not overlap with tests or profiling.

Default: 45 warm workers and 30 exploratory cold workers. Each warm worker has
its own empty Numba cache directory and performs two warmups, nine timed calls,
and a separate tracemalloc call per operation. Arm order rotates by replication.
Cold workers make one target call, first with an empty directory, then in a
separate process using the directory left by that saved first call. Kernels with
cache=False still compile in both processes; operations without cached kernels
may leave the directory empty. OS file caches are never cleared. Imports, input
setup, output checks, and whole-worker RSS remain separate from operation time.

Use the same interpreter to launch every arm. Archives are generated once and
reused byte-for-byte. Results are local reconstructions, not sealed observations.
All artifact roots must be new. --plan prints commands without running or writing.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import sys
import time

from benchmark import OPERATIONS, command_output, file_digest

SIZES = (128, 512, 2048, 8192, 32768)
ARMS = ("old", "base", "optimized")
DEFAULT_REPOS = (
    "/Users/agus/Developer/toponymy-perf-old",
    "/Users/agus/Developer/toponymy",
    "/Users/agus/Developer/toponymy-perf",
)


def source_identity(repo):
    files = {
        str(path.relative_to(repo)): file_digest(path)
        for path in sorted((repo / "toponymy").rglob("*.py"))
    }
    return {
        "repo": str(repo),
        "head": command_output(["git", "-C", str(repo), "rev-parse", "HEAD"]),
        "status": command_output(["git", "-C", str(repo), "status", "--short"]),
        "python_source_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
        "python_files": files,
    }


def inventory(directory):
    return [
        {
            "path": str(path.relative_to(directory)),
            "bytes": path.stat().st_size,
            "sha256": file_digest(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def worker_specs(root, cache_root, python, harness, repos, fixture):
    for size in SIZES:
        for replication in range(3):
            for arm in ARMS[replication:] + ARMS[:replication]:
                name = f"warm-n{size}-r{replication + 1}-{arm}"
                arguments = ["--memory"]
                if size == 2048:
                    arguments += ["--fixture", str(fixture)]
                yield specification(
                    root,
                    cache_root / name,
                    python,
                    harness,
                    repos,
                    arm,
                    size,
                    name,
                    "warm",
                    replication + 1,
                    "empty Numba directory at process start; two in-process warmups; "
                    "OS filesystem cache not cleared",
                    arguments,
                )
    for operation in OPERATIONS:
        for arm in ARMS:
            cache = cache_root / f"cold-n2048-{operation}-{arm}"
            for condition in ("empty", "primed"):
                name = f"cold-n2048-{operation}-{arm}-{condition}"
                label = (
                    "empty Numba directory"
                    if condition == "empty"
                    else "directory from separate saved first-call process; may contain no cached kernel"
                )
                yield specification(
                    root,
                    cache,
                    python,
                    harness,
                    repos,
                    arm,
                    2048,
                    name,
                    "cold",
                    None,
                    label + "; OS filesystem cache not cleared",
                    ["--operations", operation],
                    condition,
                )


def specification(
    root,
    cache,
    python,
    harness,
    repos,
    arm,
    size,
    name,
    mode,
    replication,
    cache_condition,
    extra,
    cold_condition=None,
):
    output = root / "raw" / f"{name}.json"
    command = [
        str(python),
        str(harness),
        "run",
        "--arm",
        arm,
        "--repo",
        str(repos[arm]),
        "--size",
        str(size),
        "--archive",
        str(root / "archives" / f"n{size}.zip"),
        "--mode",
        mode,
        "--warmups",
        "2",
        "--repetitions",
        "9",
        "--cache-condition",
        cache_condition,
        "--output",
        str(output),
        *extra,
    ]
    return {
        "name": name,
        "arm": arm,
        "size": size,
        "mode": mode,
        "replication": replication,
        "cold_condition": cold_condition,
        "cache_directory": str(cache),
        "output": str(output),
        "command": command,
    }


def save_manifest(root, manifest):
    temporary = root / "manifest.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    temporary.replace(root / "manifest.json")


def invoke(root, manifest, name, command, environment, cache=None):
    before = inventory(cache) if cache else None
    start = time.time()
    with (root / "logs" / f"{name}.stdout").open("x") as stdout:
        with (root / "logs" / f"{name}.stderr").open("x") as stderr:
            result = subprocess.run(
                command, env=environment, stdout=stdout, stderr=stderr, check=False
            )
    record = {
        "order": len(manifest["processes"]) + 1,
        "name": name,
        "command": command,
        "started_unix_seconds": start,
        "worker_seconds": time.time() - start,
        "returncode": result.returncode,
        "initial_cache_inventory": before,
        "final_cache_inventory": inventory(cache) if cache else None,
        "numba_cache_dir": str(cache) if cache else None,
    }
    manifest["processes"].append(record)
    if result.returncode:
        manifest["errors"].append(
            {
                "process": name,
                "returncode": result.returncode,
                "stderr": f"logs/{name}.stderr",
            }
        )
    save_manifest(root, manifest)
    print(json.dumps({"completed": name, "returncode": result.returncode}), flush=True)
    if result.returncode:
        raise RuntimeError(f"Worker {name} failed; see its stderr and manifest")


def summarize(root, specs):
    reports = [(spec, json.loads(Path(spec["output"]).read_text())) for spec in specs]
    environment = reports[0][1]
    for _, report in reports:
        for field in (
            "dependencies",
            "python",
            "python_executable",
            "thread_environment",
            "harness_sha256",
        ):
            if report[field] != environment[field]:
                raise AssertionError(f"Worker environment or harness changed: {field}")
    # Exact comparison includes centroids' raw-byte digest, not just tolerances.
    equivalent = {}
    for spec, report in reports:
        if spec["arm"] == "old":
            continue
        for operation, measurement in report["measurements"].items():
            key = (spec["size"], operation)
            if key in equivalent and equivalent[key] != measurement["output"]:
                raise AssertionError(
                    f"BASE/OPT output mismatch for {key} in {spec['name']}"
                )
            equivalent[key] = measurement["output"]
    # Common input identity is checked across all arms and process modes.
    inputs, archives, legacy_outputs = {}, {}, {}
    for spec, report in reports:
        size = spec["size"]
        if size in inputs and inputs[size] != report["input"]:
            raise AssertionError(f"Input mismatch at n={size}")
        inputs[size] = report["input"]
        for name, archive in report["archives"].items():
            key = (size, name)
            if key in archives and archives[key] != archive["sha256"]:
                raise AssertionError(f"Archive bytes differ for {key}")
            archives[key] = archive["sha256"]
        for operation in ("legacy_read", "legacy_fixture"):
            if operation in report["measurements"]:
                key = (size, operation)
                output = report["measurements"][operation]["output"]
                if key in legacy_outputs and legacy_outputs[key] != output:
                    raise AssertionError(
                        f"Legacy output mismatch across arms for {key}"
                    )
                legacy_outputs[key] = output
    rows = []
    for size in SIZES:
        for operation in (*OPERATIONS, *(("legacy_fixture",) if size == 2048 else ())):
            values, peaks = {}, {}
            for arm in ARMS:
                selected = [
                    report["measurements"][operation]
                    for spec, report in reports
                    if spec["mode"] == "warm"
                    and spec["size"] == size
                    and spec["arm"] == arm
                ]
                assert len(selected) == 3
                values[arm] = statistics.median(
                    value["median_seconds"] for value in selected
                )
                peaks[arm] = statistics.median(
                    value["separate_tracemalloc_bytes"]["peak"] for value in selected
                )
            rows.append(
                {
                    "size": size,
                    "operation": operation,
                    "seconds": values,
                    "optimized_over_base": values["optimized"] / values["base"],
                    "optimized_over_old": values["optimized"] / values["old"],
                    "median_separate_tracemalloc_peak_bytes": peaks,
                }
            )
    summary = {
        "estimator": "median of three independent warm-process medians; "
        "within-process repetitions correlated; no statistical superiority claim",
        "base_optimized_exact_outputs": "PASS across sizes, replications and cache modes",
        "matched_dependencies_and_harness": "PASS",
        "identical_inputs_and_archives": "PASS",
        "old_base_optimized_legacy_outputs": "PASS for all shared persistence digests",
        "old_contracts": "OLD precomputed includes centroids but lacks NEW ownership/validation; "
        "OLD plotting leaf sizes are one; OLD persistence lacks NEW integrity/materialization work",
        "cold": "Exploratory single process per arm/operation/cache condition; raw files only",
        "rows": rows,
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        summary["estimator"],
        "",
        summary["old_contracts"],
        "",
        "Ratios are OPT/BASE and OPT/OLD; below one means shorter runtime.",
        "",
        "| n | Operation | OLD s | #211 s | OPTIMIZED s | vs #211 | vs OLD |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        times = row["seconds"]
        lines.append(
            f"| {row['size']} | {row['operation']} | {times['old']:.9f} | "
            f"{times['base']:.9f} | {times['optimized']:.9f} | "
            f"{row['optimized_over_base']:.3f} | {row['optimized_over_old']:.3f} |"
        )
    (root / "summary.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New artifact directory")
    parser.add_argument(
        "--cache-root", help="New separate cache directory; defaults under output"
    )
    parser.add_argument(
        "--python", default=sys.executable, help="Interpreter used for ALL workers"
    )
    parser.add_argument(
        "--repos", nargs=3, default=DEFAULT_REPOS, metavar=("OLD", "BASE", "OPT")
    )
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    root = Path(args.output).absolute()
    cache_root = (
        Path(args.cache_root).absolute() if args.cache_root else root / "numba_cache"
    )
    # Preserve a venv executable path; resolving its symlink bypasses that venv.
    python = Path(args.python).absolute()
    harness = Path(__file__).with_name("benchmark.py").resolve()
    repos = dict(zip(ARMS, (Path(value).resolve() for value in args.repos)))
    fixture = repos["base"] / "tests/data/mock-20ng.tm.zip"
    specs = list(worker_specs(root, cache_root, python, harness, repos, fixture))
    if args.plan:
        for spec in specs:
            print(
                f"NUMBA_CACHE_DIR={shlex.quote(spec['cache_directory'])} "
                + shlex.join(spec["command"])
            )
        return
    if root.exists() or cache_root.exists():
        raise FileExistsError("Campaign artifact/cache roots must not already exist")
    root.mkdir(parents=True)
    cache_root.mkdir(parents=True)
    for directory in ("archives", "raw", "logs"):
        (root / directory).mkdir()
    manifest = {
        "methodology": __doc__,
        "interpreter": str(python),
        "harness_sha256": file_digest(harness),
        "runner_sha256": file_digest(__file__),
        "sources": {arm: source_identity(repo) for arm, repo in repos.items()},
        "specifications": specs,
        "processes": [],
        "errors": [],
        "status": "running",
    }
    save_manifest(root, manifest)
    try:
        for size in SIZES:
            command = [
                str(python),
                str(harness),
                "prepare",
                "--size",
                str(size),
                "--archive",
                str(root / "archives" / f"n{size}.zip"),
            ]
            invoke(root, manifest, f"prepare-n{size}", command, dict(os.environ))
        for spec in specs:
            source = source_identity(repos[spec["arm"]])
            for field in ("head", "python_source_sha256"):
                if source[field] != manifest["sources"][spec["arm"]][field]:
                    raise RuntimeError(
                        f"Source changed during campaign: {spec['arm']} {field}"
                    )
            if file_digest(harness) != manifest["harness_sha256"]:
                raise RuntimeError("Harness changed during campaign")
            cache = Path(spec["cache_directory"])
            if spec["cold_condition"] != "primed":
                cache.mkdir()
            environment = {**os.environ, "NUMBA_CACHE_DIR": str(cache)}
            invoke(root, manifest, spec["name"], spec["command"], environment, cache)
        summarize(root, specs)
        manifest["status"] = "complete"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["errors"].append(
            {"error_type": type(error).__name__, "message": str(error)}
        )
        raise
    finally:
        save_manifest(root, manifest)


if __name__ == "__main__":
    main()
