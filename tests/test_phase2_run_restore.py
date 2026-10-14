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

from cmig.gui import run_restore  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from cmig.io import project as proj  # noqa: E402

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


def _out(argv: list[str]) -> Path:
    return Path(argv[argv.index("--out") + 1])


def _wait(calls: list[list[str]], n: int = 1) -> list[str]:
    deadline = time.time() + 10
    while len(calls) < n and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    assert len(calls) >= n
    return calls[-1]


def test_every_run_records_its_inputs(window) -> None:
    w, calls = window
    w.search_view.model_picker.set_selected(["a", "b"])
    w.search_view.min_size_spin.setValue(1)
    assert w.run_search_fixture()
    record, problem = proj.read_run_request(_out(_wait(calls)))
    assert problem == "" and record is not None
    assert record["analysis"] == "search"
    assert record["values"]["models"] == ["a", "b"]
    assert record["values"]["min_size"] == 1
    assert record["models"] == ["a", "b"]


def test_reopening_a_run_restores_its_page_and_inputs(window) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    page.target_input.setText("ac")
    assert w.run_gene_ko_search()
    run_dir = _out(_wait(calls))
    w.show_analysis("search")
    page.target_input.setText("but")
    page.model_picker.set_selected(["c"])
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is page
    assert page.model_picker.selected_ids() == ["a", "b"]
    assert page.members_picker.selected_ids() == ["a"]
    assert page.target_input.text() == "ac"
    assert "Inputs restored from" in page.banner.text()


def test_removed_model_named_in_banner(window) -> None:
    w, calls = window
    w.strain_growth_page.model_picker.set_selected(["a", "b"])
    assert w.run_strain_growth_report()
    run_dir = _out(_wait(calls))
    w.session.remove_models(["b"])
    w._open_run_entry(run_dir)
    page = w.strain_growth_page
    assert page.model_picker.selected_ids() == ["a"]
    assert "b can no longer be chosen" in page.banner.text()


def test_corrupt_request_opens_page_with_banner(window) -> None:
    w, _calls = window
    project = w.session.require()
    run_dir = project.runs_dir / "gene-ko-20261014-101010"
    run_dir.mkdir()
    proj.run_request_path(run_dir).write_text("{oops")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.gene_ko_page
    assert "cannot be restored" in w.gene_ko_page.banner.text()
    assert "could not be read" in w.gene_ko_page.banner.text()


def test_run_without_record_keeps_inputs(window) -> None:
    w, _calls = window
    project = w.session.require()
    run_dir = project.runs_dir / "dfba-20261014-101010"
    run_dir.mkdir()
    w.dynamics_view.initial_input.setText("EX_glc__D_e=3")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.dynamics_view
    assert w.dynamics_view.initial_input.text() == "EX_glc__D_e=3"
    assert "Inputs for dfba-20261014-101010 cannot be restored" in w.dynamics_view.banner.text()


def test_record_failure_refuses_the_run_and_leaves_nothing(window, monkeypatch) -> None:
    w, calls = window

    def refuse(*_a, **_k):  # type: ignore[no-untyped-def]
        raise proj.ProjectError("disk full")

    monkeypatch.setattr(proj, "write_run_request", refuse)
    before = sorted(p.name for p in w.session.require().runs_dir.iterdir())
    w.strain_growth_page.model_picker.set_selected(["a"])
    assert w.run_strain_growth_report() == ""
    assert "disk full" in w.strain_growth_page.status.text()
    assert sorted(p.name for p in w.session.require().runs_dir.iterdir()) == before
    assert calls == []


def test_restored_ranked_result_is_not_marked_superseded(window, monkeypatch) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    assert w.run_gene_ko_search()
    run_dir = _out(_wait(calls))
    run_dir.mkdir(exist_ok=True)
    (run_dir / "gene_ko_summary.json").write_text(json.dumps({
        "target": "but", "ko_level": "gene", "warnings": [],
        "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                        "community_growth": 0.3, "evaluation_status": "optimal"}],
    }))
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    page.target_input.setText("ac")
    w._open_run_entry(run_dir)
    assert page.results.has_results()
    assert "superseded" not in page.status.text()


def test_analysis_for_run_falls_back_to_the_folder_name(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "host-search-20261014-101010"
    run_dir.mkdir(parents=True)
    assert run_restore.analysis_for_run(run_dir) == ("host_search", None, "")
    (run_dir / "manifest.json").write_text(json.dumps({"workflow_kind": "strain_growth"}))
    assert run_restore.analysis_for_run(run_dir)[0] == "strain_growth"


def _gene_ko_summary(run_dir: Path) -> None:
    run_dir.mkdir(exist_ok=True)
    (run_dir / "gene_ko_summary.json").write_text(json.dumps({
        "target": "but", "ko_level": "gene", "warnings": [],
        "top_ranked": [{"member": "a", "gene": "g1", "score": 1.0, "target_flux": 2.0,
                        "community_growth": 0.3, "evaluation_status": "optimal"}],
    }))


def test_unloadable_ranked_run_does_not_keep_another_runs_result(window, monkeypatch) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    assert w.run_gene_ko_search()
    shown = _out(_wait(calls))
    _gene_ko_summary(shown)
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    w._open_run_entry(shown)
    assert page.results.has_results()
    page.target_input.setText("ac")
    assert w.run_gene_ko_search()
    broken = _out(_wait(calls, 2))  # claimed and recorded, but no summary was written
    w._open_run_entry(shown)
    assert page.results.has_results()
    w._open_run_entry(broken)
    assert page.target_input.text() == "ac"
    assert not page.results.has_results()
    assert page.results_panel.table.rowCount() == 0
    assert "Readback invalid/unreadable" in page.status.text()
    assert "Inputs restored from" in page.banner.text()


def test_unloadable_community_run_does_not_keep_another_runs_result(window) -> None:
    w, _calls = window
    w._show_profile("community")  # some other community result on show
    assert w.community_builder.results.has_results()
    run_dir = w.session.require().runs_dir / "community-20261014-101010"
    run_dir.mkdir()
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.community_builder
    assert not w.community_builder.results.has_results()
    assert (f"No result shown for {run_dir.name}"
            in w.community_builder.status.text())
    assert "cannot be restored" in w.community_builder.banner.text()


def test_opening_another_page_clears_the_banner(window) -> None:
    w, _calls = window
    run_dir = w.session.require().runs_dir / "dfba-20261014-101010"
    run_dir.mkdir()
    w._open_run_entry(run_dir)
    assert w.dynamics_view.banner.isVisibleTo(w.dynamics_view)
    w.show_analysis("search")
    w.show_analysis("dfba")
    assert not w.dynamics_view.banner.isVisibleTo(w.dynamics_view)
