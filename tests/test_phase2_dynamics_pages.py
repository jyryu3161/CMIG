from __future__ import annotations

import json
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

_DFBA = {"status": "ok", "final_t": 1.0, "final_biomass": 0.2,
         "final_concentrations": {"glc": 1.0}, "warnings": []}
_SPATIAL = {"status": "ok", "final_t": 1.0, "final_min": 0.0, "final_max": 2.0, "warnings": []}


@pytest.fixture
def window(tmp_path: Path):
    make_project(tmp_path / "p", ["a", "b"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def _draw(w, key: str, tmp_path: Path) -> None:
    if key == "dfba":
        w.dynamics_view.load_dfba_summary(_DFBA, run_dir=tmp_path)
    else:
        w.spatial_page.load_spatial_summary(_SPATIAL, run_dir=tmp_path)


def _wait_for_button(w, button) -> None:
    deadline = time.time() + 10
    while not button.isEnabled() and time.time() < deadline:
        APP.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    assert button.isEnabled()


def test_two_dynamics_pages() -> None:
    w = build_main_window()
    assert w.analysis_pages["dfba"] is w.dynamics_view
    assert w.analysis_pages["spatial"] is w.spatial_page
    assert not hasattr(w.dynamics_view, "spatial_metabolite_input")
    assert w.dynamics_view.run_dfba_btn is w.dynamics_view.run_btn
    assert w.spatial_page.run_spatial_btn is w.spatial_page.run_btn


def test_spatial_result_loads_on_its_page(tmp_path) -> None:
    w = build_main_window()
    w.spatial_page.load_spatial_summary(
        {"status": "ok", "final_t": 1.0, "final_min": 0.0, "final_max": 2.0, "warnings": []},
        run_dir=tmp_path,
    )
    assert w.spatial_page.results.has_results()
    assert w.spatial_page.table.item(0, 0).text() == "Spatial"
    assert w.dynamics_view.table.rowCount() == 0


def test_dfba_advanced_counts_changes() -> None:
    w = build_main_window()
    page = w.dynamics_view
    page.close_untracked_check.setChecked(True)
    assert page.advanced.changed_count() == 1


def test_spatial_advanced_counts_changes() -> None:
    page = build_main_window().spatial_page
    page.diffusion_spin.setValue(0.5)
    page.sink_combo.setCurrentText("top")
    assert page.advanced.changed_count() == 2


@pytest.mark.parametrize("key", ["dfba", "spatial"])
def test_edit_clears_the_result(window, tmp_path, key: str) -> None:
    page = window.analysis_pages[key]
    _draw(window, key, tmp_path)
    assert page.results.has_results()
    (page.t_end_spin if key == "dfba" else page.steps_spin).setValue(3)
    assert not page.results.has_results()
    assert page.table.rowCount() == 0
    assert page.status.text() == "Inputs changed — previous result cleared; re-run to update."


def test_new_result_without_a_figure_drops_the_previous_figure(window, tmp_path) -> None:
    pytest.importorskip("PySide6.QtSvg")
    page = window.spatial_page
    (tmp_path / "spatial_snapshots.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='120' height='80'>"
        "<rect width='120' height='80' fill='#2b8cbe'/></svg>"
    )
    page.load_spatial_summary(_SPATIAL, run_dir=tmp_path)
    assert not page.figure_label.pixmap().isNull()
    other = tmp_path / "other"
    other.mkdir()
    page.load_spatial_summary(_SPATIAL, run_dir=other)
    assert page.figure_label.pixmap().isNull()


@pytest.mark.parametrize("key", ["dfba", "spatial"])
def test_failed_rerun_clears_the_previous_result(window, monkeypatch, tmp_path, key) -> None:
    w = window
    page = w.analysis_pages[key]
    if key == "dfba":
        page.model_picker.set_selected(["a"])
    _draw(w, key, tmp_path)
    assert page.results.has_results()
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: 2)
    assert (w.run_dfba() if key == "dfba" else w.run_spatial_preview())
    _wait_for_button(w, page.run_btn)
    assert "failed" in page.status.text()
    assert not page.results.has_results()
    assert page.table.rowCount() == 0


@pytest.mark.parametrize("key", ["dfba", "spatial"])
def test_unreadable_readback_clears_the_previous_result(window, tmp_path, key) -> None:
    page = window.analysis_pages[key]
    _draw(window, key, tmp_path)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / f"{key}_summary.json").write_text("{not json")
    loader = window.load_dfba_dir if key == "dfba" else window.load_spatial_dir
    assert loader(broken) is False
    assert not page.results.has_results()
    assert page.table.rowCount() == 0
    assert "Readback invalid/unreadable" in page.status.text()


@pytest.mark.parametrize("key", ["dfba", "spatial"])
def test_missing_summary_clears_the_previous_result(window, tmp_path, key) -> None:
    page = window.analysis_pages[key]
    _draw(window, key, tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    loader = window.load_dfba_dir if key == "dfba" else window.load_spatial_dir
    assert loader(empty) is False
    assert not page.results.has_results()
    assert "Readback invalid/unreadable" in page.status.text()


def test_good_readback_shows_on_the_matching_page(window, tmp_path) -> None:
    run = tmp_path / "spatial"
    run.mkdir()
    (run / "spatial_summary.json").write_text(json.dumps(_SPATIAL))
    assert window.load_spatial_dir(run)
    assert window.pages.currentWidget() is window.spatial_page
    assert window.spatial_page.results.has_results()
    assert not window.dynamics_view.results.has_results()


def test_project_switch_clears_both_dynamics_pages(window, tmp_path) -> None:
    w = window
    for key in ("dfba", "spatial"):
        _draw(w, key, tmp_path)
        assert w.analysis_pages[key].results.has_results()
    make_project(tmp_path / "p2", ["x"])
    assert w.open_project(tmp_path / "p2")
    for page in (w.dynamics_view, w.spatial_page):
        assert not page.results.has_results()
        assert page.table.rowCount() == 0
        assert page.status.text() == ""
        assert page.figure_label.text() == "No dynamics figure loaded."
