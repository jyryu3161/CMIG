from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, textbook_sbml  # noqa: E402,F401
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "e_coli_core.xml"))
    proj.save_project(project)
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(project.root)
    w.show()
    deadline = time.time() + 20
    while not w._search_rows and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.05)
        w._poll_completed_jobs()
    yield w
    w.close_project()


def test_cmd_f_focuses_the_field(window) -> None:
    window.find_action.trigger()
    APP.processEvents()
    assert window.find_field.hasFocus()
    assert window.find_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Find)


def test_typing_lists_groups_and_return_opens_the_item(window) -> None:
    field = window.find_field
    field.setFocus()
    QTest.keyClicks(field, "pgi")
    assert field.popup.isVisible()
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert "Reactions" in texts
    assert any("PGI · e_coli_core" in t for t in texts)
    QTest.keyClick(field, Qt.Key.Key_Return)
    APP.processEvents()
    assert window.pages.currentWidget() is window.model_browser
    assert window.model_browser.reactions_tab.current_id() == "PGI"


def test_escape_closes_then_clears(window) -> None:
    field = window.find_field
    field.setFocus()
    QTest.keyClicks(field, "glc")
    QTest.keyClick(field, Qt.Key.Key_Escape)
    assert not field.popup.isVisible() and field.text() == "glc"
    QTest.keyClick(field, Qt.Key.Key_Escape)
    assert field.text() == ""


def test_media_are_found(window) -> None:
    field = window.find_field
    QTest.keyClicks(field, "western")
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert "Media" in texts
    assert any(t.strip() == "western_diet" for t in texts)


def test_a_switched_project_never_shows_the_previous_rows(window, tmp_path: Path) -> None:
    field = window.find_field
    QTest.keyClicks(field, "pgi")
    assert field.popup.isVisible()
    # A rows job still out for the first project when the second one opens.
    window._search_rows = {}
    window._refresh_search_rows()
    assert window._search_rows_job is not None
    other = proj.create_project(tmp_path / "q")
    proj.save_project(other)
    assert window.open_project(other.root)
    assert not field.popup.isVisible()
    deadline = time.time() + 20
    while window._search_rows_job is not None and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.05)
        window._poll_completed_jobs()
    assert window._search_rows == {}
    assert window._search_table().entities == {}
    field.clear()
    QTest.keyClicks(field, "pgi")
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert not any("PGI" in t for t in texts)


def test_closing_the_window_cancels_the_unlisted_jobs(window, monkeypatch) -> None:
    import threading

    release = threading.Event()

    def _wait(ctx):  # type: ignore[no-untyped-def]
        while not ctx.cancelled and not release.is_set():
            time.sleep(0.01)
        return {}

    window._index_job = window.runner.submit("index_check", _wait)
    window._index_job_kind = "check"
    window._search_rows_job = window.runner.submit("search_rows", _wait)
    cancelled: list[str] = []
    real_cancel = window.runner.cancel
    monkeypatch.setattr(window.runner, "cancel",
                        lambda jid: (cancelled.append(jid), real_cancel(jid))[1])
    try:
        window.close()
        assert window._index_job in cancelled and window._search_rows_job in cancelled
    finally:
        release.set()


def test_a_rebuilt_index_becomes_searchable(window) -> None:
    sha = window.session.project.models[0].sha256
    window._search_rows.pop(sha)
    window._search_unreadable.add(sha)  # e.g. read while the index file was corrupt
    assert window._search_table().unreadable == 1
    window._index_checked.add(sha)  # an index job rebuilt it
    window._index_changed()
    deadline = time.time() + 20
    while sha not in window._search_rows and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.05)
        window._poll_completed_jobs()
    assert sha in window._search_rows and window._search_table().unreadable == 0


def test_one_character_never_builds_the_table() -> None:
    from PySide6.QtWidgets import QWidget

    from cmig.gui.find import FindField, SearchTable

    calls: list[int] = []

    def source() -> SearchTable:
        calls.append(1)
        return SearchTable()

    host = QWidget()
    field = FindField(source, host)
    host.show()
    QTest.keyClicks(field, "a")
    assert calls == [] and not field.popup.isVisible()
    QTest.keyClicks(field, "c")
    assert calls == [1] and field.popup.isVisible()
    QTest.keyClick(field, Qt.Key.Key_Backspace)
    assert calls == [1] and not field.popup.isVisible()


def test_the_table_is_built_once_until_something_changes(window, monkeypatch) -> None:
    builds: list[int] = []
    real = window._build_search_table
    monkeypatch.setattr(window, "_build_search_table", lambda: (builds.append(1), real())[1])
    window._search_changed()
    QTest.keyClicks(window.find_field, "pgi")
    assert builds == [1]
    window.refresh_workspace()  # e.g. a run finished: the open list is redrawn from a new table
    assert builds == [1, 1]
    QTest.keyClick(window.find_field, Qt.Key.Key_Backspace)
    assert builds == [1, 1]


def test_focus_elsewhere_hides_the_list(window) -> None:
    window.activateWindow()
    field = window.find_field
    field.setFocus()
    APP.processEvents()
    QTest.keyClicks(field, "pgi")
    assert field.popup.isVisible()
    window.sidebar.setFocus()
    APP.processEvents()
    assert not field.popup.isVisible()


def test_resizing_the_window_hides_the_list(window) -> None:
    field = window.find_field
    QTest.keyClicks(field, "pgi")
    assert field.popup.isVisible()
    window.resize(window.width() + 40, window.height())  # it may already be at its minimum
    APP.processEvents()
    assert not field.popup.isVisible()


def test_a_failed_rows_job_marks_the_model_unsearchable_once(window, monkeypatch) -> None:
    from cmig.io import model_index

    def broken(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk gone")

    sha = window.session.project.models[0].sha256
    window._search_rows.pop(sha)
    monkeypatch.setattr(model_index, "load_index", broken)
    window._refresh_search_rows()
    deadline = time.time() + 20
    while window._search_rows_job is not None and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.05)
        window._poll_completed_jobs()
    assert sha in window._search_unreadable
    window._poll_completed_jobs()
    assert window._search_rows_job is None  # not submitted again
    assert window._search_table().unreadable == 1


def test_opening_a_run_selects_its_row_and_opens_it_once(window, monkeypatch) -> None:
    run_dir = window.session.require().runs_dir / "dfba-20261014-101010"
    run_dir.mkdir()
    window.refresh_workspace()
    opened: list[Path] = []
    monkeypatch.setattr(window, "_open_run_entry", lambda path: opened.append(Path(path)))
    (row,) = [r for g in __import__("cmig.gui.find", fromlist=["find"]).find(
        window._search_table(), "dfba") if g.kind == "run" for r in g.rows]
    window._find_activated("run", row.key, None)
    assert window._sidebar_current() == ("runs", row.key)
    assert opened == [run_dir]
    window._find_activated("run", row.key, None)  # already selected: still opens, once
    assert opened == [run_dir, run_dir]


def test_an_open_list_shows_rows_that_arrive(window) -> None:
    sha = window.session.project.models[0].sha256
    window._search_rows.pop(sha)
    window._search_changed()
    field = window.find_field
    QTest.keyClicks(field, "pgi")
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert not any("PGI ·" in t for t in texts) and "1 model still indexing" in texts
    window._refresh_search_rows()
    deadline = time.time() + 20
    while sha not in window._search_rows and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.05)
        window._poll_completed_jobs()
    texts = [field.popup.item(i).text() for i in range(field.popup.count())]
    assert field.popup.isVisible() and any("PGI · e_coli_core" in t for t in texts)


def test_a_long_row_is_shortened_not_scrolled_sideways() -> None:
    from PySide6.QtWidgets import QWidget

    from cmig.gui.find import FindField, build_table

    name = "D-gluconate transport via proton symport, reversible " * 4
    table = build_table([("iHN637", "iHN637.xml")],
                        {"iHN637": [("reaction", "GLCNt2r", name)]}, [], [])
    host = QWidget()
    host.resize(1280, 800)
    field = FindField(lambda: table, host)
    host.show()
    QTest.keyClicks(field, "glcn")
    APP.processEvents()
    row = next(field.popup.item(i) for i in range(field.popup.count())
               if field.popup.item(i).data(Qt.ItemDataRole.UserRole) is not None)
    assert field.popup.horizontalScrollBar().maximum() == 0
    assert row.text().startswith("   GLCNt2r · iHN637") and row.text().endswith("…")
    assert row.toolTip() == row.data(Qt.ItemDataRole.UserRole).text  # all of it
