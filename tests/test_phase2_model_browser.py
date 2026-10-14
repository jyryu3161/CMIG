from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import (  # noqa: E402
    _deterministic_qt_teardown,  # noqa: F401
    make_project,
    textbook_sbml,
)
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _open(w, root: Path, tmp_path: Path) -> None:
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(root)


@pytest.fixture
def textbook_window(tmp_path: Path):
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "e_coli_core.xml"))
    proj.save_project(project)
    w = build_main_window()
    _open(w, project.root, tmp_path)
    yield w
    w.close_project()


def _visible_ids(tab) -> list[str]:
    return [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())
            if not tab.table.isRowHidden(r)]


def test_selecting_a_model_opens_its_browser(textbook_window) -> None:
    w = textbook_window
    w.sidebar.select("models", "e_coli_core")
    assert w.pages.currentWidget() is w.model_browser
    b = w.model_browser
    assert b.title_label.text().startswith("e_coli_core · 95 reactions · 72 metabolites")
    assert b.reactions_tab.table.rowCount() == 95
    assert b.exchanges_tab.table.rowCount() == 20
    assert b.objective_label.text() == "Objective: Biomass_Ecoli_core (biomass)"
    assert "Namespace not reviewed" in b.namespace_label.text()
    assert "0 of 20 reviewed" in b.namespace_label.text()
    assert not b.confirm_btn.isHidden() and b.revoke_btn.isHidden()


def test_filter_and_detail_navigation(textbook_window) -> None:
    w = textbook_window
    w.sidebar.select("models", "e_coli_core")
    b = w.model_browser
    b.reactions_tab.filter_input.setText("glc")
    assert set(_visible_ids(b.reactions_tab)) >= {"EX_glc__D_e", "GLCpts"}
    assert "PGI" not in _visible_ids(b.reactions_tab)
    assert b.select("reaction", "GLCpts")
    detail = b.reactions_tab.detail.toHtml()
    assert "D-Glucose" in detail and "met:glc__D_e" in detail
    b._navigate("met:glc__D_e")
    assert b.tabs.currentWidget() is b.metabolites_tab
    assert b.metabolites_tab.current_id() == "glc__D_e"
    assert "C6H12O6" in b.metabolites_tab.detail.toHtml()


def test_multi_term_objective_is_not_called_biomass(tmp_path: Path) -> None:
    from cmig.gui.model_browser import ModelBrowser

    entry = proj.ModelEntry(
        id="iAF987", file="models/iAF987.xml", source_path="x", sha256="s", format="xml",
        added="t", status="warning", biomass=[f"R{i}" for i in range(283)],
    )
    browser = ModelBrowser()
    browser.show_model(entry, None, "")
    assert browser.objective_label.text().startswith("Objective: 283 terms")
    assert "biomass)" not in browser.objective_label.text()
    assert browser.objective_terms.isHidden()
    browser.objective_toggle.setChecked(True)
    assert not browser.objective_terms.isHidden()


def test_missing_index_is_built_in_the_background(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"], index=False)
    real = textbook_sbml(tmp_path / "src" / "real.xml")
    (project.root / project.model("a").file).write_bytes(real.read_bytes())
    entry = project.model("a")
    entry.sha256 = proj._sha256(project.root / entry.file)
    proj.save_project(project)
    w = build_main_window()
    _open(w, project.root, tmp_path)
    try:
        w.sidebar.select("models", "a")
        deadline = time.time() + 30
        while w.model_browser.reactions_tab.table.rowCount() == 0 and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert w.model_browser.reactions_tab.table.rowCount() == 95
    finally:
        w.close_project()


def test_index_failure_shows_retry_and_keeps_model_selectable(
    tmp_path: Path, monkeypatch
) -> None:
    from cmig.io import model_index

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise ValueError("boom")

    monkeypatch.setattr(model_index, "build_index_file", boom)
    make_project(tmp_path / "p", ["a", "b"], index=False)
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)
    try:
        w.sidebar.select("models", "a")
        deadline = time.time() + 10
        while "boom" not in w.model_browser.contents_label.text() and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert "Model contents unavailable: boom" in w.model_browser.contents_label.text()
        assert not w.model_browser.retry_btn.isHidden()
        assert "a" in w.search_view.model_picker.selected_ids()
    finally:
        w.close_project()


def test_model_table_shows_reasons(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "bad"], statuses={"bad": "failed"})
    project = proj.open_project(tmp_path / "p")
    project.model("a").warnings = ["20 unresolved high-confidence namespace mappings block solve"]
    proj.save_project(project)
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)
    try:
        table = w.model_manager.exchange_table
        checks = {table.item(r, 0).text(): table.item(r, 1).text()
                  for r in range(table.rowCount())}
        assert checks == {"a": "⚠ Namespace not reviewed", "bad": "✗ Unreadable"}
    finally:
        w.close_project()


def test_legacy_entry_reason_from_warning_text(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    entry.namespace_mappings = None
    entry.warnings = ["3 low-confidence normalized candidates require review"]
    assert proj.check_reason(entry) == ("⚠", "Namespace not reviewed")


def test_inspector_wording(textbook_window) -> None:
    w = textbook_window
    w.sidebar.select("models", "e_coli_core")
    text = w.inspector.details.toPlainText()
    assert "Namespace mappings: 0 of 20 reviewed" in text
    assert "BiGG namespace coverage" not in text
    assert "Biomass:" not in text
    assert w.inspector.exchange_list.isHidden() if hasattr(w.inspector, "exchange_list") else True


def test_nothing_selected_shows_project_summary(textbook_window) -> None:
    w = textbook_window
    w._show_project_summary()
    assert w.inspector.title_label.text().startswith("Project · ")
    assert "Models: 1" in w.inspector.details.toPlainText()


def test_unreadable_model_is_not_shown_as_being_built(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "bad"], statuses={"bad": "failed"}, index=False)
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)
    try:
        w.sidebar.select("models", "bad")
        assert w.pages.currentWidget() is w.model_browser
        assert w.model_browser.contents_label.text() == "Model contents unavailable: unreadable"
        assert w.model_browser.retry_btn.isHidden()
    finally:
        w.close_project()


def test_switching_project_does_not_keep_the_browsed_model(tmp_path: Path) -> None:
    make_project(tmp_path / "p1", ["a"])
    make_project(tmp_path / "p2", ["a"])
    w = build_main_window()
    _open(w, tmp_path / "p1", tmp_path)
    try:
        w.sidebar.select("models", "a")
        assert w.model_browser.model_id() == "a"
        assert w.open_project(tmp_path / "p2")
        assert w.model_browser.model_id() is None
        assert w.pages.currentWidget() is not w.model_browser
        assert w.inspector.title_label.text() == "Project · p2"
    finally:
        w.close_project()
