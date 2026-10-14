from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.service import JobStatus  # noqa: E402

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


def test_edit_clears_a_ranked_result_but_a_same_choice_keeps_it(window, tmp_path: Path) -> None:
    w, _calls = window
    ko = w.gene_ko_page
    payload = {"target": "but", "ko_level": "gene", "warnings": [],
               "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                               "community_growth": 0.3, "evaluation_status": "optimal"}]}
    w._show_ranked("gene_ko", payload, tmp_path, ko.request_fields("gene_ko"))
    assert ko.results.has_results()
    ko.target_input.setText("ac")
    assert not ko.results.has_results()
    assert "Inputs changed" in ko.status.text()

    ratio = w.ratio_impact_page
    ratio.model_picker.set_selected(["b", "c"])
    ratio.member_combo.setCurrentText("b")
    ratio_payload = {"status": "ok", "target_member": "b", "target": "but",
                     "rows": [{"target_abundance": 0.2, "target_influence_share": 0.7,
                               "target_member_exchange": 1.2, "community_growth": 0.5,
                               "status": "optimal"}]}
    w._show_ranked("ratio_impact", ratio_payload, tmp_path,
                   ratio.request_fields("abundance_impact"))
    assert ratio.results.has_results()
    ratio.model_picker.set_selected(["b", "c"])
    w._refresh_pickers()  # a picker rebuild that keeps the same choice
    assert ratio.model_picker.selected_ids() == ["b", "c"]
    assert ratio.results.has_results()
    assert ratio.results_panel.table.rowCount() == 1


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


_KO_PAYLOAD = {"target": "but", "ko_level": "gene", "warnings": [],
               "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                               "community_growth": 0.3, "evaluation_status": "optimal"}]}


def test_failed_gene_ko_rerun_clears_the_shown_ranking(window, tmp_path: Path) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    w._show_ranked("gene_ko", _KO_PAYLOAD, tmp_path, page.request_fields("gene_ko"))
    assert page.results.has_results()
    assert w.run_gene_ko_search()
    deadline = time.time() + 10
    while not page.run_btn.isEnabled() and time.time() < deadline:
        APP.processEvents()
        w._poll_completed_jobs()
        time.sleep(0.02)
    assert calls, "the rerun reached the CLI (which fails with rc=2)"
    assert "gene KO search failed" in page.status.text()
    assert not page.results.has_results()
    assert page.results_panel.table.rowCount() == 0


def test_unreadable_ranked_result_clears_the_shown_ranking(window, tmp_path, monkeypatch) -> None:
    w, _calls = window
    page = w.gene_ko_page
    w._show_ranked("gene_ko", _KO_PAYLOAD, tmp_path, page.request_fields("gene_ko"))
    page.status.setText("gene-ko started: j1")
    monkeypatch.setattr(w.runner, "poll", lambda _jid: SimpleNamespace(
        status=JobStatus.DONE, result=dict(_KO_PAYLOAD), error=None))
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _run_dir: None)
    out_dir = tmp_path / "unreadable"
    jobs = {"j1": (out_dir, page.request_fields("gene_ko"))}
    w._finish_ranked_jobs("gene_ko", jobs, "gene KO search")
    assert jobs == {}
    assert not page.results.has_results()
    assert page.results_panel.table.rowCount() == 0
    assert page.status.text() == (
        f"gene KO search finished, but its result could not be read back — see the inspector "
        f"({out_dir})"
    )


def test_project_switch_clears_every_ranked_page(window, tmp_path: Path) -> None:
    from cmig.gui.app import _host_search_summary_for_search_view

    w, _calls = window
    search_payload = {"target": "ac", "metric": "target_transfer", "status": "ok",
                      "warnings": [], "top_ranked": [{"members": ["a"], "score": 1.0}]}
    w.search_view.load_summary(_host_search_summary_for_search_view(search_payload),
                               run_dir=tmp_path)
    w.search_view.status.setText("Search run: old project")
    w._show_ranked("gene_ko", _KO_PAYLOAD, tmp_path, w.gene_ko_page.request_fields("gene_ko"))
    w._show_ranked("host_search", search_payload, tmp_path,
                   w.host_search_page.request_fields("host_search"))
    pages = (w.search_view, w.gene_ko_page, w.host_search_page)
    assert all(page.results.has_results() for page in pages)
    make_project(tmp_path / "p2", ["x"])
    assert w.open_project(tmp_path / "p2")
    for page in (*pages, w.strain_growth_page, w.ratio_impact_page):
        assert not page.results.has_results()
        assert page.results_panel.table.rowCount() == 0
        assert page.status.text() == ""
