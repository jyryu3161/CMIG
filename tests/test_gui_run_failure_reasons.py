"""A failed GUI run says why it failed, in the user's terms.

User report: the dFBA page showed ``dFBA failed: {"code": "solver_error", ...
"RuntimeError: dFBA failed with rc=2"}`` — the CLI's own reason ("dfba input error: --initial
exchange ids not found in model: [...]") was lost and an input refusal was labelled a solver
error. Search showed "pass --allow-failed-run to exit 0 anyway", a CLI-only hint, instead of
the per-candidate diagnostics its published run folder already held.
"""

from __future__ import annotations

import json
import os
import sys
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

from cmig.core.diagnostics import parse_diagnostic  # noqa: E402
from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402

APP = QApplication.instance() or QApplication([])

CLI_HINT = (
    "  analysis failed: artifacts were written to /x/.stage-abc/run but the scientific solve "
    "did not succeed (exit 3); pass --allow-failed-run to exit 0 anyway\n"
)
MEDIUM_DIAGNOSTIC = (
    "medium exchange has no counterpart in the target model (matched on metabolite): "
    "['EX_26dap__M_m', 'EX_4abz_m']"
)


# ── the shared, Qt-free helpers ────────────────────────────────────────────────────────────────


def test_cli_error_text_drops_cli_only_hints_and_license_banners():
    from cmig.gui.run_failure import cli_error_text

    text = cli_error_text([
        "Set parameter Username\n",
        "Academic license - for non-commercial use only - expires 2027-05-27\n",
        "dfba input error: --initial exchange ids not found in model: ['EX_glc__D_e']\n",
        CLI_HINT,
    ])
    assert text == "dfba input error: --initial exchange ids not found in model: ['EX_glc__D_e']"
    assert cli_error_text([CLI_HINT]) == ""


def test_ranked_failure_reason_counts_and_names_the_most_common_cause():
    from cmig.gui.run_failure import ranked_failure_reason

    other = json.dumps({"code": "infeasible", "message": "community maximum growth is 0"})
    summary = {
        "n_candidates_total": 4,
        "unevaluated": [
            {"members": ["a", "b"], "status": "failed", "diagnostic": MEDIUM_DIAGNOSTIC},
            {"members": ["a", "c"], "status": "failed", "diagnostic": MEDIUM_DIAGNOSTIC},
            {"members": ["b", "c"], "status": "failed", "diagnostic": MEDIUM_DIAGNOSTIC},
            {"members": ["c", "d"], "status": "non_viable", "diagnostic": other},
        ],
    }
    reason = ranked_failure_reason(summary)
    assert reason.startswith("4 of 4 candidates could not be evaluated: ")
    assert "medium exchange has no counterpart" in reason
    assert "(3 of 4)" in reason
    long = {"unevaluated": [{"members": ["a"], "diagnostic": "x" * 1000}]}
    assert len(ranked_failure_reason(long)) < 300
    assert ranked_failure_reason({"unevaluated": []}) == ""


def test_an_input_refusal_is_not_a_solver_error():
    from cmig.service.jobrunner import JobInputError

    runner = JobRunner(max_workers=1)

    def job(_ctx):
        raise JobInputError("dfba input error: bad --initial (rc=2)")

    jid = runner.submit("dfba", job)
    deadline = time.time() + 5
    while runner.poll(jid).status not in (JobStatus.FAILED, JobStatus.DONE):
        assert time.time() < deadline
        time.sleep(0.01)
    diagnostic = parse_diagnostic(runner.poll(jid).error)
    assert diagnostic["code"] == "input_error"
    assert diagnostic["message"] == "dfba input error: bad --initial (rc=2)"
    runner.shutdown()


# ── pages ──────────────────────────────────────────────────────────────────────────────────────


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


def test_dfba_page_shows_the_cli_reason_for_an_input_refusal(w, monkeypatch):
    reason = "dfba input error: --initial exchange ids not found in model: ['EX_glc__D_e']"

    def fake_main(argv):
        print(reason, file=sys.stderr)
        return 2

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    w.dynamics_view.model_picker.set_selected(["a"])
    jid = w.run_dfba()
    assert jid
    _settle(w, jid)
    assert parse_diagnostic(w.runner.poll(jid).error)["code"] == "input_error"
    shown = w.dynamics_view.status.text()
    assert shown == f"dFBA failed: {reason} (rc=2)", shown
    assert "solver_error" not in shown and '{"code"' not in shown


@pytest.mark.parametrize("driver", ["spatial", "community", "host", "strain_growth"])
def test_other_pages_show_the_cli_reason_too(w, monkeypatch, driver):
    from argv_drivers import DRIVERS

    reason = f"{driver} input error: something specific the CLI said"

    def fake_main(argv):
        print(reason, file=sys.stderr)
        return 2

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    jid = DRIVERS[driver](w)
    assert jid
    _settle(w, jid)
    assert parse_diagnostic(w.runner.poll(jid).error)["code"] == "input_error"
    page = {
        "spatial": lambda: w.spatial_page.status.text(),
        "community": lambda: w.community_builder.status.text(),
        "host": lambda: w.host_view.run_status.text(),
        "strain_growth": lambda: w.strain_growth_page.status.text(),
    }[driver]()
    assert reason in page, page


def _failed_search_run(out: Path, n: int = 3) -> None:
    out.mkdir(parents=True, exist_ok=True)
    pairs = [["a", "b"], ["a", "host"], ["b", "host"]][:n]
    summary = {
        "status": "failed", "target": "but", "target_exchange": "EX_but_m",
        "direction": "max_secretion", "strategy": "exhaustive", "n_pool_members": 3,
        "n_candidates_total": n, "n_candidates_evaluated": n, "n_candidates_ranked": 0,
        "n_candidates_failed": n, "top_ranked": [],
        "unevaluated": [
            {"members": m, "status": "failed", "diagnostic": MEDIUM_DIAGNOSTIC} for m in pairs
        ],
        "warnings": [f"{n} of {n} candidates could not be evaluated"],
    }
    (out / "search_summary.json").write_text(json.dumps(summary))
    (out / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "model_pool_search", "status": "failed",
        "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(out, "model_pool_search", ["search_summary.json"]),
    }))


def test_failed_search_says_why_and_never_shows_the_cli_flag(w, monkeypatch):
    def fake_main(argv):
        _failed_search_run(Path(argv[argv.index("--out") + 1]))
        print(CLI_HINT, file=sys.stderr, end="")
        return 3

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    w.search_view.model_picker.set_selected(["a", "b", "host"])
    jid = w.run_search_fixture()
    assert jid
    _settle(w, jid)
    status = w.search_view.status.text()
    details = w.search_view.details.toPlainText()
    assert "3 of 3 candidates could not be evaluated: medium exchange has no counterpart" in status
    assert "--allow-failed-run" not in status and "--allow-failed-run" not in details
    assert "Unevaluated 1:" in details and "EX_26dap__M_m" in details
    assert "status: failed" in details or "status: failed" in status
    assert w.search_view.table.rowCount() == 0  # a failed run is never shown as a ranking


def test_failed_host_search_reads_its_published_summary(w, monkeypatch):
    from argv_drivers import DRIVERS

    def fake_main(argv):
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        summary = {
            "status": "failed", "metric": "objective_value", "target": "but",
            "n_candidates_total": 2, "n_candidates_evaluated": 0, "n_candidates_failed": 2,
            "top_ranked": [], "warnings": ["no candidate was evaluable; the ranking is empty"],
            "unevaluated": [
                {"members": ["a"], "evaluation_status": "failed",
                 "diagnostic": "microbial medium exchange has no counterpart: ['EX_x_m']"},
                {"members": ["b"], "evaluation_status": "failed",
                 "diagnostic": "microbial medium exchange has no counterpart: ['EX_x_m']"},
            ],
        }
        (out / "host_search_summary.json").write_text(json.dumps(summary))
        (out / "manifest.json").write_text(json.dumps({
            "manifest_scope": "workflow", "manifest_schema_version": "1.2",
            "workflow_kind": "host_search_bigg", "status": "failed",
            "artifacts": ["host_search_summary.json"],
            "result_digest": artifact_result_digest(
                out, "host_search_bigg", ["host_search_summary.json"]
            ),
        }))
        print(CLI_HINT, file=sys.stderr, end="")
        return 3

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    jid = DRIVERS["host_search"](w)
    assert jid
    _settle(w, jid)
    page = w.host_search_page
    status = page.status.text()
    assert "2 of 2 candidates could not be evaluated: microbial medium exchange" in status, status
    assert "--allow-failed-run" not in status
    details = page.results_panel.details.toPlainText()
    assert "Unevaluated 1:" in details and "--allow-failed-run" not in details
    assert page.results_panel.table.rowCount() == 0


# ── review round 1 ─────────────────────────────────────────────────────────────────────────────


def _publish(out: Path, name: str, kind: str, summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(summary))
    (out / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": kind, "status": "failed", "artifacts": [name],
        "result_digest": artifact_result_digest(out, kind, [name]),
    }))


def test_failed_strain_growth_shows_no_ranking_rows_and_the_cli_reason(w, monkeypatch):
    from argv_drivers import DRIVERS

    reason = "strain-growth: the community solve did not reach an optimum (status=infeasible)"

    def fake_main(argv):
        _publish(Path(argv[argv.index("--out") + 1]), "strain_growth_summary.json",
                 "strain_growth", {
                     "status": "failed", "warnings": ["community solve was not optimal"],
                     "members": [
                         {"member": "a", "single_growth": 0.4, "single_status": "optimal",
                          "community_member_growth": None, "community_growth": None,
                          "community_status": "infeasible", "diagnostic": None},
                         {"member": "b", "single_growth": 0.2, "single_status": "optimal",
                          "community_member_growth": None, "community_growth": None,
                          "community_status": "infeasible", "diagnostic": None},
                     ],
                 })
        print(reason, file=sys.stderr)
        print(CLI_HINT, file=sys.stderr, end="")
        return 3

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    jid = DRIVERS["strain_growth"](w)
    _settle(w, jid)
    page = w.strain_growth_page
    assert page.results_panel.table.rowCount() == 0, "a failed run is never shown as a ranking"
    status = page.status.text()
    assert reason in status and "--allow-failed-run" not in status, status
    details = page.results_panel.details.toPlainText()
    assert "Not ranked 1 (the run failed):" in details, details
    assert "status: failed" in details


def test_failed_ratio_impact_without_a_cli_reason_names_the_runs_own_warning(w, monkeypatch):
    from argv_drivers import DRIVERS

    def fake_main(argv):
        _publish(Path(argv[argv.index("--out") + 1]), "abundance_impact_summary.json",
                 "abundance_impact", {
                     "status": "failed", "target": "but", "target_member": "b",
                     "warnings": ["no abundance point solved: every point was infeasible"],
                     "rows": [{"target_member": "b", "target_abundance": 0.2, "status": "failed",
                               "diagnostic": "infeasible", "community_growth": None}],
                 })
        print(CLI_HINT, file=sys.stderr, end="")
        return 3

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    jid = DRIVERS["ratio_impact"](w)
    _settle(w, jid)
    page = w.ratio_impact_page
    assert page.results_panel.table.rowCount() == 0
    status = page.status.text()
    assert "no abundance point solved: every point was infeasible" in status, status
    assert "--allow-failed-run" not in status


def test_check_growth_input_refusal_is_an_input_error(w, monkeypatch):
    reason = ("medium exchange has no counterpart in the target model (matched on metabolite): "
              "['EX_fru_e']")

    def fake_main(argv):
        print(reason, file=sys.stderr)
        return 2

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    w.session.confirm_namespace("a")
    w.sidebar.select("models", "a")
    jid = w.run_check_growth("a")
    assert jid
    _settle(w, jid)
    diagnostic = parse_diagnostic(w.runner.poll(jid).error)
    assert diagnostic["code"] == "input_error"
    assert reason in diagnostic["message"]


def test_job_error_text_strips_any_exception_type_prefix():
    from cmig.gui.run_failure import job_error_text

    for kind in ("RuntimeError", "ArtifactJobFailure", "ModelImportError", "SystemExit"):
        raw = json.dumps({"code": "solver_error", "message": f"{kind}: the reason",
                          "detail": {"exc_type": kind}})
        assert job_error_text(raw) == "the reason", kind
    assert job_error_text(json.dumps({"code": "x", "message": "ValueError: why"})) == "why"
    assert job_error_text("Note: a plain sentence") == "Note: a plain sentence"


def test_the_stderr_router_is_not_installed_over_a_missing_stderr(monkeypatch):
    from cmig.gui import app as gui_app

    monkeypatch.setattr(sys, "stderr", None)
    gui_app._install_stderr_router()
    assert sys.stderr is None


# ── fix round 2: both "not applicable" records reach the result details ───────────────────────


def test_result_details_show_both_not_applicable_records(w):
    summary = {
        "status": "ok", "strategy": "exhaustive", "top_ranked": [], "warnings": [],
        "medium_not_applicable": {"ids": ["EX_but_m"], "n_candidates": 1},
        "medium_not_applicable_to_pool": ["EX_notreal_m"],
    }
    w.search_view.load_summary(summary, workflow_kind="search")
    details = w.search_view.details.toPlainText()
    assert "medium_not_applicable: {'ids': ['EX_but_m'], 'n_candidates': 1}" in details
    assert "medium_not_applicable_to_pool: ['EX_notreal_m']" in details


def test_ranked_pages_carry_the_pool_record_through_their_adapter():
    from cmig.gui.app import _host_search_summary_for_search_view, _with_search_conditions

    payload = {"top_ranked": [], "warnings": [], "medium_not_applicable_to_pool": ["EX_x_m"]}
    shown = _with_search_conditions(_host_search_summary_for_search_view(payload), payload)
    assert shown["medium_not_applicable_to_pool"] == ["EX_x_m"]
