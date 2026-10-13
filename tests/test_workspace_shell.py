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


def test_new_analysis_button_leaves_room_for_its_menu_arrow(window) -> None:
    from PySide6.QtWidgets import QToolButton

    button = next(
        b for b in window.workspace_toolbar.findChildren(QToolButton) if b.text() == "New Analysis"
    )
    # The arrow is drawn over the text's last letters unless the button is wider than its text.
    assert button.minimumWidth() > button.fontMetrics().horizontalAdvance(button.text())


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


# ── fix round 1: overlays reachable, exchanges off the GUI thread, activity opens ─────────
def _wait_for(window, condition, timeout: float = 10.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        window._poll_completed_jobs()
        APP.processEvents()
        time.sleep(0.01)
    window._poll_completed_jobs()
    assert condition()


def _exchange_texts(window) -> list[str]:
    listing = window.inspector.exchange_list
    return [listing.item(i).text() for i in range(listing.count())]


def _profile_overlay_shown(window) -> bool:
    return (window.pages.currentWidget() is window.community_result_page
            and window.community_result_page.currentWidget() is window.profile_view
            and window.profile_view.net_chart.delta_active
            and not window.profile_view.delta_note.isHidden())


def test_compare_runs_overlay_is_shown_on_profile(window, tmp_path: Path) -> None:
    from cmig.core.engine import SolveResult
    from cmig.core.interactions import build_tidy

    def result(growth: float, ac: float) -> SolveResult:
        return SolveResult(
            objective=growth, member_growth={"A": growth}, abundances={"A": 1.0},
            external_exchange={"ac": ac}, member_exchange={"A": {"ac": ac}},
            status="optimal", flux_report_status="full", growth_solver="gurobi",
            flux_solver="gurobi", members=["A"],
        )

    build_tidy(result(0.5, 5.0)).write(tmp_path / "a")
    build_tidy(result(0.8, 2.0)).write(tmp_path / "b")
    window.show_analysis("compare")
    window.scenario_compare.run_a_input.setText(str(tmp_path / "a"))
    window.scenario_compare.run_b_input.setText(str(tmp_path / "b"))
    window.run_scenario_compare()
    assert _profile_overlay_shown(window)


def _fake_sandbox_engine(monkeypatch: pytest.MonkeyPatch, gate=None) -> list[bool]:
    """Patch the sandbox solve; returns the list of `commit` flags it was called with."""
    from types import SimpleNamespace

    import cmig.service
    from cmig.core.delta import DeltaResult, MetaboliteDelta

    calls: list[bool] = []

    class FakeEngineService:
        def sandbox_fixture(self, *, reaction_id, lower, upper, commit, out_dir):
            calls.append(commit)
            if gate is not None:
                assert gate.wait(10)
            return SimpleNamespace(delta=DeltaResult([MetaboliteDelta("ac", 1.0, 2.0, 1.0)],
                                                     [], [], 0.0),
                                   run_hash="commithash" if commit else None)

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)
    return calls


def _sandbox_with_bound(window):
    window.show_analysis("sandbox")
    view = window.sandbox_view
    view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    view._debounce.stop()  # these tests press the buttons themselves
    return view


def test_sandbox_overlay_is_shown_on_profile(window, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_sandbox_engine(monkeypatch)
    _sandbox_with_bound(window).preview_btn.click()
    _wait_for(window, lambda: not window._sandbox_jobs)
    assert _profile_overlay_shown(window)


def test_sandbox_commit_shows_profile(
    window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QFileDialog

    calls = _fake_sandbox_engine(monkeypatch)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(tmp_path))
    _sandbox_with_bound(window).commit_btn.click()
    _wait_for(window, lambda: not window._sandbox_jobs)
    assert calls == [True]
    assert _profile_overlay_shown(window)


def test_auto_preview_after_a_bound_edit_stays_on_the_sandbox_page(
    window, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    calls = _fake_sandbox_engine(monkeypatch)
    window.show_analysis("sandbox")
    view = window.sandbox_view
    view._debounce.setInterval(20)
    loop = QEventLoop()
    view._debounce.timeout.connect(loop.quit)
    QTimer.singleShot(2000, loop.quit)
    view.add_bound("EX_glc__D_e", -1.0, 1000.0)  # an edit arms the debounced preview
    loop.exec()
    _wait_for(window, lambda: bool(calls) and not window._sandbox_jobs)
    assert calls == [False]
    assert window.pages.currentWidget() is view  # the delta table and its warning stay visible
    assert "preview" in view.status.text()
    assert window.profile_view.net_chart.delta_active  # Profile still carries the overlay


def test_auto_preview_waits_for_the_solve_in_flight_then_follows_the_latest_bound(
    window, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    import cmig.service

    gate = threading.Event()
    calls = _fake_sandbox_engine(monkeypatch, gate)
    fake = cmig.service.EngineService  # the fake the helper installed
    lowers: list[float] = []
    solve = fake.sandbox_fixture

    def recording(self, *, reaction_id, lower, upper, commit, out_dir):
        lowers.append(lower)
        return solve(self, reaction_id=reaction_id, lower=lower, upper=upper,
                     commit=commit, out_dir=out_dir)

    monkeypatch.setattr(fake, "sandbox_fixture", recording)
    view = _sandbox_with_bound(window)
    view._debounce.setInterval(60_000)  # these tests fire the debounce themselves
    view.auto_preview_requested.emit()  # the debounced preview starts a solve, held on the gate
    (first,) = window._sandbox_jobs
    view.bound_table.item(0, 1).setText("-2.0")  # another bound edit while it is in flight
    view._debounce.stop()
    view.auto_preview_requested.emit()  # its debounce expires: dropped, but re-armed
    assert list(window._sandbox_jobs) == [first], "still the one job"
    assert view._debounce.isActive(), "the preview is postponed, not lost"
    gate.set()
    _wait_for(window, lambda: not window._sandbox_jobs)
    assert calls == [False], "the engine ran once"
    assert view.preview_btn.isEnabled()
    assert "table has changed" in view.status.text(), "the first delta says it is stale"
    view._debounce.stop()
    view.auto_preview_requested.emit()  # the re-armed debounce expires with the job done
    _wait_for(window, lambda: len(calls) == 2 and not window._sandbox_jobs)
    assert calls == [False, False]
    assert lowers == [-1.0, -2.0], "the second preview is for the latest bound"
    assert "table has changed" not in view.status.text()


def test_explicit_preview_does_not_leave_a_cell_being_edited(
    window, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from PySide6.QtWidgets import QAbstractItemView

    gate = threading.Event()
    _fake_sandbox_engine(monkeypatch, gate)
    window.show()
    view = _sandbox_with_bound(window)
    view.preview_btn.click()
    view.bound_table.editItem(view.bound_table.item(0, 1))  # the user starts typing a bound
    assert view.bound_table.state() == QAbstractItemView.State.EditingState
    gate.set()
    _wait_for(window, lambda: not window._sandbox_jobs)
    assert window.pages.currentWidget() is view
    assert view.bound_table.state() == QAbstractItemView.State.EditingState


def test_starting_a_job_opens_the_activity_pane(window) -> None:
    assert window.activity.isHidden()
    window.submit_job("calc", lambda ctx: 21 * 2)
    assert not window.activity.isHidden()
    assert window.toggle_activity_action.text() == "Hide Activity"


def test_model_exchanges_load_in_the_background(
    window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    import time
    from types import SimpleNamespace

    import cmig.io.model_import as model_import

    gate = threading.Event()
    calls: list[Path] = []

    def slow_import(path):
        calls.append(path)
        assert gate.wait(10)
        return SimpleNamespace(exchanges=["EX_ac_e", "EX_but_e"])

    monkeypatch.setattr(model_import, "import_model", slow_import)
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    started = time.monotonic()
    window.sidebar.select("models", "a")
    assert time.monotonic() - started < 1.0  # selection does not wait for the parse
    assert _exchange_texts(window) == ["Loading exchanges…"]
    assert window.activity.isHidden()  # a background lookup does not pop the pane open
    gate.set()
    _wait_for(window, lambda: not window._exchange_jobs)
    assert _exchange_texts(window) == ["EX_ac_e", "EX_but_e"]
    window.sidebar.select("media", "preset:western_diet")
    window.sidebar.select("models", "a")
    assert _exchange_texts(window) == ["EX_ac_e", "EX_but_e"]  # cached by checksum
    assert len(calls) == 1


def test_model_exchanges_fill_only_the_model_still_shown(
    window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from types import SimpleNamespace

    import cmig.io.model_import as model_import

    gate = threading.Event()
    monkeypatch.setattr(model_import, "import_model",
                        lambda path: gate.wait(10) and SimpleNamespace(exchanges=["EX_ac_e"]))
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("models", "a")
    window.sidebar.select("media", "preset:western_diet")  # the user moved on
    gate.set()
    _wait_for(window, lambda: not window._exchange_jobs)
    assert window.inspector.title_label.text() == "Medium · western_diet"


def test_failed_exchange_lookup_is_shown_and_retried(
    window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cmig.io.model_import as model_import

    attempts: list[Path] = []

    def broken_import(path):
        attempts.append(path)
        raise ValueError("not a model")

    monkeypatch.setattr(model_import, "import_model", broken_import)
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("models", "a")
    _wait_for(window, lambda: not window._exchange_jobs)
    [note] = _exchange_texts(window)
    assert note.startswith("Exchange list unavailable:") and "not a model" in note
    window.sidebar.select("media", "preset:western_diet")
    window.sidebar.select("models", "a")
    _wait_for(window, lambda: not window._exchange_jobs)
    assert len(attempts) == 2  # a failure is not cached
