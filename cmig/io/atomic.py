"""Atomic artifact publication — a failed write must not destroy the previous file.

R5-P3 (opus F4 / codex F8, V3): `Path.write_text` truncates the destination *before* it writes,
so any failure part-way through (disk full, process death) leaves a half-written file where a
valid one used to be. For a run artifact that is the record of a completed analysis, that turns a
failed re-run into the loss of the previous run's result.

`cmig/io/solve_output.py` already publishes the solve directory this way (stage, then
`os.replace`); this module is the same idea for a single file, so the rest of the codebase does
not have to reinvent it.

`os.replace` is atomic only within a filesystem, so the temporary file is created in the
*destination directory* rather than in the system temp dir.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


def atomic_write_binary(
    path: str | Path, writer: Callable[[BinaryIO], object]
) -> Path:
    """Publish binary output produced by ``writer`` without exposing partial bytes.

    ``writer`` receives an open binary file. The file is flushed and synced before the
    same-filesystem replacement. On any exception the temporary file is removed and the previous
    destination remains untouched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    """Atomically publish ``data`` to ``path``."""

    def write(handle: BinaryIO) -> None:
        handle.write(data)

    return atomic_write_binary(path, write)


def atomic_write_parquet(path: str | Path, table: object) -> Path:
    """Atomically publish a PyArrow table while preserving its normal on-disk bytes."""
    import pyarrow.parquet as pq

    return atomic_write_binary(
        path, lambda handle: pq.write_table(table, handle)  # type: ignore[no-untyped-call]
    )


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    """Write ``text`` to ``path`` so the previous contents survive any failure.

    Returns the written path. On any exception the temporary file is removed and the original
    ``path`` is left exactly as it was.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target
