"""Atomic publication when the platform has no descriptor chmod operation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmig.io import atomic


@pytest.mark.parametrize("writer", ["binary", "text", "path"])
def test_atomic_writers_without_fchmod_replace_and_clean_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer: str
) -> None:
    target = tmp_path / "artifact"
    target.write_bytes(b"previous")
    monkeypatch.delattr(atomic.os, "fchmod", raising=False)

    if writer == "binary":
        atomic.atomic_write_bytes(target, b"replacement")
    elif writer == "text":
        atomic.atomic_write_text(target, "replacement")
    else:
        atomic.atomic_write_path(target, lambda path: path.write_bytes(b"replacement"))

    assert target.read_bytes() == b"replacement"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("writer", ["binary", "text", "path"])
def test_atomic_writers_without_fchmod_keep_previous_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer: str
) -> None:
    target = tmp_path / "artifact"
    target.write_bytes(b"previous")
    monkeypatch.delattr(atomic.os, "fchmod", raising=False)

    def fail_replace(_source: os.PathLike[str], _destination: os.PathLike[str]) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(atomic.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        if writer == "binary":
            atomic.atomic_write_bytes(target, b"replacement")
        elif writer == "text":
            atomic.atomic_write_text(target, "replacement")
        else:
            atomic.atomic_write_path(target, lambda path: path.write_bytes(b"replacement"))

    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.skipif(not hasattr(os, "fchmod"), reason="POSIX descriptor chmod unavailable")
@pytest.mark.parametrize("writer", ["binary", "text", "path"])
def test_atomic_writer_preserves_existing_posix_mode(tmp_path: Path, writer: str) -> None:
    target = tmp_path / "artifact"
    target.write_bytes(b"previous")
    target.chmod(0o640)

    if writer == "binary":
        atomic.atomic_write_bytes(target, b"replacement")
    elif writer == "text":
        atomic.atomic_write_text(target, "replacement")
    else:
        atomic.atomic_write_path(target, lambda path: path.write_bytes(b"replacement"))

    assert target.stat().st_mode & 0o777 == 0o640
