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
