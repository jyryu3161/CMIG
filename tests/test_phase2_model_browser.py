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
    assert not hasattr(w.inspector, "exchange_list")


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


@pytest.mark.parametrize("bad_index", ["{not json", "older schema"])
def test_unusable_index_file_is_rebuilt(tmp_path: Path, bad_index: str) -> None:
    import json

    from cmig.io import model_index

    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "e_coli_core.xml"))
    proj.save_project(project)
    path = model_index.index_path(project.root, entry.sha256)
    if bad_index == "older schema":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = 0
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_text(bad_index, encoding="utf-8")
    w = build_main_window()
    _open(w, project.root, tmp_path)
    try:
        w.sidebar.select("models", "e_coli_core")
        deadline = time.time() + 30
        while w.model_browser.reactions_tab.table.rowCount() == 0 and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert w.model_browser.reactions_tab.table.rowCount() == 95
        assert model_index.load_index(project.root, entry.sha256) is not None
    finally:
        w.close_project()


def test_retry_rebuilds_an_unusable_index(tmp_path: Path, monkeypatch) -> None:
    from cmig.io import model_index

    real_build = model_index.build_index_file
    calls: list[str] = []

    def flaky(root, path, sha, model_id):  # type: ignore[no-untyped-def]
        calls.append(model_id)
        if len(calls) == 1:
            raise ValueError("boom")
        return real_build(root, path, sha, model_id)

    monkeypatch.setattr(model_index, "build_index_file", flaky)
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "e_coli_core.xml"))
    proj.save_project(project)
    model_index.index_path(project.root, entry.sha256).write_text("{not json")
    w = build_main_window()
    _open(w, project.root, tmp_path)
    try:
        w.sidebar.select("models", "e_coli_core")
        b = w.model_browser
        deadline = time.time() + 30
        while "boom" not in b.contents_label.text() and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert not b.retry_btn.isHidden()
        b.retry_btn.click()
        assert w._index_job is not None
        while b.reactions_tab.table.rowCount() == 0 and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert b.reactions_tab.table.rowCount() == 95 and calls == ["e_coli_core"] * 2
    finally:
        w.close_project()


def test_another_models_index_does_not_redraw_the_browsed_model(
    tmp_path: Path, monkeypatch
) -> None:
    import threading

    from cmig.io import model_index

    gate = threading.Event()
    real_write = model_index.write_index

    def gated(root, path, sha, model_id):  # type: ignore[no-untyped-def]
        assert gate.wait(10)
        return real_write(root, sha, model_id, {"reactions": [], "metabolites": [],
                                                "genes": [], "exchanges": [], "objective": []})

    monkeypatch.setattr(model_index, "build_index_file", gated)
    project = make_project(tmp_path / "p", ["a", "b"], index=False)
    reaction = {"id": "R1", "name": "one", "metabolites": {}, "lower": 0.0, "upper": 1.0}
    real_write(project.root, project.model("a").sha256, "a",
               {"reactions": [reaction], "metabolites": [], "genes": [], "exchanges": [],
                "objective": []})
    w = build_main_window()
    _open(w, project.root, tmp_path)
    try:
        assert w._index_job is not None  # b's index is being built
        w.sidebar.select("models", "a")
        b = w.model_browser
        b.set_growth("Growth 0.5")
        assert b.select("reaction", "R1")
        gate.set()
        deadline = time.time() + 10
        while w._index_job is not None and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert w._index_job is None
        assert b.growth_label.text() == "Growth 0.5"
        assert b.reactions_tab.current_id() == "R1"
    finally:
        w.close_project()


def test_model_derived_labels_are_plain_text() -> None:
    from PySide6.QtCore import Qt

    from cmig.gui.model_browser import ModelBrowser

    b = ModelBrowser()
    for label in (b.title_label, b.contents_label, b.objective_label, b.objective_terms,
                  b.namespace_label, b.growth_label):
        assert label.textFormat() == Qt.TextFormat.PlainText


def test_ensure_indexes_reads_no_index_on_the_gui_thread(tmp_path: Path, monkeypatch) -> None:
    import threading

    from cmig.io import model_index

    real_load = model_index.load_index
    on_main: list[bool] = []

    def recording(root, sha):  # type: ignore[no-untyped-def]
        on_main.append(threading.current_thread() is threading.main_thread())
        return real_load(root, sha)

    monkeypatch.setattr(model_index, "load_index", recording)
    make_project(tmp_path / "p", ["a", "b"])  # usable (empty) indexes on disk
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)  # opening calls _ensure_indexes
    try:
        assert w._index_job is not None and w._index_job_kind == "check"
        assert w._index_job not in w.bridge._job_ids, "a check alone is not an Activity job"
        deadline = time.time() + 10
        while w._index_job is not None and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.05)
            w._poll_completed_jobs()
        assert w._index_job is None
        assert w.jobs_panel.rowCount() == 0, "nothing to rebuild: nothing in Activity"
        assert on_main and not any(on_main), "index files are read only inside the job"
        w._ensure_indexes()
        assert w._index_job is None, "indexes the job found usable are not checked again"
    finally:
        w.close_project()


def test_another_model_starts_with_no_row_selected() -> None:
    """A row picked in one model must not stay highlighted (with an empty detail) in the next."""
    from cmig.gui.model_browser import ModelBrowser

    def entry(model_id: str) -> proj.ModelEntry:
        return proj.ModelEntry(id=model_id, file=f"models/{model_id}.xml", source_path="x",
                               sha256=model_id, format="xml", added="t", status="ok",
                               biomass=["BIOMASS"])

    def index(prefix: str) -> dict:
        reactions = [{"id": f"{prefix}{i}", "name": "", "metabolites": {}, "lower": 0.0,
                      "upper": 1.0, "gpr": "", "subsystem": ""} for i in range(5)]
        return {"reactions": reactions, "metabolites": [], "genes": [], "exchanges": [],
                "objective": []}

    b = ModelBrowser()
    b.show_model(entry("a"), index("A"))
    assert b.select("reaction", "A3")
    b.show_model(entry("b"), index("B"))
    assert b.reactions_tab.current_id() is None
    assert b.reactions_tab.table.selectedItems() == []
    assert b.reactions_tab.detail.toPlainText() == ""


def test_model_table_check_column_is_not_cut_at_1280(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a_model_with_a_long_id", "b"])
    proj.confirm_namespace(project, "b")
    proj.save_project(project)
    w = build_main_window()
    _open(w, tmp_path / "p", tmp_path)
    try:
        w.resize(1280, 800)
        w.show()
        APP.processEvents()
        table = w.model_manager.exchange_table
        for row in range(table.rowCount()):
            text = table.item(row, 1).text()
            assert table.columnWidth(1) > table.fontMetrics().horizontalAdvance(text), text
    finally:
        w.close_project()
