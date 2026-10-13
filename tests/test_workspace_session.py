from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.project_session import (  # noqa: E402
    ProjectSession,
    RecentProjects,
    inspect_run,
    run_label,
)
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


def test_open_locks_and_close_releases(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    session = ProjectSession()
    events: list[str] = []
    session.opened.connect(lambda: events.append("opened"))
    session.closed.connect(lambda: events.append("closed"))
    session.open(tmp_path / "p")
    assert session.project is not None and len(session.project.models) == 2
    assert (tmp_path / "p" / ".cmig-project.lock").exists()
    other = ProjectSession()
    with pytest.raises(proj.ProjectError, match="already open"):
        other.open(tmp_path / "p")
    session.close()
    assert session.project is None
    assert not (tmp_path / "p" / ".cmig-project.lock").exists()
    assert events == ["opened", "closed"]


def test_remove_and_rename_are_undoable_and_saved(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "b", "c"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    session.remove_models(["a", "c"])
    assert [m.id for m in session.project.models] == ["b"]
    assert session.undo_stack.undoText() == "Remove 2 Models"
    assert [m.id for m in proj.open_project(tmp_path / "p").models] == ["b"]
    session.undo_stack.undo()
    assert [m.id for m in session.project.models] == ["a", "b", "c"]
    session.rename_model("b", "Bifido")
    assert session.undo_stack.undoText() == "Rename Model"
    session.undo_stack.undo()
    assert [m.id for m in session.project.models] == ["a", "b", "c"]
    with pytest.raises(proj.ProjectError):
        session.rename_model("a", "c")
    session.close()


def test_rename_and_undo_keep_remembered_selections(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    session.store_settings("search", {"models": ["a", "b"], "medium": "preset:western_diet"})
    session.store_settings("dynamics", {"models": ["b"]})
    session.rename_model("b", "Bifido")
    assert session.settings("search")["models"] == ["a", "Bifido"]
    assert session.settings("dynamics") == {"models": ["Bifido"]}
    saved = proj.open_project(tmp_path / "p").analysis_settings
    assert saved["dynamics"] == {"models": ["Bifido"]}, "saved together with the rename"
    session.undo_stack.undo()
    assert session.settings("search") == {"models": ["a", "b"], "medium": "preset:western_diet"}
    assert session.settings("dynamics") == {"models": ["b"]}
    assert proj.open_project(tmp_path / "p").analysis_settings["dynamics"] == {"models": ["b"]}
    session.undo_stack.redo()
    assert session.settings("dynamics") == {"models": ["Bifido"]}
    session.close()


def test_adding_models_and_media_is_undoable(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    project = session.project
    src = tmp_path / "new.xml"
    src.write_text("<sbml id='new'/>")
    entry = proj.add_model_file(
        proj.Project(project.root, project.name, project.created, list(project.models)),
        src, check=None,
    )
    session.add_entries([entry])
    assert [m.id for m in session.project.models] == ["a", "new"]
    assert session.undo_stack.undoText() == "Add Model"
    session.undo_stack.undo()
    assert [m.id for m in session.project.models] == ["a"]
    assert (project.root / entry.file).exists(), "undo keeps the copied file"
    medium_src = tmp_path / "diet.csv"
    medium_src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    medium = proj.add_medium_file(
        proj.Project(project.root, project.name, project.created, media=list(project.media)),
        medium_src,
    )
    session.add_medium(medium)
    assert session.undo_stack.undoText() == "Add Medium"
    session.undo_stack.undo()
    assert session.project.media == []
    session.close()


def test_runs_listing_newest_first_with_status(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    old = project.runs_dir / "search-20261001-090000"
    old.mkdir()
    (old / "search_summary.json").write_text('{"status": "failed", "top_ranked": []}')
    new = project.runs_dir / "search-20261013-103100"
    new.mkdir()
    (new / "search_summary.json").write_text('{"status": "ok", "targets": ["but"]}')
    os.utime(old, (1, 1))
    session = ProjectSession()
    session.open(tmp_path / "p")
    runs = session.runs()
    assert [r.name for r in runs] == [new.name, old.name]
    assert [r.status for r in runs] == ["ok", "failed"]
    assert runs[0].label == "Search · but · 10:31"
    assert all(r.path.parent.name == "runs" for r in runs)
    session.close()


def test_run_state_marker_lists_a_bad_ending_and_never_upgrades(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])

    def run(name: str, summary: str | None) -> Path:
        folder = project.runs_dir / name
        folder.mkdir()
        if summary is not None:
            (folder / "search_summary.json").write_text(summary)
        return folder

    bare = run("search-20261013-090000", None)
    claims_ok = run("search-20261013-090100", '{"status": "ok", "targets": ["but"]}')
    failed = run("search-20261013-090200", '{"status": "failed", "top_ranked": []}')
    fine = run("search-20261013-090300", '{"status": "ok", "targets": ["ac"]}')
    for folder, status in ((bare, "cancelled"), (claims_ok, "failed"), (failed, "cancelled")):
        proj.write_run_state(folder, status, "search_fixture")
    assert sorted(p.name for p in bare.iterdir()) == [], "nothing is written into the run folder"
    session = ProjectSession()
    session.open(tmp_path / "p")
    by_name = {r.name: r.status for r in session.runs()}
    assert by_name == {
        bare.name: "cancelled",      # an unknown folder is now known to be cancelled
        claims_ok.name: "failed",    # a marker that is worse than the summary wins
        failed.name: "failed",       # the summary's failure is not softened to cancelled
        fine.name: "ok",             # no marker, no change
    }
    session.close()


def test_run_state_marker_ignores_garbage_and_rejects_other_states(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    folder = project.runs_dir / "search-20261013-090000"
    folder.mkdir()
    (folder / "search_summary.json").write_text('{"status": "ok", "targets": ["but"]}')
    with pytest.raises(proj.ProjectError, match="failed.*cancelled"):
        proj.write_run_state(folder, "ok", "search_fixture")
    with pytest.raises(proj.ProjectError, match="does not exist"):
        proj.write_run_state(project.runs_dir / "gone", "failed", "search_fixture")
    for text in ("not json", "[]", '{"status": "ok"}', '{"status": 3}'):
        proj.run_state_path(folder).write_text(text)
        assert proj.read_run_state(folder) is None, text
    session = ProjectSession()
    session.open(tmp_path / "p")
    assert [r.status for r in session.runs()] == ["ok"], "a marker that says ok upgrades nothing"
    session.close()


def test_run_label_fallbacks() -> None:
    assert run_label("gene_ko_search", "gene-ko-20261013-091502", "") == "Gene KO · 09:15"
    assert run_label("unknown", "odd-name", "") == "odd-name"


def test_settings_round_trip(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    session.store_settings("search", {"models": ["a"]})
    session.close()
    session.open(tmp_path / "p")
    assert session.settings("search") == {"models": ["a"]}
    assert session.settings("host") == {}
    session.close()


def test_recent_projects_order_and_limit(tmp_path: Path) -> None:
    store = QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat)
    recent = RecentProjects(store)
    for i in range(12):
        recent.add(tmp_path / f"p{i}")
    recent.add(tmp_path / "p3")
    paths = recent.paths()
    assert paths[0] == (tmp_path / "p3").resolve()
    assert len(paths) == 10
    recent.clear()
    assert recent.paths() == []


def _disk_full(_project: object) -> None:
    raise proj.ProjectError("disk full")


def test_close_with_failing_save_still_closes_and_unlocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    events: list[str] = []
    session.closed.connect(lambda: events.append("closed"))
    session.open(tmp_path / "p")
    with monkeypatch.context() as patch:
        patch.setattr(proj, "save_project", _disk_full)
        with pytest.raises(proj.ProjectError, match="disk full"):
            session.close()
    assert session.project is None
    assert events == ["closed"]
    assert not (tmp_path / "p" / ".cmig-project.lock").exists()
    assert session.undo_stack.count() == 0


def test_close_reports_a_lock_that_cannot_be_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")

    def stuck(_self: proj.ProjectLock) -> None:
        raise PermissionError("read-only volume")

    with monkeypatch.context() as patch:
        patch.setattr(proj.ProjectLock, "release", stuck)
        with pytest.raises(proj.ProjectError, match="cannot remove project lock"):
            session.close()
    assert session.project is None


@pytest.mark.parametrize("how", ["open", "create"])
def test_failed_close_does_not_leak_the_new_projects_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    make_project(tmp_path / "p", ["a"])
    make_project(tmp_path / "q", ["b"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    target = tmp_path / "q" if how == "open" else tmp_path / "fresh"
    assert session.project is not None
    failing_root, real_save = session.project.root, proj.save_project

    def save_unless_new_project(project: proj.Project) -> None:
        if project.root == failing_root:  # only the old project's final save fails
            raise proj.ProjectError("disk full")
        real_save(project)

    with monkeypatch.context() as patch:
        patch.setattr(proj, "save_project", save_unless_new_project)
        with pytest.raises(proj.ProjectError, match="disk full"):
            if how == "open":
                session.open(target)
            else:
                session.create(target, None)
    assert session.project is None
    assert not (tmp_path / "p" / ".cmig-project.lock").exists()
    assert not (target / ".cmig-project.lock").exists()
    other = ProjectSession()  # the new project is free to open
    other.open(target)
    other.close()


def _prepare_change(session: ProjectSession, tmp_path: Path, op: str) -> object:
    assert session.project is not None
    project = session.project
    if op == "add_models":
        src = tmp_path / "new.xml"
        src.write_text("<sbml id='new'/>")
        scratch = proj.Project(project.root, project.name, project.created, list(project.models))
        entry = proj.add_model_file(scratch, src, check=None)
        return lambda: session.add_entries([entry])
    if op == "add_medium":
        src = tmp_path / "diet.csv"
        src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
        scratch = proj.Project(project.root, project.name, project.created, media=[])
        medium = proj.add_medium_file(scratch, src)
        return lambda: session.add_medium(medium)
    if op == "remove":
        return lambda: session.remove_models(["a"])
    return lambda: session.rename_model("a", "Alpha")


@pytest.mark.parametrize("op", ["remove", "rename", "add_models", "add_medium"])
def test_failed_save_rolls_back_and_keeps_the_stack_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str
) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    assert session.project is not None
    change = _prepare_change(session, tmp_path, op)
    assert callable(change)
    signals: list[str] = []
    session.models_changed.connect(lambda: signals.append("models"))
    session.media_changed.connect(lambda: signals.append("media"))
    before = session.project.project_file.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(proj, "save_project", _disk_full)
        with pytest.raises(proj.ProjectError, match="disk full"):
            change()
    assert [m.id for m in session.project.models] == ["a", "b"]
    assert session.project.media == []
    assert session.project.project_file.read_bytes() == before
    assert session.undo_stack.count() == 0
    assert signals == []
    change()  # the same change succeeds once saving works again
    assert session.undo_stack.count() == 1
    assert signals != []
    session.close()


@pytest.mark.parametrize("ids", [["b", "zzz"], ["b", "b"], ["zzz"]])
def test_remove_models_validates_ids_before_changing_anything(
    tmp_path: Path, ids: list[str]
) -> None:
    make_project(tmp_path / "p", ["a", "b", "c"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    assert session.project is not None
    before = session.project.project_file.read_bytes()
    with pytest.raises(proj.ProjectError):
        session.remove_models(ids)
    assert [m.id for m in session.project.models] == ["a", "b", "c"]
    assert session.project.project_file.read_bytes() == before
    assert session.undo_stack.count() == 0
    session.close()


def test_changes_without_an_open_project_raise_project_error(tmp_path: Path) -> None:
    session = ProjectSession()
    with pytest.raises(proj.ProjectError):
        session.remove_models(["a"])
    with pytest.raises(proj.ProjectError):
        session.rename_model("a", "b")
    assert session.undo_stack.count() == 0


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_failed_save_during_undo_or_redo_rolls_back_and_drops_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direction: str
) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    assert session.project is not None
    session.remove_models(["a"])
    if direction == "redo":
        session.undo_stack.undo()
    expected = ["b"] if direction == "undo" else ["a", "b"]
    failures: list[str] = []
    session.save_failed.connect(failures.append)
    with monkeypatch.context() as patch:
        patch.setattr(proj, "save_project", _disk_full)
        (session.undo_stack.undo if direction == "undo" else session.undo_stack.redo)()
    assert [m.id for m in session.project.models] == expected
    assert [m.id for m in proj.open_project(tmp_path / "p").models] == expected
    assert failures == ["disk full"]
    APP.processEvents()
    assert session.undo_stack.count() == 0, "stale history is dropped after a failed save"
    session.close()


def test_runs_listing_survives_a_missing_runs_folder(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    shutil.rmtree(project.runs_dir)
    assert session.runs() == []
    session.close()


def test_runs_listing_skips_vanished_and_unreadable_run_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path / "p", ["a"])
    good = project.runs_dir / "search-20261013-103100"
    good.mkdir()
    (good / "search_summary.json").write_text('{"status": "ok", "targets": ["but"]}')
    (project.runs_dir / "search-20261013-110000").mkdir()  # unreadable below
    session = ProjectSession()
    session.open(tmp_path / "p")
    real_iterdir, real_stat = Path.iterdir, Path.stat

    def iterdir(self: Path) -> Iterator[Path]:
        yield from real_iterdir(self)
        if self.name == "runs":
            yield self / "search-20261013-120000"  # listed, then gone before it is read

    def stat(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self.name == "search-20261013-110000":
            raise PermissionError("denied")
        return real_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(Path, "iterdir", iterdir)
        patch.setattr(Path, "stat", stat)
        runs = session.runs()
    assert [r.name for r in runs] == [good.name]
    session.close()


def test_inspect_run_of_a_vanished_dir_is_unreadable_not_an_error(tmp_path: Path) -> None:
    entry = inspect_run(tmp_path / "search-20261013-103100")
    assert entry.status == "unreadable"
    assert entry.mtime == 0.0
