import json, os, subprocess, sys, tempfile, time
from pathlib import Path

repo = Path("/Users/agus/Developer/toponymy-perf")
base = Path("/Users/agus/Developer/toponymy-perf-base")
python = repo / ".venv/bin/python"
out = repo / "doc/performance_recovery/correction/validation"
records = []
with tempfile.TemporaryDirectory(prefix="toponymy-correction-validation-") as temporary:
    root = Path(temporary)
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        HYPOTHESIS_STORAGE_DIRECTORY=str(root / "hypothesis"),
        COVERAGE_FILE=str(root / "coverage"),
    )
    threads = (
        "NUMBA_NUM_THREADS",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    env.update({key: "1" for key in threads})

    def run(name, arguments, cwd=repo, expected=(0,)):
        local_env = dict(env, NUMBA_CACHE_DIR=str(root / name))
        command = [str(python), *arguments]
        started = time.time()
        with (out / (name + ".txt")).open("x") as log:
            result = subprocess.run(
                command, cwd=cwd, env=local_env, stdout=log, stderr=subprocess.STDOUT
            )
        records.append(
            dict(
                name=name,
                command=command,
                cwd=str(cwd),
                returncode=result.returncode,
                seconds=time.time() - started,
                expected=list(expected),
            )
        )
        (out / "commands.json").write_text(
            json.dumps(
                dict(threads={key: env[key] for key in threads}, commands=records),
                indent=2,
            )
            + "\n"
        )
        print(name, result.returncode, flush=True)
        return result.returncode

    pytest = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:azurepipelines"]
    run(
        "focused",
        pytest
        + [
            "tests/test_clustering_contracts.py",
            "tests/test_clustering_characterization.py",
            "tests/test_clustering_adapters.py",
            "tests/test_result_consumers.py",
            "tests/test_performance_clustering.py",
            "tests/test_performance_centroids.py",
            "tests/test_performance_persistence.py",
            "tests/test_archive_boundaries.py",
            "tests/test_archive_identity.py",
            "tests/test_persistence_contracts.py",
            "tests/test_lance_integrity.py",
            "tests/test_migration_regressions.py",
            "tests/test_name_state.py",
            "tests/test_reuse_and_renderings.py",
        ],
    )
    run(
        "full",
        pytest
        + [
            "--cov=toponymy",
            "--cov-report=term",
            "--cov-report=json:" + str(out / "coverage.json"),
        ],
    )
    # Capture the existing assertion helper's inputs without changing its assertion.
    plugin = root / "correction_evoc_capture.py"
    plugin.write_text(
        """import hashlib, json\nimport numpy as np\nfrom sklearn.metrics import adjusted_mutual_info_score\ndef pytest_collection_modifyitems(items):\n    module=items[0].module\n    original=module._assert_assigned_ami\n    def capture(labels, ground_truth, minimum):\n        assigned=labels>=0\n        print("EVOC_OBSERVATION="+json.dumps(dict(ami=adjusted_mutual_info_score(ground_truth[assigned],labels[assigned]),assigned=int(assigned.sum()),clusters=int(np.unique(labels[assigned]).size),label_sha256=hashlib.sha256(labels.tobytes()).hexdigest(),minimum=minimum)))\n        return original(labels,ground_truth,minimum)\n    module._assert_assigned_ami=capture\n"""
    )
    env["PYTHONPATH"] = str(root)
    target = "tests/test_clustering_quality.py::test_evoc_refactor_default_hierarchy_quality_matches_original_threshold"
    run("evoc-after", pytest + ["-s", "-p", "correction_evoc_capture", target])
    run("evoc-base", pytest + ["-s", "-p", "correction_evoc_capture", target], cwd=base)
    env.pop("PYTHONPATH")
    run(
        "centroid-differential",
        [
            "doc/performance_recovery/check_centroids.py",
            "--base",
            str(base),
            "--optimized",
            str(repo),
        ],
    )
    run(
        "persistence-differential",
        [
            "doc/performance_recovery/check_persistence.py",
            "--base",
            "04c300c6a0fe1117531a64e6a7966b436eadfce7",
            "--output",
            str(out / "persistence-differential.json"),
        ],
    )
    run(
        "black",
        [
            "-m",
            "black",
            "--check",
            "--diff",
            "--target-version",
            "py310",
            "toponymy/",
            "doc/",
            "tests/test_performance_clustering.py",
            "tests/test_performance_centroids.py",
            "tests/test_performance_persistence.py",
        ],
    )
    modules = [
        "toponymy/clustering.py",
        "toponymy/types.py",
        "toponymy/utility_functions.py",
        "toponymy/plotting.py",
        "toponymy/serialization.py",
    ]
    typing = [
        "-m",
        "mypy",
        "--no-incremental",
        "--cache-dir",
        str(root / "mypy"),
        "--follow-imports=silent",
        "--ignore-missing-imports",
    ]
    run("mypy-after", typing + modules, expected=(1,))
    run("mypy-base", typing + modules, cwd=base, expected=(1,))
    run("mypy-clean", typing + [modules[i] for i in (1, 2, 3)])
    run(
        "compilation",
        [
            "-c",
            "import pathlib,py_compile,tempfile; files=[*pathlib.Path('toponymy').rglob('*.py'),*pathlib.Path('doc/performance_recovery').rglob('*.py')]; d=tempfile.TemporaryDirectory(); [py_compile.compile(str(p),cfile=d.name+'/'+str(i)+'.pyc',doraise=True) for i,p in enumerate(files)]; print(f'Compiled {len(files)} Python files'); d.cleanup()",
        ],
    )
    run(
        "dependency-audit",
        [
            "-m",
            "pip_audit",
            "--format",
            "json",
            "--output",
            str(out / "dependency-audit.json"),
        ],
        expected=(1,),
    )
