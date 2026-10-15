"""GUI: medium ids no selected model can take up are shown, never silent (round 11).

The Community Solve page itself takes no medium (its argv is members, abundances, tradeoff and
the namespace policy); the GUI's `cmig solve --medium` is the Medium page's Check Growth, and the
model browser's Check Growth is `cmig single --fba`. Those, and the ranked and host pages, show the
`medium_not_applicable_to_pool` list and the matched fraction their run recorded.
"""

from __future__ import annotations

import json
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402

APP = QApplication.instance() or QApplication([])

POOL_NA = ["EX_notreal_m", "EX_x_m"]
MATCHED = {"matched": 8, "requested": 10, "fraction": 0.8}


def _settle(w, jid: str) -> None:
    deadline = time.time() + 15
    while w.runner.poll(jid).status not in (
        JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED
    ) and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    w._poll_completed_jobs()


@pytest.fixture
def w(tmp_path: Path):
    window = build_main_window(runner=JobRunner(max_workers=1))
    open_test_project(window, tmp_path / "p", ["a", "b", "host"])
    yield window
    window.close_project()


def _stub_graph(monkeypatch) -> None:
    from PySide6.QtWidgets import QWidget

    import cmig.gui.app as app_module
    import cmig.gui.graph_view as graph_view_module

    class GraphStub(QWidget):
        def set_bundle(self, _bundle, gate=None):
            return None

        def set_payload(self, _payload):
            return None

        def clear(self):
            return None

    monkeypatch.setattr(app_module, "InteractionGraphView", GraphStub)
    monkeypatch.setattr(graph_view_module, "InteractionGraphView", GraphStub)


def test_medium_page_check_growth_names_the_not_applicable_ids_and_the_match(w, monkeypatch):
    _stub_graph(monkeypatch)

    def fake_main(argv):
        assert argv[0] == "solve" and "--medium" in argv
        out = Path(argv[argv.index("--out") + 1])
        result = SolveResult(
            objective=0.5, member_growth={"a": 0.5}, abundances={"a": 1.0},
            external_exchange={"ac": 1.0}, member_exchange={"a": {"ac": 1.0}},
            status="optimal", flux_report_status="full", growth_solver="gurobi",
            flux_solver="gurobi", members=["a"],
        )
        build_tidy(result).write(out)
        (out / "manifest.json").write_text(json.dumps({
            "run_hash": "run-1", "diagnostic": None,
            "provenance": {"medium_not_applicable_to_pool": POOL_NA, "medium_matched": MATCHED},
        }))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    editor = w.medium_editor
    editor.model_picker.set_selected(["a"])
    editor.assume_bigg_check.setChecked(True)
    editor.exact_medium_check.setChecked(True)
    editor.add_row("EX_glc__D_m", 3.0)
    jid = w.run_medium_growth_check()
    assert jid
    _settle(w, jid)
    shown = editor.dropped_ids_label.text()
    assert "Not applicable to the selected models (2): EX_notreal_m, EX_x_m" in shown, shown
    assert "medium ids matched: 8/10" in shown, shown


def _publish(out: Path, name: str, kind: str, summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(summary))
    (out / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": kind, "status": summary["status"], "artifacts": [name],
        "result_digest": artifact_result_digest(out, kind, [name]),
    }))


def test_strain_growth_page_status_names_the_not_applicable_ids(w, monkeypatch):
    from argv_drivers import DRIVERS

    def fake_main(argv):
        _publish(Path(argv[argv.index("--out") + 1]), "strain_growth_summary.json",
                 "strain_growth", {
                     "status": "ok", "warnings": [], "community_status": "optimal",
                     "medium_not_applicable_to_pool": POOL_NA, "medium_matched": MATCHED,
                     "members": [
                         {"member": "a", "single_growth": 0.4, "single_status": "optimal",
                          "community_member_growth": 0.3, "community_growth": 0.5,
                          "community_status": "optimal", "diagnostic": None},
                     ],
                 })
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    jid = DRIVERS["strain_growth"](w)
    _settle(w, jid)
    panel = w.strain_growth_page.results_panel
    shown = w.strain_growth_page.status.text() + " " + panel.status.text()
    assert "2 medium ids not applicable to this pool" in shown, shown
    assert "medium_matched: {'matched': 8" in panel.details.toPlainText()


def test_host_page_status_names_the_not_applicable_ids(w):
    w.host_view.load_bigg_summary({
        "warnings": [], "medium_not_applicable_to_pool": POOL_NA, "medium_matched": MATCHED,
        "microbial_secretion": {}, "host": {}, "microbe_to_host": {},
    })
    status = w.host_view.run_status.text()
    assert "2 microbial medium ids not applicable to the selected models" in status, status
    assert "EX_notreal_m" in status and "8/10" in status, status


def test_model_browser_growth_reading_names_the_not_applicable_ids(tmp_path):
    from cmig.gui.growth import read_growth

    run = tmp_path / "check-growth-20261015-103100"
    run.mkdir()
    (run / "single_summary.json").write_text(json.dumps({
        "status": "ok", "solver": "gurobi", "growth_feasible": True, "growth_threshold": 1e-6,
        "warnings": [], "methods": {"FBA": {"status": "optimal", "objective": 0.8739}},
        "medium_not_applicable_to_pool": POOL_NA, "medium_matched": MATCHED,
    }))
    reading = read_growth(run, objective_warning=None, medium="gut (exact)", finished="10:31")
    assert reading.symbol == "✓"
    assert reading.text.startswith("Growth 0.8739 h⁻¹")
    assert "2 medium ids not applicable to this model (EX_notreal_m, EX_x_m)" in reading.text
    assert "8/10 matched" in reading.text


def test_medium_page_check_growth_never_reads_a_failed_solve_as_optimal(w, monkeypatch):
    """Reachable since round 11: {iAF987, iHN637, iYO844} on the gut overlay is no longer refused
    (exit 2) but solved, and fails (exit 3, solver_failed). The artifacts exist, so the page used
    to reconstruct "growth: 0 · status: optimal" from them."""
    _stub_graph(monkeypatch)

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        result = SolveResult(
            objective=0.0, member_growth={"a": 0.0}, abundances={"a": 1.0},
            external_exchange={}, member_exchange={"a": {}},
            status="solver_failed", flux_report_status="none", growth_solver="gurobi",
            flux_solver="gurobi", members=["a"],
        )
        build_tidy(result).write(out)
        (out / "manifest.json").write_text(json.dumps({
            "run_hash": "run-f", "diagnostic": json.dumps({
                "code": "solver_error", "message": "could not get community growth rate."}),
            "provenance": {"medium_not_applicable_to_pool": POOL_NA, "medium_matched": MATCHED},
        }))
        return 3

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    editor = w.medium_editor
    editor.model_picker.set_selected(["a"])
    editor.assume_bigg_check.setChecked(True)
    editor.exact_medium_check.setChecked(True)
    editor.add_row("EX_glc__D_m", 3.0)
    jid = w.run_medium_growth_check()
    _settle(w, jid)
    shown = editor.growth_label.text()
    assert "optimal" not in shown and "growth: 0" not in shown, shown
    assert "failed" in shown, shown
    # the medium record is still shown for the failed run
    assert "Not applicable to the selected models (2)" in editor.dropped_ids_label.text()


# ── review round 5 ─────────────────────────────────────────────────────────────────────────────


def _tidy_run(path: Path, *, failed: bool) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if failed:
        result = SolveResult(
            objective=0.0, member_growth={}, abundances={}, external_exchange={},
            member_exchange={}, status="solver_failed", flux_report_status="none",
            growth_solver="gurobi", flux_solver="gurobi", members=[],
        )
    else:
        result = SolveResult(
            objective=0.5, member_growth={"a": 0.5}, abundances={"a": 1.0},
            external_exchange={"ac": 1.0}, member_exchange={"a": {"ac": 1.0}},
            status="optimal", flux_report_status="full", growth_solver="gurobi",
            flux_solver="gurobi", members=["a"],
        )
    build_tidy(result).write(path)
    (path / "manifest.json").write_text(json.dumps({
        "run_hash": "r-failed" if failed else "r-ok",
        "diagnostic": json.dumps({"code": "solver_error", "message": "no growth"})
        if failed else None,
        "provenance": {"medium_not_applicable_to_pool": POOL_NA, "medium_matched": MATCHED},
    }))
    return path


def test_a_failed_solve_run_is_never_read_back_as_optimal(tmp_path):
    from cmig.gui.app import _solve_result_like_from_run_dir

    failed = _solve_result_like_from_run_dir(_tidy_run(tmp_path / "f", failed=True))
    assert failed.status != "optimal"


def test_scenario_compare_refuses_a_failed_side(w, monkeypatch, tmp_path):
    _stub_graph(monkeypatch)
    good = _tidy_run(tmp_path / "good", failed=False)
    bad = _tidy_run(tmp_path / "bad", failed=True)
    w.scenario_compare.run_a_input.setText(str(bad))
    w.scenario_compare.run_b_input.setText(str(good))
    w.run_scenario_compare()
    status = w.scenario_compare.status.text()
    assert "compare complete" not in status, status
    assert "did not solve" in status and "bad" in status, status
    assert w.profile_view.net_chart.delta_active is False


def test_reopening_a_failed_medium_run_says_failed_and_shows_the_medium_notes(w, monkeypatch,
                                                                             tmp_path):
    _stub_graph(monkeypatch)
    run = _tidy_run(tmp_path / "medium-growth-x", failed=True)
    w.load_run_dir(run, host_key="medium")
    bar = w.statusBar().currentMessage()
    assert "failed" in bar.lower() and "Loaded run:" not in bar, bar
    notes = w.medium_editor.dropped_ids_label.text()
    assert "Not applicable to the selected models (2)" in notes and "8/10" in notes, notes


def test_reopening_an_ok_medium_run_shows_the_medium_notes(w, monkeypatch, tmp_path):
    _stub_graph(monkeypatch)
    run = _tidy_run(tmp_path / "medium-growth-y", failed=False)
    w.load_run_dir(run, host_key="medium")
    assert "Loaded run:" in w.statusBar().currentMessage()
    assert "medium ids matched: 8/10" in w.medium_editor.dropped_ids_label.text()


def test_allow_unknown_controls_describe_what_they_still_do(w):
    from cmig.gui.growth import MISMATCHED_MEDIUM_OPTION, medium_text

    for text in (
        w.model_browser.skip_unknown_check.text(),
        w.medium_editor.allow_unknown_check.text(),
        w.sweep_view.allow_unknown_medium_check.text(),
    ):
        assert "lacks" not in text and "report every dropped" not in text, text
        assert "mismatched medium" in text.lower(), text
    assert w.model_browser.skip_unknown_check.text() == MISMATCHED_MEDIUM_OPTION
    assert "skipped" not in medium_text("preset:western_diet", skip_unknown=True)
    assert "always" in w.model_browser.skip_unknown_check.toolTip()


def test_korean_catalogue_carries_the_same_english_wording():
    window = build_main_window(runner=JobRunner(max_workers=1), lang="ko")
    try:
        assert "mismatched medium" in window.medium_editor.allow_unknown_check.text().lower()
        assert "mismatched medium" in window.sweep_view.allow_unknown_medium_check.text().lower()
    finally:
        window.runner.shutdown()


@pytest.mark.parametrize(("reason", "expected"), [
    ("medium exchange ids written in another notation of exchanges the selected models have "
     "(VMH `glc_D`/`(e)` vs BiGG `glc__D`/`_e`): EX_glc_D_m -> EX_glc__D_m, EX_ala_L_m -> "
     "EX_ala__L_m. rename them",
     "rename EX_glc_D_m to EX_glc__D_m, EX_ala_L_m to EX_ala__L_m in the medium file"),
    ("none of the medium's 2 exchange ids matches an exchange of the model (matched on "
     "metabolite)", "write the medium in this model's namespace"),
])
def test_refusal_hint_says_what_to_fix(reason, expected):
    from cmig.gui.growth import medium_refusal_hint

    hint = medium_refusal_hint(reason)
    assert expected in hint, hint
    assert "lacks" not in hint
    assert medium_refusal_hint("some solver error") == ""
