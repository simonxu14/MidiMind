from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


def get_storage_dir(default_subdir: str, env_var: Optional[str] = None) -> Path:
    """Resolve a persistent application storage directory and ensure it exists."""
    override = os.environ.get(env_var) if env_var else None
    if override:
        path = Path(override).expanduser()
    else:
        root = Path(os.environ.get("MIDIMIND_STORAGE_DIR", "~/.midimind")).expanduser()
        path = root / default_subdir

    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace a file with byte content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp_file:
        tmp_file.write(data)
        tmp_path = Path(tmp_file.name)

    os.replace(tmp_path, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    """Atomically replace a file with UTF-8 JSON."""
    atomic_write_bytes(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
    )
