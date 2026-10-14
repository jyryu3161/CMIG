from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget  # noqa: E402

from cmig.gui.analysis_page import (  # noqa: E402
    FLUX_LEGEND,
    is_failed_status,
    mark_computed_headers,
    paint_computed,
)
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.builder import read_only_item  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _accent() -> QColor:
    return QApplication.palette().color(QPalette.ColorRole.Accent)


def _fg(table: QTableWidget, row: int, col: int):  # type: ignore[no-untyped-def]
    return table.item(row, col).data(Qt.ItemDataRole.ForegroundRole)


def test_paint_computed_rules() -> None:
    table = QTableWidget(3, 3)
    table.setHorizontalHeaderLabels(["Name", "Flux", "Status"])
    rows = [("a", "1.5", "optimal"), ("b", "—", "optimal"), ("c", "2.0", "failed")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.setItem(r, c, read_only_item(text))
    fixed = read_only_item("9.9")
    fixed.setForeground(QColor("#d62728"))
    table.setItem(0, 0, fixed)
    mark_computed_headers(table, [1])
    paint_computed(table, [0, 1], status_column=2)
    assert _fg(table, 0, 1).color() == _accent()
    assert _fg(table, 0, 0).color() == QColor("#d62728"), "an explicit colour is kept"
    assert _fg(table, 1, 1) is None, "a missing value is not painted as a value"
    assert _fg(table, 2, 1) is None, "a failed row is never painted"
    assert "Computed by CMIG" in table.horizontalHeaderItem(1).toolTip()


def test_only_numbers_and_numeric_ranges_are_painted() -> None:
    table = QTableWidget(8, 2)
    table.setHorizontalHeaderLabels(["Value", "Status"])
    rows = [("1.2e-3", "optimal"), ("[0.1, 2]", "optimal"), ("0.1..2", "optimal"),
            ("-0.5", "optimal"), ("biomass=unknown", "optimal"), ("not_run", "optimal"),
            ("1.5", "completed ⚠ see warnings"), ("2.5", "unevaluated")]
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.setItem(r, c, read_only_item(text))
    paint_computed(table, [0], status_column=1)
    painted = [_fg(table, r, 0) is not None for r in range(len(rows))]
    assert painted == [True, True, True, True, False, False, False, False]


@pytest.mark.parametrize(("text", "failed"), [("failed", True), ("Infeasible", True),
                                              ("non-viable", True), ("optimal", False),
                                              ("ok", False), ("timeout", True),
                                              ("time_limit", True), ("not_run", True),
                                              ("no_solution", True), ("unbounded", True),
                                              ("completed ⚠ see warnings", True)])
def test_is_failed_status(text: str, failed: bool) -> None:
    assert is_failed_status(text) is failed


def test_search_results_paint_computed_columns() -> None:
    w = build_main_window()
    panel = w.search_view.results_panel
    panel.load_summary({"status": "ok", "strategy": "exhaustive", "target": "but",
                        "top_ranked": [{"members": ["a"], "score": 1.0, "target_flux": 2.0,
                                        "community_growth": 0.4, "status": "optimal"}]})
    assert _fg(panel.table, 0, 2).color() == _accent()
    assert _fg(panel.table, 0, 0) is None
    assert "Computed by CMIG" in panel.table.horizontalHeaderItem(3).toolTip()


def test_flux_legend_next_to_flux_tables() -> None:
    w = build_main_window()
    for widget in (w.profile_view, w.host_view):
        labels = [label.text() for label in widget.findChildren(QLabel)]
        assert FLUX_LEGEND in labels


def test_status_bar_names_the_last_finished_run(tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    try:
        monkeypatch.setattr("cmig.cli.main.main", lambda argv: 2)
        w.strain_growth_page.model_picker.set_selected(["a"])
        assert w.run_strain_growth_report()
        deadline = time.time() + 10
        while not w.last_run_button.text() and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.02)
            w._poll_completed_jobs()
        text = w.last_run_button.text()
        assert text.startswith("✗ Strain Growth · strain-growth-")
        assert "rc=2" in text
        w.show_analysis("search")
        w.last_run_button.click()
        assert w.pages.currentWidget() is w.strain_growth_page
    finally:
        w.close_project()


def test_failure_reason_reads_a_serialized_diagnostic() -> None:
    raw = json.dumps({"code": "E1", "message": "RuntimeError: first line\nsecond line"})
    assert build_main_window()._failure_reason(raw) == "first line"
    assert build_main_window()._failure_reason("plain text\nmore") == "plain text"
    assert build_main_window()._failure_reason("") == ""


def test_closing_the_project_clears_the_last_run(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    run = tmp_path / "p" / "runs" / "strain-growth-20260101-000000"
    run.mkdir(parents=True)
    # no run yet: no button (an empty one draws as a bare box in the native status bar)
    assert w.last_run_button.isHidden()
    w._show_last_run(run, "boom")
    assert w.last_run_button.text()
    assert not w.last_run_button.isHidden()
    w.close_project()
    assert w.last_run_button.text() == ""
    assert w.last_run_button.isHidden()
    assert w._last_run_dir is None


def _wait_for(predicate, w, seconds: float = 10.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.time() + seconds
    while not predicate() and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
        w._poll_completed_jobs()
    return bool(predicate())


def test_last_run_button_is_visible_beside_a_status_message(tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    w.show()
    assert w.open_project(tmp_path / "p")
    try:
        w.statusBar().showMessage("Ready")
        monkeypatch.setattr("cmig.cli.main.main", lambda argv: 2)
        w.strain_growth_page.model_picker.set_selected(["a"])
        assert w.run_strain_growth_report()
        assert _wait_for(lambda: bool(w.last_run_button.text()), w)
        APP.processEvents()
        assert w.last_run_button.isVisible()
        tip = w.last_run_button.toolTip()
        assert "rc=2" in tip and "strain-growth-" in tip, "the tooltip has the reason and path"
    finally:
        w.close_project()


def test_a_closed_projects_run_is_not_shown_in_the_next_project(
    tmp_path: Path, monkeypatch
) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    make_project(tmp_path / "q", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    release = threading.Event()

    def slow_main(argv: list[str]) -> int:
        release.wait(10)
        return 2

    try:
        monkeypatch.setattr("cmig.cli.main.main", slow_main)
        w.strain_growth_page.model_picker.set_selected(["a"])
        assert w.run_strain_growth_report()
        assert w._job_runs, "the job is in flight"
        monkeypatch.setattr(w, "_confirm_closing_with_jobs", lambda: True)
        assert w.open_project(tmp_path / "q")
        release.set()
        assert _wait_for(lambda: not w._job_runs, w)
        w._poll_completed_jobs()
        assert w.last_run_button.text() == ""
        assert w._last_run_dir is None
        w.show_analysis("search")
        w.last_run_button.click()
        assert w.pages.currentWidget() is not w.strain_growth_page
    finally:
        release.set()
        w.close_project()
