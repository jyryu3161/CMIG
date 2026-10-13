from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.project_session import ProjectSession, RecentProjects, run_label  # noqa: E402
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
