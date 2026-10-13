from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.project_session import RunEntry  # noqa: E402
from cmig.gui.sidebar import (  # noqa: E402
    ANALYSES,
    WorkspaceSidebar,
    droppable_paths,
    status_symbol,
)
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _group_texts(sidebar: WorkspaceSidebar) -> list[str]:
    return [sidebar.topLevelItem(i).text(0) for i in range(sidebar.topLevelItemCount())]


def test_groups_and_models_with_status(tmp_path: Path) -> None:
    statuses = {"b": "warning", "c": "failed"}
    project = make_project(tmp_path / "p", ["a", "b", "c"], statuses=statuses)
    sidebar = WorkspaceSidebar()
    sidebar.set_models(project.models, pending=["loading.xml"])
    assert _group_texts(sidebar) == ["MODELS (3)", "MEDIA", "ANALYSES", "RUNS"]
    models = sidebar.topLevelItem(0)
    texts = [models.child(i).text(0) for i in range(models.childCount())]
    assert texts == ["✓ a", "⚠ b", "✗ c", "… loading.xml"]


def test_status_symbols() -> None:
    assert status_symbol("ok") == "✓"
    assert status_symbol("ok", "changed") == "⚠"
    assert status_symbol("degraded") == "⚠"
    assert status_symbol("failed") == "✗"
    assert status_symbol("cancelled") == "⊘"
    assert status_symbol("pending") == "…"
    assert status_symbol("weird") == "?"


def test_status_symbol_failure_beats_integrity_warning() -> None:
    for integrity in ("changed", "missing"):
        assert status_symbol("failed", integrity) == "✗"
        assert status_symbol("unreadable", integrity) == "✗"
        assert status_symbol("ok", integrity) == "⚠"
        assert status_symbol("pending", integrity) == "⚠"
    assert status_symbol("pending", "ok") == "…"


def test_model_tooltip_states_integrity_problem(tmp_path: Path) -> None:
    project = make_project(
        tmp_path / "p", ["a", "b", "c", "d"], statuses={"c": "failed", "d": "failed"}
    )
    a, b, c, d = project.models
    a.integrity = "changed"
    b.integrity = "missing"
    c.integrity = "changed"
    c.error = "parse error"
    d.error = "bad stoichiometry"
    sidebar = WorkspaceSidebar()
    sidebar.set_models(project.models, pending=[])
    group = sidebar.topLevelItem(0)
    tips = [group.child(i).toolTip(0) for i in range(group.childCount())]
    assert tips[0] == "File changed since it was added"
    assert tips[1] == "File missing from the project"
    assert tips[2].startswith("File changed since it was added") and "parse error" in tips[2]
    assert tips[3] == "bad stoichiometry"
    assert group.child(2).text(0) == "✗ c", "a failed model stays failed when its file also changed"


def test_analyses_listed_with_separator_and_selection_signal() -> None:
    sidebar = WorkspaceSidebar()
    seen: list[tuple[str, str]] = []
    sidebar.selection_changed.connect(lambda g, k: seen.append((g, k)))
    group = sidebar.topLevelItem(2)
    keys = [group.child(i).data(0, Qt.ItemDataRole.UserRole) for i in range(group.childCount())]
    assert keys[:5] == ["search", "gene_ko", "strain_growth", "ratio_impact", "community"]
    assert None in keys, "a disabled separator row follows the primary analyses"
    sidebar.select("analyses", "host")
    assert seen[-1] == ("analyses", "host")
    assert [k for k, _ in ANALYSES][-1] == "compare"


def test_runs_and_multi_select(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    sidebar = WorkspaceSidebar()
    sidebar.set_models(project.models, pending=[])
    runs = [RunEntry(tmp_path / "r1", "r1", "search", "ok", "Search · but · 10:31", 2.0),
            RunEntry(tmp_path / "r2", "r2", "search", "failed", "Search · ac · 09:00", 1.0)]
    sidebar.set_runs(runs, external=[])
    run_group = sidebar.topLevelItem(3)
    assert run_group.child(0).text(0) == "✓ Search · but · 10:31"
    assert run_group.child(1).text(0) == "✗ Search · ac · 09:00"
    models = sidebar.topLevelItem(0)
    models.child(0).setSelected(True)
    models.child(1).setSelected(True)
    assert sidebar.selected_keys("models") == ["a", "b"]


def test_drop_filters_unsupported_and_reports_skipped(tmp_path: Path) -> None:
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "a.xml").write_text("<sbml/>")
    (pool / "readme.txt").write_text("x")
    (pool / ".DS_Store").write_text("x")
    # A folder is taken as dropped; the import job searches it (and counts the skipped files).
    paths, skipped = droppable_paths([QUrl.fromLocalFile(str(pool))])
    assert paths == [pool] and skipped == 0
    paths, skipped = droppable_paths(
        [QUrl.fromLocalFile(str(pool / name)) for name in ("a.xml", "readme.txt", ".DS_Store")]
    )
    assert paths == [pool / "a.xml"] and skipped == 2

    sidebar = WorkspaceSidebar()
    received: list[list[Path]] = []
    sidebar.files_dropped.connect(lambda files: received.append(files))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(pool / "readme.txt"))])
    enter = QDragEnterEvent(sidebar.rect().center(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    sidebar.dragEnterEvent(enter)
    assert not enter.isAccepted(), "a drop with no model file is not accepted"
    mime.setUrls([QUrl.fromLocalFile(str(pool))])
    drop = QDropEvent(QPointF(sidebar.rect().center()), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    sidebar.dropEvent(drop)
    assert received == [[pool]]


def _drag_events(
    sidebar: WorkspaceSidebar, *paths: Path
) -> tuple[QMimeData, QDragEnterEvent, QDragMoveEvent, QDropEvent]:
    """Synthetic events plus their mime data (events do not own it: the caller must keep it)."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    args = (Qt.DropAction.CopyAction, mime, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    center = sidebar.rect().center()
    return (
        mime,
        QDragEnterEvent(center, *args),
        QDragMoveEvent(center, *args),
        QDropEvent(QPointF(center), *args),
    )


def test_move_keeps_a_rejected_enter_rejected(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("x")
    sidebar = WorkspaceSidebar()
    _mime, enter, move, _drop = _drag_events(sidebar, tmp_path / "readme.txt")
    sidebar.dragEnterEvent(enter)
    sidebar.dragMoveEvent(move)
    assert not enter.isAccepted()
    assert not move.isAccepted(), "a move must not re-accept a drag the enter rejected"


def test_move_accepts_a_supported_drag(tmp_path: Path) -> None:
    (tmp_path / "a.xml").write_text("<sbml/>")
    sidebar = WorkspaceSidebar()
    _mime, enter, move, _drop = _drag_events(sidebar, tmp_path / "a.xml")
    sidebar.dragEnterEvent(enter)
    sidebar.dragMoveEvent(move)
    assert enter.isAccepted() and move.isAccepted()


def test_drop_of_only_unsupported_items_emits_nothing(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("x")
    sidebar = WorkspaceSidebar()
    received: list[list[Path]] = []
    sidebar.files_dropped.connect(lambda files: received.append(files))
    _mime, _enter, _move, drop = _drag_events(sidebar, tmp_path / "readme.txt")
    sidebar.dropEvent(drop)
    assert received == [] and not drop.isAccepted()


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions enforced for this user",
)
def test_drag_of_unreadable_folder_is_taken_without_reading_it(tmp_path: Path) -> None:
    """The folder is not read while dragging; the import job reports that it cannot be read."""
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "a.xml").write_text("<sbml/>")
    sidebar = WorkspaceSidebar()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(locked))])
    enter = QDragEnterEvent(sidebar.rect().center(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    locked.chmod(0)
    try:
        assert droppable_paths([QUrl.fromLocalFile(str(locked))]) == ([locked], 0)
        sidebar.dragEnterEvent(enter)  # raises nothing
    finally:
        locked.chmod(0o700)
    assert enter.isAccepted()


def _no_scanning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything lists a folder or parses a JSON file."""
    import cmig.core.model_pool
    import cmig.gui.sidebar

    def refuse(*_args, **_kwargs):
        raise AssertionError("a drag must not scan folders or parse model files")

    for module, name in ((proj, "supported_model_paths"), (proj, "_files_under"),
                         (cmig.gui.sidebar, "supported_model_paths"),
                         (cmig.core.model_pool, "is_supported_model_file"),
                         (cmig.core.model_pool, "_is_cobra_json_candidate")):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, refuse)


def test_drag_enter_on_a_folder_or_json_does_not_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = tmp_path / "pool"
    (pool / "deep").mkdir(parents=True)
    (pool / "deep" / "m.json").write_text('{"reactions": [], "metabolites": []}')
    (tmp_path / "x.json").write_text("{}")
    _no_scanning(monkeypatch)
    sidebar = WorkspaceSidebar()
    received: list[list[Path]] = []
    sidebar.files_dropped.connect(received.append)
    _mime, enter, move, drop = _drag_events(sidebar, pool, tmp_path / "x.json")
    sidebar.dragEnterEvent(enter)
    sidebar.dragMoveEvent(move)
    sidebar.dropEvent(drop)
    assert enter.isAccepted() and move.isAccepted() and drop.isAccepted()
    assert received == [[pool, tmp_path / "x.json"]]


def test_context_request_uses_selection_or_clicked_row(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b", "c"])
    sidebar = WorkspaceSidebar()
    sidebar.resize(300, 400)
    sidebar.set_models(project.models, pending=[])
    sidebar.show()
    APP.processEvents()
    seen: list[tuple[str, list[str]]] = []
    sidebar.context_requested.connect(lambda g, k: seen.append((g, k)))
    models = sidebar.topLevelItem(0)
    models.child(0).setSelected(True)
    models.child(1).setSelected(True)
    sidebar.customContextMenuRequested.emit(sidebar.visualItemRect(models.child(0)).center())
    assert seen[-1] == ("models", ["a", "b"])
    sidebar.clearSelection()
    sidebar.customContextMenuRequested.emit(sidebar.visualItemRect(models.child(2)).center())
    assert seen[-1] == ("models", ["c"])
    n = len(seen)
    sidebar.customContextMenuRequested.emit(sidebar.visualItemRect(models).center())
    assert len(seen) == n, "a group header row opens no context menu"


def test_media_presets_and_user(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    entry = proj.add_medium_file(project, src)
    sidebar = WorkspaceSidebar()
    sidebar.set_media(["western", "high_fiber"], [entry])
    media = sidebar.topLevelItem(1)
    keys = [media.child(i).data(0, Qt.ItemDataRole.UserRole) for i in range(media.childCount())]
    assert keys == ["preset:western", "preset:high_fiber", "medium:diet"]


def test_medium_with_changed_file_shows_warning_and_reason(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    entry = proj.add_medium_file(project, src)
    entry.integrity = "changed"
    sidebar = WorkspaceSidebar()
    sidebar.set_media([], [entry])
    item = sidebar.topLevelItem(1).child(0)
    assert item.text(0) == "⚠ diet"
    assert item.toolTip(0) == "File changed since it was added"
