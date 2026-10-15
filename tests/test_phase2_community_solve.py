from __future__ import annotations

import csv
import os
import time
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
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    yield w, calls
    w.close_project()


def _rows(view) -> list[tuple[str, str]]:
    return [(view.table.item(r, 0).text(), view.table.item(r, 1).text())
            for r in range(view.table.rowCount())]


def test_member_table_mirrors_the_picker(window) -> None:
    w, _calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    assert _rows(view) == [("a", "1"), ("b", "1")]
    view.set_abundance("a", 0.25)
    view.model_picker.set_selected(["a", "b", "c"])
    assert _rows(view) == [("a", "0.25"), ("b", "1"), ("c", "1")]
    view.model_picker.set_selected(["b", "c"])
    view.model_picker.set_selected(["a", "b", "c"])
    assert _rows(view)[0] == ("a", "1"), "a re-added member starts at 1 again"
    assert not hasattr(view, "add_member_btn")


def test_member_names_are_read_only(window) -> None:
    from PySide6.QtCore import Qt

    w, _calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a"])
    assert not view.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable
    assert view.table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable


def test_bad_abundance_is_refused(window) -> None:
    w, calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    view.table.item(1, 1).setText("lots")
    view.assume_bigg_check.setChecked(True)
    assert w.run_community_solve() == ""
    assert view.status.text() == "b: abundance is not a number — fix it before running."
    assert calls == []


def test_abundances_reach_the_taxonomy(window) -> None:
    w, calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    view.set_abundance("b", 3.0)
    view.assume_bigg_check.setChecked(True)
    assert w.run_community_solve()
    deadline = time.time() + 10
    while not calls and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    path = Path(calls[0][calls[0].index("--taxonomy") + 1])
    rows = {r["id"]: float(r["abundance"]) for r in csv.DictReader(path.open())}
    assert rows == {"a": 1.0, "b": 3.0}


def test_community_result_lives_in_the_page(window) -> None:
    w, _calls = window
    w._show_profile("community")
    assert w.pages.currentWidget() is w.community_builder
    assert w.community_result_page.parent() is not None
    assert w.community_builder.results.has_results()
    assert w.community_result_page.isAncestorOf(w.profile_view)


def _taxonomy(w, calls) -> dict[str, float]:
    deadline = time.time() + 10
    while not calls and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    path = Path(calls[0][calls[0].index("--taxonomy") + 1])
    return {r["id"]: float(r["abundance"]) for r in csv.DictReader(path.open())}


def _load_run(w, run_dir: Path) -> None:
    from gui_project_helpers import solved_bundle

    solved_bundle().write(run_dir)
    (run_dir / "manifest.json").write_text('{"run_hash": "abc1234567890"}\n')
    assert w.load_run_dir(run_dir)
    assert w.community_builder.results.has_results()


def test_an_abundance_still_being_typed_is_what_runs(window) -> None:
    from PySide6.QtWidgets import QLineEdit

    w, calls = window
    view = w.community_builder
    w.show_analysis("community")
    view.model_picker.set_selected(["a", "b"])
    view.assume_bigg_check.setChecked(True)
    view.table.setCurrentCell(0, 1)
    view.table.editItem(view.table.item(0, 1))
    editors = view.table.viewport().findChildren(QLineEdit)
    assert editors, "the abundance editor is open"
    editors[0].setText("0.5")
    assert view.table.item(0, 1).text() == "1", "not committed by typing alone"
    view.run_btn.click()
    assert _taxonomy(w, calls) == {"a": 0.5, "b": 1.0}


def test_project_switch_clears_the_community_result(window, tmp_path: Path) -> None:
    w, _calls = window
    _load_run(w, tmp_path / "run")
    make_project(tmp_path / "p2", ["x"])
    assert w.open_project(tmp_path / "p2")
    w.show_analysis("community")
    assert not w.community_builder.results.has_results()
    assert w.current_manifest is None
    assert w.profile_view.table.rowCount() == 0


def test_failed_rerun_clears_the_previous_result(window, tmp_path: Path) -> None:
    w, calls = window
    _load_run(w, tmp_path / "run")
    view = w.community_builder
    view.assume_bigg_check.setChecked(True)
    assert w.run_community_solve()
    deadline = time.time() + 10
    while not view.run_btn.isEnabled() and time.time() < deadline:
        APP.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    assert calls, "the rerun reached the CLI (which fails with rc=2)"
    assert "community solve failed" in view.status.text()
    assert not view.results.has_results()


def test_changed_inputs_clear_the_shown_result(window, tmp_path: Path) -> None:
    w, _calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a", "b"])
    _load_run(w, tmp_path / "run")
    view.model_picker.set_selected(["a"])
    assert not view.results.has_results()
    assert view.status.text() == "Inputs changed — previous result cleared; re-run to update."
    _load_run(w, tmp_path / "run")
    view.set_abundance("a", 2.0)
    assert not view.results.has_results()
    _load_run(w, tmp_path / "run")
    view.f_slider.setValue(30)
    assert not view.results.has_results()


def test_a_failed_load_empties_the_hosted_result(window, tmp_path: Path) -> None:
    w, _calls = window
    _load_run(w, tmp_path / "run")
    broken = tmp_path / "broken"
    broken.mkdir()
    assert not w.load_run_dir(broken)
    assert not w.community_builder.results.has_results()
    assert w.current_manifest is None
