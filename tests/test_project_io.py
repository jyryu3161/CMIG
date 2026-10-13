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


def _lock_path(root: Path) -> Path:
    return root / ".cmig-project.lock"


def test_lock_message_names_lock_file_and_recovery(tmp_path: Path) -> None:
    root = tmp_path / "remote-msg"
    proj.create_project(root)
    _lock_path(root).write_text(
        json.dumps({"pid": 1, "host": "some-other-machine", "created": "x"})
    )
    with pytest.raises(proj.ProjectError, match="already open") as excinfo:
        proj.ProjectLock.acquire(root)
    message = str(excinfo.value)
    assert str(_lock_path(root.resolve())) in message
    assert "delete" in message


@pytest.mark.parametrize(
    "content", [b"[]", b"null", b'"x"', b"7", b"", b"garbage {", b"\xff\xfe\x00{"]
)
def test_garbage_lock_is_reported_not_reclaimed_or_leaked(tmp_path: Path, content: bytes) -> None:
    root = tmp_path / "garbage"
    proj.create_project(root)
    _lock_path(root).write_bytes(content)
    before = _lock_path(root).read_bytes()
    with pytest.raises(proj.ProjectError, match="already open") as excinfo:
        proj.ProjectLock.acquire(root)
    assert str(_lock_path(root.resolve())) in str(excinfo.value)
    assert _lock_path(root).read_bytes() == before


@pytest.mark.parametrize("pid", [2**80, -5, 0, "123", 1.5, True, None])
def test_lock_with_unusable_pid_is_respected(tmp_path: Path, pid: object) -> None:
    root = tmp_path / "pids"
    proj.create_project(root)
    _lock_path(root).write_text(
        json.dumps({"pid": pid, "host": socket.gethostname(), "created": "x"})
    )
    with pytest.raises(proj.ProjectError, match="already open"):
        proj.ProjectLock.acquire(root)
    assert json.loads(_lock_path(root).read_text())["pid"] == pid


def test_lock_in_missing_folder_is_project_error(tmp_path: Path) -> None:
    with pytest.raises(proj.ProjectError, match="cannot create project lock"):
        proj.ProjectLock.acquire(tmp_path / "nope")


def _write_project(root: Path, **overrides: object) -> str:
    """Write a hand-made project file (valid unless overridden) and return its exact text."""
    root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"format_version": 1, "name": "hand", "created": "t"}
    payload.update(overrides)
    text = json.dumps(payload)
    (root / "cmig-project.json").write_text(text)
    return text


def _model(model_id: object = "m1", file: object = "models/m1.xml") -> dict[str, object]:
    return {
        "id": model_id,
        "file": file,
        "source_path": "/src/m1.xml",
        "sha256": "0" * 64,
        "format": "sbml",
        "added": "t",
    }


def _medium(medium_id: object = "d1", file: object = "media/d1.csv") -> dict[str, object]:
    return {
        "id": medium_id,
        "file": file,
        "source_path": "/src/d1.csv",
        "sha256": "0" * 64,
        "added": "t",
    }


def test_open_accepts_well_formed_entries(tmp_path: Path) -> None:
    root = tmp_path / "ok"
    _write_project(
        root,
        models=[_model("a", "models/a.xml"), _model("b", "models/b.xml")],
        media=[_medium()],
        analysis_settings={"search": {"models": ["a"]}},
    )
    project = proj.open_project(root)
    assert [m.id for m in project.models] == ["a", "b"]
    assert project.medium("d1").file == "media/d1.csv"


@pytest.mark.parametrize(
    "overrides",
    [
        {"analysis_settings": []},
        {"analysis_settings": "x"},
        {"analysis_settings": None},
        {"analysis_settings": {"search": 3}},
        {"analysis_settings": {"search": ["a"]}},
        {"analysis_settings": [["a", "b"]]},
        {"analysis_settings": ["ab"]},
        {"models": {"a": 1}},
        {"models": "x"},
        {"models": [3]},
        {"models": [{"id": "a"}]},
        {"media": None},
        {"models": [_model("a"), _model("a", "models/other.xml")]},
        {"media": [_medium("d"), _medium("d", "media/other.csv")]},
        {"models": [_model(1)]},
        {"models": [_model(None)]},
        {"media": [_medium(["d"])]},
        {"models": [_model("a", 5)]},
        {"models": [_model("a", None)]},
        {"media": [_medium("d", {"x": 1})]},
    ],
)
def test_open_rejects_malformed_shapes_without_touching_file(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    root = tmp_path / "shape"
    text = _write_project(root, **overrides)
    with pytest.raises(proj.ProjectError, match="malformed"):
        proj.open_project(root)
    assert (root / "cmig-project.json").read_text() == text


def test_same_id_in_models_and_media_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "shared-id"
    _write_project(root, models=[_model("x")], media=[_medium("x")])
    project = proj.open_project(root)
    assert project.model("x").id == project.medium("x").id == "x"


@pytest.mark.parametrize(
    "file",
    [
        "../../etc/passwd",
        "models/../../escape.xml",
        "/etc/passwd",
        "\\\\server\\share\\m.xml",
        "\\abs\\m.xml",
        "C:\\models\\m.xml",
        "C:m.xml",
        "",
        ".",
        "models/\x00bad.xml",
    ],
)
def test_open_rejects_entry_file_outside_project(tmp_path: Path, file: str) -> None:
    for key, entry in (("models", _model("a", file)), ("media", _medium("d", file))):
        root = tmp_path / f"escape-{key}"
        text = _write_project(root, **{key: [entry]})
        with pytest.raises(proj.ProjectError, match="malformed"):
            proj.open_project(root)
        assert (root / "cmig-project.json").read_text() == text


def test_open_rejects_absolute_native_path(tmp_path: Path) -> None:
    root = tmp_path / "abs"
    text = _write_project(root, models=[_model("a", str(tmp_path / "outside.xml"))])
    with pytest.raises(proj.ProjectError, match="malformed"):
        proj.open_project(root)
    assert (root / "cmig-project.json").read_text() == text


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_open_rejects_entry_file_escaping_through_symlink(tmp_path: Path) -> None:
    root = tmp_path / "link"
    text = _write_project(root, models=[_model("a", "models/evil/m.xml")])
    (tmp_path / "outside").mkdir()
    (root / "models").mkdir()
    (root / "models" / "evil").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(proj.ProjectError, match="malformed"):
        proj.open_project(root)
    assert (root / "cmig-project.json").read_text() == text


def test_open_non_utf8_project_file_is_project_error(tmp_path: Path) -> None:
    root = tmp_path / "bytes"
    root.mkdir()
    (root / "cmig-project.json").write_bytes(b'{"name": "\xff\xfe"}')
    with pytest.raises(proj.ProjectError, match="not valid JSON"):
        proj.open_project(root)


def test_open_unreadable_project_file_is_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "unreadable"
    _write_project(root)
    real_read_text = Path.read_text

    def deny(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "cmig-project.json":
            raise PermissionError("denied")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", deny)
    with pytest.raises(proj.ProjectError, match="cannot read"):
        proj.open_project(root)


def test_open_unpreparable_folder_is_project_error(tmp_path: Path) -> None:
    root = tmp_path / "blocked"
    _write_project(root)
    (root / "models").write_text("a file where a folder belongs")
    with pytest.raises(proj.ProjectError, match="cannot prepare"):
        proj.open_project(root)
