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
def window(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    yield w, calls
    w.close_project()


def test_each_workflow_has_its_own_page(window) -> None:
    w, _calls = window
    assert w.analysis_pages["gene_ko"] is w.gene_ko_page
    assert w.analysis_pages["strain_growth"] is w.strain_growth_page
    assert w.analysis_pages["ratio_impact"] is w.ratio_impact_page
    assert not hasattr(w.search_view, "ko_members_input")
    assert not hasattr(w.search_view, "growth_member_input")
    for page in (w.search_view, w.gene_ko_page, w.strain_growth_page, w.ratio_impact_page):
        assert not page.results.has_results(), "no result until a run"


def test_gene_ko_combination_follows_the_models(window) -> None:
    w, _calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    assert page.members_picker.choice_ids() == ["a", "b"]
    assert page.members_picker.selected_ids() == [], "no combination is assumed"
    page.members_picker.set_selected(["a", "b"])
    items = [page.member_combo.itemText(i) for i in range(page.member_combo.count())]
    assert items == ["All members", "a", "b"]
    page.member_combo.setCurrentText("b")
    page.model_picker.set_selected(["a"])
    assert page.members_picker.selected_ids() == ["a"]
    assert page.member_combo.currentText() == "All members", "b left the combination"


def test_gene_ko_refuses_without_combination_or_target(window) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    assert w.run_gene_ko_search() == ""
    assert "KO members are required" in page.status.text()
    page.members_picker.set_selected(["a"])
    page.target_input.setText("")
    assert w.run_gene_ko_search() == ""
    assert "does not substitute a default target" in page.status.text()
    assert calls == []


def test_ratio_member_comes_from_the_models(window) -> None:
    w, calls = window
    page = w.ratio_impact_page
    page.model_picker.set_selected(["b", "c"])
    items = [page.member_combo.itemText(i) for i in range(page.member_combo.count())]
    assert items == ["choose…", "b", "c"]
    assert w.run_abundance_impact() == ""
    assert "Target member is required" in page.status.text()
    assert calls == []


def test_ranked_result_lands_on_its_own_page(window, tmp_path: Path) -> None:
    w, _calls = window
    payload = {"target": "ac", "ko_level": "gene", "warnings": [],
               "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                               "community_growth": 0.3, "evaluation_status": "optimal"}]}
    w._show_ranked("gene_ko", payload, tmp_path, w.gene_ko_page.request_fields("gene_ko"))
    assert w.pages.currentWidget() is w.gene_ko_page
    assert w.gene_ko_page.results.has_results()
    assert w.gene_ko_page.results_panel.table.item(0, 0).text() == "a:g1"
    assert w.search_view.results_panel.table.rowCount() == 0, "Search keeps its own result"


def test_search_advanced_counts_changes(window) -> None:
    w, _calls = window
    page = w.search_view
    assert page.advanced.changed_count() == 0
    page.strategy_combo.setCurrentText("exhaustive")
    page.seed_spin.setValue(3)
    assert page.advanced.toggle.text() == "Advanced options · 2 changed"
    assert page.advanced_toggle is page.advanced.toggle


def test_remembered_choice_per_page(window) -> None:
    w, _calls = window
    w.strain_growth_page.model_picker.set_selected(["b"])
    assert w.session.settings("strain_growth")["models"] == ["b"]
    assert w.session.settings("gene_ko").get("models") != ["b"]
