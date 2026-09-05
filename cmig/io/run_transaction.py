"""Stage a complete run and roll back publication failures as a directory transaction."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def staged_run(
    destination: str | Path, *, artifacts: frozenset[str] = frozenset()
) -> Iterator[Path]:
    target = Path(destination).resolve()
    if target in {Path(target.anchor), Path.home(), Path.cwd(), *Path.cwd().parents}:
        raise ValueError("search output must be a dedicated run directory")
    if target.exists() and not target.is_dir():
        raise ValueError("search output is not a directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / f".{target.name}.publish.lock"
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError(f"another writer holds the run lock: {lock}") from error
    os.close(handle)
    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{target.name}.stage-", dir=target.parent
        ) as temp:
            root = Path(temp)
            stage = root / "run"
            # Keep the previous directory outside TemporaryDirectory: even a
            # failed rollback must leave recoverable user data on disk.
            previous = target.parent / f".{target.name}.previous-{uuid.uuid4().hex}"
            if target.exists():
                # Preserve unrelated user notes/files while replacing only the
                # workflow's declared artifacts. Never follow existing symlinks.
                shutil.copytree(
                    target,
                    stage,
                    symlinks=True,
                    ignore=lambda directory, names: (
                        set(names) & set(artifacts) if Path(directory) == target else set()
                    ),
                )
            else:
                stage.mkdir()
            yield stage
            moved = False
            try:
                if target.exists():
                    os.replace(target, previous)
                    moved = True
                os.replace(stage, target)
            except BaseException:
                if moved:
                    try:
                        os.replace(previous, target)
                    except OSError as error:
                        raise OSError(
                            f"publication rollback failed; previous run is preserved at {previous}"
                        ) from error
                raise
            if moved:
                shutil.rmtree(previous)
    finally:
        lock.unlink(missing_ok=True)
