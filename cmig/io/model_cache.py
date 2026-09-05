"""Canonical, disposable model files without modifying the user's source models."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any


class ModelFileCache:
    def __init__(self) -> None:
        self._directory = tempfile.TemporaryDirectory(prefix="cmig-model-cache-")
        self._entries: dict[tuple[str, int, int], str] = {}

    def prepare(self, taxonomy: Any, *, all_models: bool = False) -> Any:
        if "file" not in getattr(taxonomy, "columns", ()):
            return taxonomy
        prepared = taxonomy.copy()
        prepared["file"] = [
            self.path(str(path), all_models=all_models) for path in taxonomy["file"]
        ]
        return prepared

    def path(self, source: str, *, all_models: bool = False) -> str:
        path = Path(source)
        # MICOM's loader is case sensitive and does not recognise plain .sbml.
        if not all_models and path.suffix in {".xml", ".gz", ".json", ".mat"}:
            return source
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if key in self._entries:
            return self._entries[key]
        from cobra.io import save_json_model

        from cmig.io.atomic import atomic_write_path
        from cmig.io.model_import import load_cobra_model

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        target = Path(self._directory.name) / f"{digest}.json"
        if not target.exists():
            model = load_cobra_model(path)
            atomic_write_path(target, lambda tmp: save_json_model(model, str(tmp), sort=True))
        self._entries[key] = str(target)
        return str(target)

    def close(self) -> None:
        self._directory.cleanup()
