from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    yield w
    w.close_project()


def _menu(w, title: str) -> list[str]:
    for action in w.menuBar().actions():
        if action.text().replace("&", "") == title:
            return [a.text() for a in action.menu().actions() if not a.isSeparator()]
    raise AssertionError(f"no {title} menu")


def test_standard_menus_and_shortcuts(window) -> None:
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert titles == ["File", "Edit", "View", "Analysis", "Window", "Help"]
    assert _menu(window, "File")[:4] == [
        "New Project…", "Open Project…", "Open Recent", "Close Project",
    ]
    assert "Add Models…" in _menu(window, "File")
    assert "Add Models from AGORA2…" in _menu(window, "File")
    assert window.add_models_action.shortcut().toString() == "Ctrl+Shift+A"
    assert window.run_action.shortcut().toString() == "Ctrl+R"
    assert window.toggle_inspector_action.shortcut().toString() == "Ctrl+Alt+I"
    analysis = _menu(window, "Analysis")
    assert analysis[:5] == [
        "Combination Search", "Gene Knockout", "Strain Growth & Ratio", "Host–Microbe", "Dynamics",
    ]
    assert analysis[-2:] == ["Run", "Cancel"]
    assert "Try Demo Run" in _menu(window, "Help")


def test_no_project_shows_welcome_and_dims_project_actions(window) -> None:
    assert window.pages.currentWidget() is window.welcome_page
    assert not window.add_models_action.isEnabled()
    assert not window.run_action.isEnabled()
    assert window.open_run_action.isEnabled()
    assert window.windowTitle() == "CMIG"


def test_open_project_shows_models_and_title(window, tmp_path: Path) -> None:
    make_project(tmp_path / "study", ["a", "b"])
    assert window.open_project(tmp_path / "study")
    assert window.windowTitle() == "study — CMIG"
    assert window.add_models_action.isEnabled()
    assert window.sidebar.topLevelItem(0).text(0) == "MODELS (2)"
    assert window.recent.paths()[0] == (tmp_path / "study").resolve()


def test_open_locked_or_corrupt_project_reports_on_welcome(window, tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "cmig-project.json").write_text("{broken")
    assert not window.open_project(bad)
    assert "not valid JSON" in window.welcome_message.text()
    assert window.pages.currentWidget() is window.welcome_page


def test_empty_project_shows_drop_hint(window, tmp_path: Path) -> None:
    make_project(tmp_path / "empty", [])
    window.open_project(tmp_path / "empty")
    assert window.pages.currentWidget() is window.empty_models_page


def test_selecting_analysis_switches_page_and_inspector(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("analyses", "host")
    assert window.pages.currentWidget() is window.host_view
    assert window.inspector.title_label.text() == "Host–Microbe"
    assert window.run_action.isEnabled()
    window.sidebar.select("analyses", "growth")
    assert window.pages.currentWidget() is window.search_view
    assert not window.run_action.isEnabled()


def test_selecting_model_updates_inspector(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["E_rectale"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("models", "E_rectale")
    assert window.inspector.title_label.text() == "Model · E_rectale"


def test_view_toggles(window) -> None:
    window.show()
    window.toggle_inspector_action.trigger()
    assert not window.inspector.isVisible()
    assert window.toggle_inspector_action.text() == "Show Inspector"
    window.toggle_inspector_action.trigger()
    assert window.inspector.isVisible()
    assert window.toggle_inspector_action.text() == "Hide Inspector"


def test_every_toolbar_command_is_also_in_a_menu(window) -> None:
    from PySide6.QtWidgets import QWidgetAction

    menu_actions = set()
    for top in window.menuBar().actions():
        menu_actions.update(top.menu().actions())
    commands = [a for a in window.workspace_toolbar.actions()
                if not a.isSeparator() and not isinstance(a, QWidgetAction)]
    assert {a.text() for a in commands} == {
        "Hide Sidebar", "Add Models…", "Hide Inspector", "Run",
    }
    for action in commands:
        assert action in menu_actions, action.text()


def test_korean_mode_opens_every_page_without_missing_strings(tmp_path: Path) -> None:
    from cmig.gui.sidebar import ANALYSES

    make_project(tmp_path / "ko", ["a"])
    w = build_main_window(lang="ko")
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "ko")
    for key, _label in ANALYSES:
        w.show_analysis(key)
    w.sidebar.select("models", "a")
    w.close_project()


@pytest.mark.parametrize("size", [(1280, 800), (1500, 950)])
def test_window_fits_target_sizes(window, tmp_path: Path, size: tuple[int, int]) -> None:
    make_project(tmp_path / "g", [f"m{i}" for i in range(12)])
    window.open_project(tmp_path / "g")
    window.resize(*size)
    window.show()
    for key in ("search", "host", "dynamics", "community", "medium", "sweep"):
        window.show_analysis(key)
        APP.processEvents()
        assert window.width() <= size[0] and window.height() <= size[1], key


# ── controller rulings and shell behaviour beyond the brief ───────────────────────────────
LOCK = ".cmig-project.lock"


def _disk_full(_project) -> None:
    from cmig.io.project import ProjectError

    raise ProjectError("disk full")


def test_reopening_the_open_project_keeps_it_open(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["a"])
    assert window.open_project(tmp_path / "s")
    window.show_analysis("host")
    project = window.session.project
    assert window.open_project(tmp_path / "s")  # no "already open in another window"
    # ...and not a silent close + reopen (that would cancel jobs and drop undo history)
    assert window.session.project is project
    assert window.pages.currentWidget() is window.host_view


def test_switching_projects_releases_the_first_lock(window, tmp_path: Path) -> None:
    make_project(tmp_path / "one", ["a"])
    make_project(tmp_path / "two", ["b"])
    assert window.open_project(tmp_path / "one")
    assert window.open_project(tmp_path / "two")
    assert window.session.project.name == "two"
    assert not (tmp_path / "one" / LOCK).exists()
    assert (tmp_path / "two" / LOCK).exists()


def test_close_with_a_failing_final_save_reports_and_unlocks(
    window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cmig.io import project as proj

    make_project(tmp_path / "s", ["a"])
    assert window.open_project(tmp_path / "s")
    monkeypatch.setattr(proj, "save_project", _disk_full)
    window.close_project()  # must not raise out of a Qt slot
    assert window.session.project is None
    assert not (tmp_path / "s" / LOCK).exists()
    assert "disk full" in window.statusBar().currentMessage()
    assert window.pages.currentWidget() is window.welcome_page


def test_save_failed_is_reported_in_the_status_bar(window) -> None:
    window.session.save_failed.emit("disk full")
    assert "disk full" in window.statusBar().currentMessage()


def test_cancel_shortcut_is_registered(window) -> None:
    assert window.cancel_job_action.shortcut().toString() == "Ctrl+."
    assert window.cancel_job_action in window.menuBar().actions()[3].menu().actions()


def test_sidebar_selection_survives_a_rebuild(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["a", "b"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("models", "b")
    window.session.refresh_runs()  # any session signal rebuilds MODELS / MEDIA / RUNS
    assert window.sidebar.selected_keys("models") == ["b"]
    assert window.sidebar.currentItem().data(0, 0x0100) == "b"


def test_opening_a_run_from_the_sidebar_shows_it_and_keeps_it_selected(
    window, tmp_path: Path
) -> None:
    import json

    project = make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    run = project.runs_dir / "dfba-20261013-120000"
    run.mkdir()
    (run / "dfba_summary.json").write_text(json.dumps({
        "status": "completed", "final_t": 1.0, "final_biomass": 0.2,
        "final_concentrations": {"glc": 1.0}, "warnings": [],
    }))
    window.session.refresh_runs()
    window.sidebar.select("runs", str(run))
    assert window.pages.currentWidget() is window.dynamics_view
    assert window.inspector.title_label.text().startswith("Run · ")
    assert "Artifact integrity" in window.inspector.details.toPlainText()
    assert window.sidebar.currentItem().data(0, 0x0100) == str(run)
    window._show_page(window.dynamics_view)  # e.g. a new dFBA result replaces this run
    assert window.sidebar.currentItem() is None  # so clicking the run again reopens it


def test_a_page_shown_elsewhere_lets_the_sidebar_item_be_clicked_again(
    window, tmp_path: Path
) -> None:
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("analyses", "host")
    window._show_page(window.search_view)  # e.g. a finished Search job shows its result
    assert not window.run_action.isEnabled()  # Run must not start Host from the Search page
    window.sidebar.select("analyses", "host")
    assert window.pages.currentWidget() is window.host_view
    assert window.run_action.isEnabled()


def test_menu_choice_is_reflected_in_the_sidebar(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    window.analysis_actions["sweep"].trigger()
    assert window.pages.currentWidget() is window.sweep_view
    assert window.sidebar.currentItem().data(0, 0x0100) == "sweep"


def test_media_lists_presets_but_not_their_provenance_table(window) -> None:
    media = window.sidebar.topLevelItem(1)
    keys = [media.child(i).data(0, 0x0100) for i in range(media.childCount())]
    assert "preset:western_diet" in keys
    assert not any("provenance" in key for key in keys)
    window.sidebar.select("media", "preset:western_diet")
    assert window.inspector.title_label.text() == "Medium · western_diet"
