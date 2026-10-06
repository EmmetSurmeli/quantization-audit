from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if canonical(read_json(path)) != canonical(value):
            raise ValueError(f"Refusing to overwrite immutable artifact: {path}")
        return
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextlib.contextmanager
def workspace_lock(workspace):
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    with (workspace / ".lock").open("a") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another audit command is using this workspace") from exc
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def environment():
    names = ["quantization-audit", "numpy", "scipy", "matplotlib", "mlx", "mlx-lm", "transformers", "huggingface-hub", "datasets"]
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(), "packages": versions}


def source_hash(names=None):
    root = Path(__file__).parent
    paths = sorted(root.glob("*.py")) if names is None else [root / f"{n}.py" for n in names]
    return digest({p.name: file_hash(p) for p in paths})


def config_at(workspace):
    return read_json(Path(workspace) / "study.json")


def configure_cache(workspace):
    cache = Path(workspace).resolve() / "cache"
    # Keep downloads and plotting caches inside the authorized study directory.
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HF_DATASETS_CACHE"] = str(cache / "datasets")
    os.environ["MPLCONFIGDIR"] = str(cache / "matplotlib")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"


def stable_order(rows, seed, purpose):
    return sorted(rows, key=lambda r: digest([seed, purpose, r["key"]]))
