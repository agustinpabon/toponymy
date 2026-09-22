import hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path

repo = Path("/Users/agus/Developer/toponymy-perf")
python = repo / ".venv/bin/python"
out = repo / "doc/performance_recovery/correction/validation"
with tempfile.TemporaryDirectory(prefix="toponymy-correction-package-") as tmp:
    root = Path(tmp)
    source = root / "source"
    source.mkdir()
    # Copy tracked working files, including current edits, without modifying build state in any checkout.
    for name in (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=repo)
        .decode()
        .split("\0")
    ):
        if name:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, target)
    shutil.copy2(
        repo / "doc/performance_recovery/check_tree_depth.py",
        source / "doc/performance_recovery/check_tree_depth.py",
    )
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        NUMBA_CACHE_DIR=str(root / "numba"),
    )
    with (out / "package-build.txt").open("x") as log:
        result = subprocess.run(
            [
                str(python),
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(root / "dist"),
            ],
            cwd=source,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    assert result.returncode == 0
    wheel = next((root / "dist").glob("*.whl"))
    target = root / "installed"
    with (out / "package-smoke.txt").open("x") as log:
        installed = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(target),
                str(wheel),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        assert installed.returncode == 0
        env["PYTHONPATH"] = str(target)
        code = """from pathlib import Path
import numpy as np
import toponymy
from toponymy.clustering import PrecomputedClusterer,build_cluster_tree
from toponymy.serialization import TopicModel
import os,tempfile
assert Path(toponymy.__file__).resolve().is_relative_to(Path(os.environ['PYTHONPATH']))
labels=[np.array([7,-1,19,7])]*64
fitted=PrecomputedClusterer(labels).fit(np.ones((4,2)))
assert build_cluster_tree(labels)==fitted.cluster_tree_
model=TopicModel.from_file(Path(os.environ['SMOKE_FIXTURE']))
with tempfile.TemporaryDirectory() as d:
 for suffix in ('zip','lance'):
  path=Path(d)/('model.'+suffix)
  model.to_file(path)
  loaded=TopicModel.from_file(path)
  assert loaded.cluster_tree==model.cluster_tree
  np.testing.assert_array_equal(loaded.embedding_vectors,model.embedding_vectors)
  assert loaded.topics.keys()==model.topics.keys()
  for key in model.topics:
   np.testing.assert_array_equal(loaded.topics[key].members,model.topics[key].members)
print('Installed wheel:',toponymy.__file__)
print('Depth-64 clustering, real legacy fixture read, ZIP/Lance round trips passed')
"""
        env["SMOKE_FIXTURE"] = str(repo / "tests/data/mock-20ng.tm.zip")
        smoke = subprocess.run(
            [str(python), "-c", code],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        assert smoke.returncode == 0
    (out / "package-artifacts.json").write_text(
        json.dumps(
            {
                p.name: {
                    "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
                for p in (root / "dist").iterdir()
            },
            indent=2,
        )
        + "\n"
    )
print("Build and installed-wheel smoke passed")
