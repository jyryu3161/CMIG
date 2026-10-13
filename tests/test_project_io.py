"""Qt-free tests for the on-disk CMIG project format."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from cmig.io import project as proj


def test_create_writes_layout_and_reopens(tmp_path: Path) -> None:
    root = tmp_path / "study"
    created = proj.create_project(root, name="Butyrate study")
    assert (root / "cmig-project.json").is_file()
    for sub in ("models", "media", "runs", "runs/_inputs"):
        assert (root / sub).is_dir()
    reopened = proj.open_project(root)
    assert reopened.name == "Butyrate study"
    assert reopened.created == created.created
    assert reopened.models == [] and reopened.media == []
    payload = json.loads((root / "cmig-project.json").read_text())
    assert payload["format_version"] == 1


def test_create_refuses_non_empty_folder(tmp_path: Path) -> None:
    root = tmp_path / "busy"
    root.mkdir()
    (root / "notes.txt").write_text("mine")
    with pytest.raises(proj.ProjectError, match="not empty"):
        proj.create_project(root)
    assert (root / "notes.txt").read_text() == "mine"
    assert not (root / "cmig-project.json").exists()


def test_create_defaults_name_to_folder(tmp_path: Path) -> None:
    assert proj.create_project(tmp_path / "gut-2026").name == "gut-2026"


@pytest.mark.parametrize(
    "content, message",
    [
        ("{not json", "not valid JSON"),
        ('{"format_version": 99, "name": "x"}', "newer CMIG"),
        ('{"format_version": 1}', "missing"),
        ("[]", "not a JSON object"),
    ],
)
def test_open_rejects_bad_project_without_touching_it(
    tmp_path: Path, content: str, message: str
) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "cmig-project.json").write_text(content)
    with pytest.raises(proj.ProjectError, match=message):
        proj.open_project(root)
    assert (root / "cmig-project.json").read_text() == content


def test_open_missing_project_file(tmp_path: Path) -> None:
    with pytest.raises(proj.ProjectError, match="no cmig-project.json"):
        proj.open_project(tmp_path)


def test_save_is_atomic_and_round_trips_settings(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "s")
    project.analysis_settings["search"] = {"models": ["a", "b"], "medium": "preset:western"}
    proj.save_project(project)
    again = proj.open_project(tmp_path / "s")
    assert again.analysis_settings == {"search": {"models": ["a", "b"], "medium": "preset:western"}}
    leftovers = [p.name for p in (tmp_path / "s").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_lock_blocks_second_open_and_releases(tmp_path: Path) -> None:
    root = tmp_path / "locked"
    proj.create_project(root)
    lock = proj.ProjectLock.acquire(root)
    with pytest.raises(proj.ProjectError, match="already open"):
        proj.ProjectLock.acquire(root)
    lock.release()
    assert not (root / ".cmig-project.lock").exists()
    proj.ProjectLock.acquire(root).release()


def test_stale_lock_from_dead_process_is_replaced(tmp_path: Path) -> None:
    root = tmp_path / "stale"
    proj.create_project(root)
    (root / ".cmig-project.lock").write_text(
        json.dumps({"pid": 2**22 + 12345, "host": socket.gethostname(), "created": "x"})
    )
    lock = proj.ProjectLock.acquire(root)
    held = json.loads((root / ".cmig-project.lock").read_text())
    assert held["pid"] == os.getpid()
    lock.release()


def test_lock_from_other_host_is_respected(tmp_path: Path) -> None:
    root = tmp_path / "remote"
    proj.create_project(root)
    (root / ".cmig-project.lock").write_text(
        json.dumps({"pid": 1, "host": "some-other-machine", "created": "x"})
    )
    with pytest.raises(proj.ProjectError, match="some-other-machine"):
        proj.ProjectLock.acquire(root)
