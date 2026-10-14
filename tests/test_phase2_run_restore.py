from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from argv_drivers import DRIVERS  # noqa: E402
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
    make_project(tmp_path / "p", ["a", "b", "c", "host"])
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


def test_a_search_run_records_its_inputs(window) -> None:
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


_DRIVER_PAGES = {
    "search_default": "search", "search_advanced": "search", "gene_ko": "gene_ko",
    "strain_growth": "strain_growth", "ratio_impact": "ratio_impact", "community": "community",
    "host": "host", "host_search": "host_search", "dfba": "dfba", "spatial": "spatial",
    "medium_growth": "medium", "minimal_medium": "medium", "sweep": "sweep",
}


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_every_run_records_its_inputs(window, name: str) -> None:
    w, calls = window
    assert DRIVERS[name](w), f"{name}: the page refused to run"
    run_dir = _out(_wait(calls))
    record, problem = proj.read_run_request(run_dir)
    assert problem == "" and record is not None
    assert record["analysis"] == _DRIVER_PAGES[name]
    assert record["values"] == w.analysis_pages[_DRIVER_PAGES[name]].snapshot()


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
    project = w.session.require()
    before = sorted(p.name for p in project.runs_dir.iterdir())
    inputs_before = sorted(p.name for p in project.inputs_dir.iterdir())
    w.strain_growth_page.model_picker.set_selected(["a"])
    assert w.run_strain_growth_report() == ""
    assert "disk full" in w.strain_growth_page.status.text()
    assert sorted(p.name for p in project.runs_dir.iterdir()) == before
    assert sorted(p.name for p in project.inputs_dir.iterdir()) == inputs_before
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


def test_a_gui_named_folder_wins_over_the_community_fallback(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "medium-growth-20261014-101010"
    run_dir.mkdir(parents=True)
    (run_dir / "nodes.parquet").write_bytes(b"")
    assert run_restore.analysis_for_run(run_dir) == ("medium", None, "")
    other = tmp_path / "runs" / "my-solve"
    other.mkdir()
    (other / "nodes.parquet").write_bytes(b"")
    assert run_restore.analysis_for_run(other)[0] == "community"


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


def test_reopened_run_without_a_record_never_claims_the_screen_as_executed(
    window, monkeypatch
) -> None:
    w, calls = window
    page = w.gene_ko_page
    run_dir = w.session.require().runs_dir / "legacy-ko"
    _gene_ko_summary(run_dir)
    (run_dir / "manifest.json").write_text(json.dumps({"workflow_kind": "gene_ko_search"}))
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    page.target_input.setText("ac")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is page
    assert page.results.has_results()
    details = page.results_panel.details.toPlainText()
    assert "Executed request" not in details and "'target': 'ac'" not in details
    assert "Executed Gene KO" not in details
    assert "Inputs for legacy-ko are not known" in page.status.text()
    assert "superseded" not in page.status.text()


def test_fully_restored_ranked_run_shows_its_executed_request(window, monkeypatch) -> None:
    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    page.target_input.setText("but")
    assert w.run_gene_ko_search()
    run_dir = _out(_wait(calls))
    _gene_ko_summary(run_dir)
    monkeypatch.setattr(w, "_inspect_gui_run", lambda _d: {"artifact_integrity": "verified"})
    page.target_input.setText("ac")
    w._open_run_entry(run_dir)
    details = page.results_panel.details.toPlainText()
    assert "Executed request" in details and "'target': 'but'" in details
    assert "not known" not in page.status.text()


def _sweep_run(w, name: str) -> Path:
    run_dir = w.session.require().runs_dir / name
    run_dir.mkdir()
    return run_dir


def test_corrupt_sweep_parquet_is_reported_and_cleared(window) -> None:
    from cmig.core.sweep import SweepRow

    w, _calls = window
    w.sweep_view.load_results([SweepRow(
        condition_id="old", axis_values={}, metric="growth", value=1.0, run_hash="h",
        status="ok", diagnostic=None, cache_hit=False,
    )])
    run_dir = _sweep_run(w, "sweep-20261014-101010")
    (run_dir / "sweep.parquet").write_bytes(b"not a parquet file")
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is w.sweep_page
    assert w.sweep_view.table.rowCount() == 0
    assert "Readback invalid/unreadable" in w.sweep_view.status.text()


def test_failed_sweep_with_partial_rows_says_it_failed(window) -> None:
    from cmig.core.sweep import SweepRow, write_sweep_parquet

    w, _calls = window
    run_dir = _sweep_run(w, "sweep-20261014-101010")
    write_sweep_parquet([SweepRow(
        condition_id="c1", axis_values={"tradeoff_f": 0.3}, metric="growth", value=0.5,
        run_hash="h", status="ok", diagnostic=None, cache_hit=False,
    )], run_dir / "sweep.parquet")
    proj.write_run_state(run_dir, "failed", "sweep")
    w._open_run_entry(run_dir)
    assert w.sweep_view.table.rowCount() == 1
    status = w.sweep_view.status.text()
    assert "failed" in status and "partial" in status


def _namespace_page(w, key: str):
    """(models picker, "already BiGG" box, the object whose namespace_policy() runs)."""
    owner = w.community_builder if key == "community" else w.medium_editor
    return owner.model_picker, owner.assume_bigg_check, owner


@pytest.mark.parametrize("key", ["community", "medium"])
def test_a_revoked_namespace_confirmation_is_not_restored(window, key: str) -> None:
    w, _calls = window
    picker, check, owner = _namespace_page(w, key)
    picker.set_selected(["a", "b"])
    w.session.confirm_namespace("a")
    w.session.confirm_namespace("b")
    w.refresh_workspace()
    assert check.isChecked()
    values = w.analysis_pages[key].snapshot()
    assert values["assume_bigg"] is True
    w.session.revoke_namespace("b")
    picker.set_selected([])  # the inputs moved on before the run is reopened
    w.refresh_workspace()
    notes = w.analysis_pages[key].restore(values)
    w.refresh_workspace()
    assert picker.selected_ids() == ["a", "b"]
    assert not check.isChecked()
    assert notes == ["namespace confirmation not restored: b not confirmed"]
    assert "--assume-bigg-namespace" not in owner.namespace_policy()[0]


@pytest.mark.parametrize("key", ["community", "medium"])
def test_a_namespace_confirmation_still_held_is_restored(window, key: str) -> None:
    w, _calls = window
    picker, check, owner = _namespace_page(w, key)
    picker.set_selected(["a"])
    w.session.confirm_namespace("a")
    w.refresh_workspace()
    values = w.analysis_pages[key].snapshot()
    picker.set_selected([])
    w.refresh_workspace()
    assert w.analysis_pages[key].restore(values) == []
    w.refresh_workspace()
    assert check.isChecked()
    assert owner.namespace_policy()[0] == ["--assume-bigg-namespace"]


def test_a_reopened_run_says_its_namespace_tick_was_not_restored(window) -> None:
    w, calls = window
    view = w.community_builder
    view.model_picker.set_selected(["a"])
    w.session.confirm_namespace("a")
    w.refresh_workspace()
    assert view.assume_bigg_check.isChecked()
    assert w.run_community_solve()
    run_dir = _out(_wait(calls))
    w.session.revoke_namespace("a")
    w.refresh_workspace()
    w._open_run_entry(run_dir)
    assert not view.assume_bigg_check.isChecked()
    assert "namespace confirmation not restored: a not confirmed" in view.banner.text()


def test_another_projects_run_is_opened_without_its_inputs(
    window, tmp_path: Path, monkeypatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    w, calls = window
    page = w.gene_ko_page
    page.model_picker.set_selected(["a", "b"])
    page.members_picker.set_selected(["a"])
    page.target_input.setText("ac")
    assert w.run_gene_ko_search()
    run_dir = _out(_wait(calls))
    assert proj.read_run_request(run_dir)[0] is not None  # the record is there to be misread
    make_project(tmp_path / "p2", ["a", "b"])
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert w.open_project(tmp_path / "p2")
    page.target_input.setText("zzz")
    page.model_picker.set_selected(["b"])
    w._open_run_entry(run_dir)
    assert w.pages.currentWidget() is page
    assert page.target_input.text() == "zzz"  # the inputs on screen are left as they are
    assert page.model_picker.selected_ids() == ["b"]
    assert (f"Inputs for {run_dir.name} cannot be restored: opened from outside this project."
            in page.banner.text())


_RERUN = {
    "search_default": "run_search_fixture", "search_advanced": "run_search_fixture",
    "gene_ko": "run_gene_ko_search", "strain_growth": "run_strain_growth_report",
    "ratio_impact": "run_abundance_impact", "community": "run_community_solve",
    "host": "run_host_microbe_bigg", "host_search": "run_host_search_bigg", "dfba": "run_dfba",
    "spatial": "run_spatial_preview", "medium_growth": "run_medium_growth_check",
    "minimal_medium": "run_minimal_medium", "sweep": "run_sweep",
}


def _settle(w) -> None:
    deadline = time.time() + 10
    while w._active_job_ids() and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    w._poll_completed_jobs()


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_a_reopened_run_reruns_with_the_same_argv(
    tmp_path: Path, monkeypatch, name: str
) -> None:
    from test_phase2_argv_parity import normalize

    make_project(tmp_path / "p", ["a", "b", "host"])
    calls: list[list[str]] = []
    monkeypatch.setattr("cmig.cli.main.main", lambda argv: (calls.append(list(argv)), 2)[1])
    recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    w = build_main_window()
    w.recent = recent
    assert w.open_project(tmp_path / "p")
    for model_id in ("a", "b", "host"):  # "already BiGG" is restored only when confirmed
        w.session.confirm_namespace(model_id)
    assert DRIVERS[name](w), f"{name}: the page refused to run"
    first = _wait(calls)
    run_dir = _out(first)
    root = w.session.require().root
    _settle(w)
    w.close_project()
    fresh = build_main_window()  # nothing of the first run's inputs is left on screen
    fresh.recent = recent
    assert fresh.open_project(tmp_path / "p")
    try:
        fresh._open_run_entry(run_dir)
        page = fresh.analysis_pages[_DRIVER_PAGES[name]]
        assert page.banner.text() == f"Inputs restored from {run_dir.name}."
        assert getattr(fresh, _RERUN[name])(), f"{name}: refused after restore"
        second = _wait(calls, 2)
        assert normalize(second, root) == normalize(first, root)
        _settle(fresh)
    finally:
        fresh.close_project()
