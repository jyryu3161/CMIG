"""Qt-free tests for the on-disk CMIG project format."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import shutil
import socket
from collections.abc import Iterator
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
    with pytest.raises(proj.ProjectError, match="^project folder is not empty"):
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


def _fake_model(path: Path, body: str = "<sbml/>") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _ok_check(_path: Path) -> proj.ModelCheck:
    return proj.ModelCheck(
        status="ok", error=None, n_reactions=10, n_metabolites=8, n_genes=3,
        biomass=["BIOMASS"], namespace_coverage_pct=97.5, warnings=[],
    )


def test_add_model_copies_and_never_touches_source(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "in" / "E_rectale.xml", "<sbml>rectale</sbml>")
    before = src.read_bytes()
    entry = proj.add_model_file(project, src, check=_ok_check)
    assert entry.id == "E_rectale"
    assert entry.file == "models/E_rectale.xml"
    assert entry.sha256 == hashlib.sha256(before).hexdigest()
    assert entry.status == "ok" and entry.n_reactions == 10
    assert (project.root / entry.file).read_bytes() == before
    assert src.read_bytes() == before
    assert proj.model_path(project, entry) == project.root / "models" / "E_rectale.xml"


def test_duplicate_content_is_refused(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    a = _fake_model(tmp_path / "a" / "x.xml", "same")
    b = _fake_model(tmp_path / "b" / "y.xml", "same")
    proj.add_model_file(project, a, check=_ok_check)
    with pytest.raises(proj.DuplicateModelError) as info:
        proj.add_model_file(project, b, check=_ok_check)
    assert info.value.existing_id == "x"
    assert len(project.models) == 1


def test_ids_unique_for_same_stem_and_odd_names(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    first = proj.add_model_file(
        project, _fake_model(tmp_path / "1" / "model.xml", "1"), check=None
    )
    second = proj.add_model_file(
        project, _fake_model(tmp_path / "2" / "model.xml", "2"), check=None
    )
    odd = proj.add_model_file(
        project, _fake_model(tmp_path / "3" / "B. longum 이름.json.xml", "3"), check=None
    )
    gz = proj.add_model_file(project, _fake_model(tmp_path / "4" / "Akk.xml.gz", "4"), check=None)
    ids = [first.id, second.id, odd.id, gz.id]
    assert len(set(ids)) == 4
    assert first.id == "model" and second.id.startswith("model_")
    assert all(i[0].isalpha() or i[0] == "_" for i in ids)
    assert second.file != first.file and second.file.endswith(".xml")
    assert gz.file.endswith(".xml.gz")
    assert first.status == "pending" and first.integrity == "ok"


def test_unsupported_model_suffix_is_refused(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    with pytest.raises(proj.ProjectError, match="not a supported model file"):
        proj.add_model_file(project, _fake_model(tmp_path / "notes.txt"), check=None)


def test_copy_failure_leaves_no_partial_file(tmp_path: Path, monkeypatch) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "big.xml", "x" * 1000)

    def boom(path, writer):
        raise OSError("disk full")

    monkeypatch.setattr(proj, "atomic_write_binary", boom)
    with pytest.raises(proj.ProjectError, match="disk full"):
        proj.add_model_file(project, src, check=None)
    assert list(project.models_dir.iterdir()) == []
    assert project.models == []


def test_check_model_file_never_raises(tmp_path: Path) -> None:
    result = proj.check_model_file(_fake_model(tmp_path / "broken.xml", "not sbml"))
    assert result.status == "failed"
    assert result.error


def test_verify_checksums_flags_changed_and_missing(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    a = proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    b = proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    (project.root / a.file).write_text("tampered")
    (project.root / b.file).unlink()
    changed = proj.verify_checksums(project)
    assert sorted(changed) == ["a", "b"]
    assert project.model("a").integrity == "changed"
    assert project.model("b").integrity == "missing"
    assert proj.selectable_models(project) == []


def test_selectable_excludes_failed_and_pending(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    ok = proj.add_model_file(project, _fake_model(tmp_path / "ok.xml", "1"), check=_ok_check)
    warn = proj.add_model_file(project, _fake_model(tmp_path / "w.xml", "2"), check=_ok_check)
    warn.status = "warning"
    bad = proj.add_model_file(project, _fake_model(tmp_path / "bad.xml", "3"), check=None)
    bad.status = "failed"
    proj.add_model_file(project, _fake_model(tmp_path / "pend.xml", "4"), check=None)
    assert [m.id for m in proj.selectable_models(project)] == [ok.id, warn.id]


def test_open_project_reverifies_checksums(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.save_project(project)
    (project.root / entry.file).write_text("edited elsewhere")
    assert proj.open_project(project.root).model("a").integrity == "changed"


def test_remove_restore_rename(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    b = proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    index, removed = proj.remove_model(project, "a")
    assert [m.id for m in project.models] == ["b"]
    assert (project.root / removed.file).exists(), "files stay on disk for run references"
    proj.restore_model(project, index, removed)
    assert [m.id for m in project.models] == ["a", "b"]
    proj.rename_model(project, "b", "Bifido_longum")
    assert project.model("Bifido_longum").sha256 == b.sha256
    for bad in ("a", "1abc", "has space", ""):
        with pytest.raises(proj.ProjectError):
            proj.rename_model(project, "Bifido_longum", bad)


def test_add_medium(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    entry = proj.add_medium_file(project, src)
    assert entry.id == "diet" and entry.file == "media/diet.csv"
    assert proj.medium_path(project, entry).read_text() == src.read_text()
    with pytest.raises(proj.ProjectError, match="CSV or JSON"):
        proj.add_medium_file(project, _fake_model(tmp_path / "x.xml"))


def test_new_run_dir_never_reuses(tmp_path: Path, monkeypatch) -> None:
    project = proj.create_project(tmp_path / "p")
    monkeypatch.setattr(proj, "_stamp", lambda: "20261013-103100")
    first = proj.new_run_dir(project, "search")
    second = proj.new_run_dir(project, "search")
    assert first.name == "search-20261013-103100"
    assert second.name == "search-20261013-103100-2"
    assert first.is_dir() and second.is_dir()
    with pytest.raises(proj.ProjectError):
        proj.new_run_dir(project, "../escape")


def test_write_run_taxonomy(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    a = proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    run = proj.new_run_dir(project, "community")
    path = proj.write_run_taxonomy(project, run, ["b", "a"], abundances={"a": 0.25})
    assert path == project.inputs_dir / f"{run.name}-taxonomy.csv"
    rows = list(csv.DictReader(path.open()))
    assert [r["id"] for r in rows] == ["b", "a"]
    assert rows[1]["file"] == str(project.root / a.file)
    assert [float(r["abundance"]) for r in rows] == [1.0, 0.25]
    assert list(run.iterdir()) == [], "nothing is pre-written into the CLI's run folder"
    (project.root / a.file).write_text("tampered")
    with pytest.raises(proj.ProjectError, match="not selectable.*changed since it was added"):
        proj.write_run_taxonomy(project, run, ["a"])
    with pytest.raises(proj.ProjectError, match="no models"):
        proj.write_run_taxonomy(project, run, [])


def test_project_survives_move(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "old")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.save_project(project)
    (tmp_path / "old").rename(tmp_path / "new")
    moved = proj.open_project(tmp_path / "new")
    assert moved.model("a").integrity == "ok"
    run = proj.new_run_dir(moved, "search")
    rows = list(csv.DictReader(proj.write_run_taxonomy(moved, run, ["a"]).open()))
    assert rows[0]["file"].startswith(str(tmp_path / "new"))


def test_supported_model_paths_filters_and_counts(tmp_path: Path) -> None:
    folder = tmp_path / "pool"
    _fake_model(folder / "a.xml")
    _fake_model(folder / "sub" / "b.mat")
    _fake_model(folder / "readme.txt")
    _fake_model(folder / ".hidden.xml")
    (folder / "notcobra.json").write_text('{"hello": 1}')
    files, skipped = proj.supported_model_paths([folder])
    assert sorted(p.name for p in files) == ["a.xml", "b.mat"]
    assert skipped == 3
    flat, _ = proj.supported_model_paths([folder], recursive=False)
    assert [p.name for p in flat] == ["a.xml"]


# --- filesystem failures surface as ProjectError, never a raw OSError -------------------------


def _deny_write(*_args: object, **_kwargs: object) -> None:
    raise OSError("disk full")


def test_save_write_failure_is_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = proj.create_project(tmp_path / "p")
    before = project.project_file.read_text()
    monkeypatch.setattr(proj, "atomic_write_text", _deny_write)
    with pytest.raises(proj.ProjectError, match="cannot save.*disk full"):
        proj.save_project(project)
    assert project.project_file.read_text() == before


def test_create_first_save_failure_is_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proj, "atomic_write_text", _deny_write)
    with pytest.raises(proj.ProjectError, match="cannot save"):
        proj.create_project(tmp_path / "p")


def test_create_mkdir_failure_is_project_error(tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    with pytest.raises(proj.ProjectError, match="cannot create project"):
        proj.create_project(blocker / "p")


needs_posix_perms = pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions enforced for this user",
)


@contextlib.contextmanager
def _unsearchable(folder: Path) -> Iterator[None]:
    folder.chmod(0)
    try:
        yield
    finally:
        folder.chmod(0o700)


@needs_posix_perms
def test_open_unsearchable_folder_is_project_error(tmp_path: Path) -> None:
    root = tmp_path / "locked-folder"
    proj.create_project(root)
    with (
        _unsearchable(root),
        pytest.raises(proj.ProjectError, match="cannot open project folder|no cmig-project"),
    ):
        proj.open_project(root)


@needs_posix_perms
def test_create_unreadable_empty_folder_is_project_error(tmp_path: Path) -> None:
    root = tmp_path / "empty-but-locked"
    root.mkdir()
    with _unsearchable(root), pytest.raises(proj.ProjectError, match="cannot create project"):
        proj.create_project(root)
    assert not (root / "cmig-project.json").exists()


@needs_posix_perms
def test_add_model_from_unsearchable_parent_is_project_error(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "in" / "a.xml", "a")
    with _unsearchable(src.parent), pytest.raises(proj.ProjectError, match="cannot read"):
        proj.add_model_file(project, src, check=None)
    assert project.models == [] and list(project.models_dir.iterdir()) == []


@needs_posix_perms
def test_add_medium_from_unsearchable_parent_is_project_error(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = tmp_path / "in" / "diet.csv"
    src.parent.mkdir()
    src.write_text("exchange,uptake\n")
    with _unsearchable(src.parent), pytest.raises(proj.ProjectError, match="cannot read"):
        proj.add_medium_file(project, src)
    assert project.media == []


@needs_posix_perms
def test_add_model_into_unsearchable_models_folder_is_project_error(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "a.xml", "a")
    with _unsearchable(project.models_dir), pytest.raises(proj.ProjectError, match="cannot"):
        proj.add_model_file(project, src, check=None)
    assert project.models == []


@needs_posix_perms
def test_supported_model_paths_unreadable_folder_is_project_error(tmp_path: Path) -> None:
    folder = tmp_path / "pool"
    _fake_model(folder / "a.xml")
    locked = folder / "locked"
    _fake_model(locked / "b.xml")
    inner = _fake_model(tmp_path / "shut" / "c.xml")
    with _unsearchable(locked):
        with pytest.raises(proj.ProjectError, match="locked"):
            proj.supported_model_paths([folder])
        with pytest.raises(proj.ProjectError, match="locked"):
            proj.supported_model_paths([locked], recursive=False)
        flat, _ = proj.supported_model_paths([folder], recursive=False)
        assert [p.name for p in flat] == ["a.xml"], "a flat listing never enters the subfolder"
    with _unsearchable(inner.parent), pytest.raises(proj.ProjectError, match="cannot read"):
        proj.supported_model_paths([inner])


def test_ids_and_run_kinds_reject_trailing_newline(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=None)
    with pytest.raises(proj.ProjectError):
        proj.rename_model(project, "a", "abc\n")
    assert project.model("a").id == "a"
    with pytest.raises(proj.ProjectError, match="invalid run kind"):
        proj.new_run_dir(project, "search\n")
    assert list(project.runs_dir.iterdir()) == [project.inputs_dir]


def _two_models(tmp_path: Path) -> proj.Project:
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    return project


def test_taxonomy_rejects_duplicate_model_ids(tmp_path: Path) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    with pytest.raises(proj.ProjectError, match="duplicate.*'a'"):
        proj.write_run_taxonomy(project, run, ["a", "b", "a"])
    assert list(project.inputs_dir.iterdir()) == []


def test_taxonomy_rejects_abundance_for_unselected_model(tmp_path: Path) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    with pytest.raises(proj.ProjectError, match="not in this run.*'b'"):
        proj.write_run_taxonomy(project, run, ["a"], abundances={"a": 1.0, "b": 2.0})
    assert list(project.inputs_dir.iterdir()) == []


@pytest.mark.parametrize(
    "value",
    [0, 0.0, -1.0, float("nan"), float("inf"), -float("inf"), "abc", "0.5", None, True, 10**400],
)
def test_taxonomy_rejects_bad_abundances(tmp_path: Path, value: object) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    with pytest.raises(proj.ProjectError, match="abundance.*'a'.*finite.*greater than 0"):
        proj.write_run_taxonomy(project, run, ["a", "b"], abundances={"a": value})  # type: ignore[dict-item]
    assert list(project.inputs_dir.iterdir()) == []


def test_taxonomy_rehashes_files_so_a_stale_ok_flag_cannot_pass(tmp_path: Path) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    (project.root / project.model("a").file).write_text("edited after it was added")
    assert project.model("a").integrity == "ok", "nothing called verify_checksums"
    with pytest.raises(proj.ProjectError, match="'a' is not selectable.*changed since it was"):
        proj.write_run_taxonomy(project, run, ["a", "b"])
    assert project.model("a").integrity == "changed"
    assert list(project.inputs_dir.iterdir()) == []


def test_taxonomy_refuses_missing_file_and_reports_every_bad_model(tmp_path: Path) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    (project.root / project.model("a").file).write_text("edited")
    (project.root / project.model("b").file).unlink()
    with pytest.raises(proj.ProjectError) as info:
        proj.write_run_taxonomy(project, run, ["a", "b"])
    message = str(info.value)
    assert "'a' is not selectable" in message and "changed since it was added" in message
    assert "'b' is not selectable" in message and "file is missing" in message
    assert project.model("a").integrity == "changed"
    assert project.model("b").integrity == "missing"


def test_taxonomy_refreshes_a_stale_changed_flag_when_the_file_is_intact(tmp_path: Path) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    project.model("a").integrity = "changed"
    path = proj.write_run_taxonomy(project, run, ["a"])
    assert project.model("a").integrity == "ok"
    assert [r["id"] for r in csv.DictReader(path.open())] == ["a"]


def test_taxonomy_refuses_failed_pending_and_unknown_models(tmp_path: Path) -> None:
    project = _two_models(tmp_path)
    run = proj.new_run_dir(project, "community")
    project.model("a").status = "failed"
    project.model("b").status = "pending"
    with pytest.raises(proj.ProjectError, match="'a' is not selectable.*'failed'"):
        proj.write_run_taxonomy(project, run, ["a"])
    with pytest.raises(proj.ProjectError, match="'b' is not selectable.*'pending'"):
        proj.write_run_taxonomy(project, run, ["b"])
    with pytest.raises(proj.ProjectError, match="'zzz' is not selectable"):
        proj.write_run_taxonomy(project, run, ["zzz"])


def test_verify_checksums_treats_unreadable_file_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    monkeypatch.setattr(proj, "_sha256", _deny_write)
    assert proj.verify_checksums(project) == ["a"]
    assert project.model("a").integrity == "missing"


def test_unreadable_source_is_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "a.xml", "a")
    monkeypatch.setattr(proj, "_sha256", _deny_write)
    with pytest.raises(proj.ProjectError, match="cannot read.*disk full"):
        proj.add_model_file(project, src, check=None)
    csv_src = tmp_path / "d.csv"
    csv_src.write_text("exchange,uptake\n")
    with pytest.raises(proj.ProjectError, match="cannot read.*disk full"):
        proj.add_medium_file(project, csv_src)
    assert project.models == [] and project.media == []


def test_new_run_dir_mkdir_failure_is_project_error(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    shutil.rmtree(project.runs_dir)
    project.runs_dir.write_text("a file where the runs folder belongs")
    with pytest.raises(proj.ProjectError, match="cannot create run folder"):
        proj.new_run_dir(project, "search")


def test_write_run_taxonomy_write_failure_is_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    run = proj.new_run_dir(project, "search")
    monkeypatch.setattr(proj, "atomic_write_text", _deny_write)
    with pytest.raises(proj.ProjectError, match="cannot write run inputs"):
        proj.write_run_taxonomy(project, run, ["a"])
