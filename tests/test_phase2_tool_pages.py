from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import (  # noqa: E402
    _deterministic_qt_teardown,  # noqa: F401
    open_test_project,
)
from PySide6.QtWidgets import QApplication, QTableWidget  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402

APP = QApplication.instance() or QApplication([])


def test_tools_are_framed_pages() -> None:
    w = build_main_window()
    pairs = {"medium": w.medium_editor, "sweep": w.sweep_view, "sandbox": w.sandbox_view,
             "compare": w.scenario_compare}
    for key, content in pairs.items():
        page = w.analysis_pages[key]
        assert page.content is content
        assert page.isAncestorOf(content)
        assert page.run_btn.isHidden() and page.advanced.isHidden()
    assert w.sweep_page.results.isHidden(), "Sweep shows its own results"


def test_no_row_numbers_anywhere() -> None:
    w = build_main_window()
    tables = w.findChildren(QTableWidget)
    assert tables
    assert all(table.verticalHeader().isHidden() for table in tables)


def test_sandbox_result_shows_on_the_sandbox_page() -> None:
    w = build_main_window()
    w._show_profile("sandbox")
    assert w.pages.currentWidget() is w.sandbox_page
    assert w.sandbox_page.isAncestorOf(w.profile_view)
    w._show_profile("community")
    assert not w.sandbox_page.results.has_results()


def test_medium_inputs_round_trip() -> None:
    w = build_main_window()
    editor = w.medium_editor
    editor.clear_rows()
    editor.add_row("EX_glc__D_e", 10.0)
    editor.exact_medium_check.setChecked(True)
    saved = w.medium_page.snapshot()
    editor.clear_rows()
    editor.exact_medium_check.setChecked(False)
    assert w.medium_page.restore(saved) == []
    assert w.medium_page.snapshot() == saved


# ── a tool's own failure, and a project switch, leave no earlier result on its page ──────
def _wait_until(w, condition, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        w._poll_completed_jobs()
        APP.processEvents()
        time.sleep(0.01)
    w._poll_completed_jobs()
    assert condition()


def _two_runs(root: Path) -> tuple[Path, Path]:
    from cmig.core.engine import SolveResult
    from cmig.core.interactions import build_tidy

    def result(growth: float, ac: float) -> SolveResult:
        return SolveResult(
            objective=growth, member_growth={"A": growth}, abundances={"A": 1.0},
            external_exchange={"ac": ac}, member_exchange={"A": {"ac": ac}},
            status="optimal", flux_report_status="full", growth_solver="gurobi",
            flux_solver="gurobi", members=["A"],
        )

    build_tidy(result(0.5, 5.0)).write(root / "a")
    build_tidy(result(0.8, 2.0)).write(root / "b")
    return root / "a", root / "b"


def test_compare_result_is_on_the_compare_page_and_a_failed_compare_empties_it(
    tmp_path: Path,
) -> None:
    w = build_main_window()
    run_a, run_b = _two_runs(tmp_path)
    w.show_analysis("compare")
    w.scenario_compare.run_a_input.setText(str(run_a))
    w.scenario_compare.run_b_input.setText(str(run_b))
    w.run_scenario_compare()
    assert w.pages.currentWidget() is w.compare_page
    assert w.compare_page.isAncestorOf(w.profile_view)
    assert w.compare_page.results.has_results()
    assert not w.community_builder.results.has_results()
    assert w.scenario_compare.delta_view.rowCount() > 0
    assert w.scenario_compare.growth_label.text()
    w.scenario_compare.run_b_input.setText(str(tmp_path / "not-a-run"))
    w.run_scenario_compare()
    assert not w.compare_page.results.has_results(), "the A vs B overlay is not this request's"
    assert w.scenario_compare.delta_view.rowCount() == 0
    assert w.scenario_compare.growth_label.text() == ""
    assert "completed CMIG runs" in w.scenario_compare.status.text()


def _sandbox_engine(monkeypatch: pytest.MonkeyPatch, outcomes: list[str]) -> None:
    """Each sandbox solve takes the next outcome: "ok" gives a delta, "fail" raises."""
    from types import SimpleNamespace

    import cmig.service
    from cmig.core.delta import DeltaResult, MetaboliteDelta

    class FakeEngineService:
        def sandbox_fixture(self, **_kwargs):
            if outcomes.pop(0) == "fail":
                raise RuntimeError("sandbox solve failed")
            return SimpleNamespace(
                delta=DeltaResult([MetaboliteDelta("ac", 1.0, 2.0, 1.0)], [], [], 0.0),
                run_hash=None,
            )

    monkeypatch.setattr(cmig.service, "EngineService", FakeEngineService)


def _sandbox_preview(w) -> None:
    if not w.sandbox_view.bound_table.rowCount():
        w.sandbox_view.add_bound("EX_glc__D_e", -1.0, 1000.0)
    w.sandbox_view._debounce.stop()
    w.sandbox_view.preview_btn.click()
    _wait_until(w, lambda: not w._sandbox_jobs)


def test_a_failed_sandbox_preview_empties_the_sandbox_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = build_main_window()
    _sandbox_engine(monkeypatch, ["ok", "fail"])
    w.show_analysis("sandbox")
    _sandbox_preview(w)
    assert w.sandbox_page.results.has_results()
    assert w.sandbox_view.delta_view.rowCount() > 0
    _sandbox_preview(w)
    assert "failed" in w.sandbox_view.status.text()
    assert not w.sandbox_page.results.has_results()
    assert w.sandbox_view.delta_view.rowCount() == 0


def test_a_failed_sweep_with_no_rows_leaves_no_earlier_sweep(tmp_path: Path) -> None:
    w = build_main_window()
    w.sweep_view.table.setRowCount(3)  # an earlier sweep's rows

    def boom(_ctx):
        raise RuntimeError("sweep failed")

    jid = w.runner.submit("sweep", boom)
    w._sweep_jobs[jid] = (tmp_path / "no-rows", "real")
    _wait_until(w, lambda: not w._sweep_jobs)
    assert w.sweep_view.table.rowCount() == 0
    assert "failed" in w.sweep_view.status.text()


def _loaded_run(w, root: Path) -> None:
    """A community run on show: profile rows and a graph, as an Open Run leaves them."""
    run_a, _run_b = _two_runs(root)
    assert w.load_run_dir(run_a)
    assert w.profile_view.table.rowCount() > 0
    assert w.graph_view._base_payload["elements"]


def _base_is_blank(w) -> bool:
    return (w.profile_view.table.rowCount() == 0
            and w.profile_view.target_label.text() == ""
            and w.graph_view._base_payload["elements"] == []
            and "NOT RECORDED" in w.graph_gate_badge.text()
            and w.current_manifest is None)


def test_a_compare_overlay_shows_no_unrelated_run_underneath(tmp_path: Path) -> None:
    w = build_main_window()
    _loaded_run(w, tmp_path / "loaded")
    run_a, run_b = _two_runs(tmp_path)
    w.scenario_compare.run_a_input.setText(str(run_a))
    w.scenario_compare.run_b_input.setText(str(run_b))
    w.run_scenario_compare()
    assert w.profile_view.net_chart.delta_active
    assert _base_is_blank(w)
    w.profile_view.clear_delta_btn.click()  # clearing the overlay brings back no other run
    assert not w.profile_view.net_chart.delta_active
    assert w.profile_view.net_chart.rows == []
    assert w.profile_view.table.rowCount() == 0


def test_a_sandbox_overlay_shows_no_unrelated_run_underneath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = build_main_window()
    _loaded_run(w, tmp_path)
    _sandbox_engine(monkeypatch, ["ok"])
    w.show_analysis("sandbox")
    _sandbox_preview(w)
    assert w.profile_view.net_chart.delta_active
    assert _base_is_blank(w)
    w.profile_view.clear_delta_btn.click()
    assert w.profile_view.net_chart.rows == []


def test_a_failed_growth_check_empties_the_medium_result(tmp_path: Path) -> None:
    w = build_main_window()
    w._show_profile("medium")  # an earlier growth check is on show

    def boom(_ctx):
        raise RuntimeError("growth check failed")

    jid = w.runner.submit("medium_growth", boom)
    w._medium_growth_jobs[jid] = (tmp_path, {})
    _wait_until(w, lambda: not w._medium_growth_jobs)
    assert not w.medium_page.results.has_results()


def test_a_failed_run_elsewhere_leaves_the_tool_result_alone(tmp_path: Path) -> None:
    w = build_main_window()
    w._show_profile("compare")

    def boom(_ctx):
        raise RuntimeError("growth check failed")

    jid = w.runner.submit("medium_growth", boom)
    w._medium_growth_jobs[jid] = (tmp_path, {})
    _wait_until(w, lambda: not w._medium_growth_jobs)
    assert w.compare_page.results.has_results()


def test_a_project_switch_empties_the_tool_result_and_drops_the_medium_baseline(
    tmp_path: Path,
) -> None:
    w = build_main_window()
    w._show_profile("sandbox")
    w._last_medium_growth_check = (tmp_path / "old-run", {"models": ["a"]})
    editor = w.medium_editor
    tables = (w.scenario_compare.delta_view, w.sandbox_view.delta_view, w.sweep_view.table,
              editor.minimal_table)
    labels = (w.scenario_compare.growth_label, editor.growth_label, editor.dropped_ids_label,
              editor.profile_delta_label, editor.minimal_status)
    for table in tables:
        table.setRowCount(2)  # results of the previous project
    for label in labels:
        label.setText("from the previous project")
    open_test_project(w, tmp_path / "p", ["a"])
    assert not w.sandbox_page.results.has_results()
    assert w._last_medium_growth_check is None
    assert [table.rowCount() for table in tables] == [0, 0, 0, 0]
    assert [label.text() for label in labels] == [""] * len(labels)


def test_medium_restore_reproduces_the_same_medium() -> None:
    w = build_main_window()
    editor = w.medium_editor
    editor.clear_rows()
    editor.add_row("EX_glc__D_e", 0.0, "nutrient", notify=False)
    editor.add_row("EX_h2o_e", 1000.0, "pool_closure", notify=False)
    editor.add_row("", 0.0, "", notify=False)  # a row the user added and left blank
    editor._update_role_presentation()
    editor.table.item(0, 1).setText("10")  # typed as "10", not "10.0"
    editor.table.item(2, 1).setText("")
    editor.exact_medium_check.setChecked(True)
    editor.nutrients_only_check.setChecked(True)
    uptake = set(editor.to_spec().uptake)
    assert uptake == {"EX_glc__D_e"}, "nutrients-only hides the pool-closure row"
    saved = w.medium_page.snapshot()
    editor.clear_rows()
    editor.add_row("EX_o2_e", 5.0)
    editor.exact_medium_check.setChecked(False)
    assert w.medium_page.restore(saved) == []
    assert w.medium_page.snapshot() == saved
    assert editor.table.item(0, 1).text() == "10"
    assert editor.nutrients_only_check.isChecked()
    assert set(editor.to_spec().uptake) == uptake
