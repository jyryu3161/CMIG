from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.activity import ActivityPane, command_line  # noqa: E402
from cmig.gui.inspector import InspectorPanel, _row  # noqa: E402
from cmig.gui.project_session import RunEntry  # noqa: E402
from cmig.service.jobrunner import JobRunner  # noqa: E402

APP = QApplication.instance() or QApplication([])


def test_model_inspector_shows_counts_checksum_and_filters_exchanges(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["E_rectale"])
    entry = project.model("E_rectale")
    panel = InspectorPanel()
    panel.show_model(project, entry, ["EX_but_e", "EX_ac_e", "EX_glc__D_e"])
    text = panel.details.toPlainText()
    assert "E_rectale" in panel.title_label.text()
    assert "10 reactions" in text and entry.sha256[:12] in text and "99.0%" in text
    panel.exchange_filter.setText("but")
    visible = [panel.exchange_list.item(i).text() for i in range(panel.exchange_list.count())
               if not panel.exchange_list.item(i).isHidden()]
    assert visible == ["EX_but_e"]
    assert panel.current_path() == project.root / entry.file


def test_model_inspector_marks_changed_copy(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    entry.integrity = "changed"
    panel = InspectorPanel()
    panel.show_model(project, entry, None)
    assert "changed since it was added" in panel.details.toPlainText()
    assert panel.exchange_list.count() == 0


def test_run_inspector_shows_status_integrity_solver_and_command(tmp_path: Path) -> None:
    panel = InspectorPanel()
    entry = RunEntry(tmp_path, "search-20261013-103100", "search", "degraded", "Search", 1.0)
    inspected = {"status": "degraded", "artifact_integrity": "verified",
                 "run_hash": "abc123", "manifest": {"solver": "osqp"}}
    panel.show_run(entry, inspected, "cmig search --taxonomy t.csv --out runs/x")
    text = panel.details.toPlainText()
    assert "degraded" in text and "verified" in text and "abc123" in text
    assert "OSQP QP-only approximation" in text
    assert panel.current_command() == "cmig search --taxonomy t.csv --out runs/x"


def _solver_text(manifest: object) -> str:
    panel = InspectorPanel()
    entry = RunEntry(Path("/tmp/x"), "solve-20261013-103100", "solve", "ok", "Solve", 1.0)
    inspected: dict[str, object] = {"status": "ok"}
    if manifest is not None:
        inspected["manifest"] = manifest
    panel.show_run(entry, inspected, "cmig solve")
    return next(line for line in panel.details.toPlainText().splitlines()
                if line.startswith("Solver"))


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        # Real solve manifest shapes (cmig.io.solve_output): solver is a dict.
        ({"solver": {"flux_report_status": "full", "flux_solver": "gurobi",
                     "growth_solver": "gurobi"}}, "Solver: Gurobi full-flux"),
        ({"solver": {"flux_report_status": "qp_only_approximate", "flux_solver": None,
                     "growth_solver": "osqp"}}, "Solver: OSQP QP-only approximation"),
        # Degraded tiers must not borrow the full-flux wording.
        ({"solver": {"flux_report_status": "fba_non_parsimonious", "flux_solver": "gurobi",
                     "growth_solver": "gurobi"}},
         "Solver: Full flux, NON-parsimonious (pFBA stage failed)"),
        ({"solver": {"flux_report_status": "none", "flux_solver": "gurobi",
                     "growth_solver": "gurobi"}}, "Solver: No flux (solve failed)"),
        # Plain string, and the workflow shape: solver_setting component of `components`.
        ({"solver": "gurobi"}, "Solver: Gurobi full-flux"),
        ({"solver": "osqp"}, "Solver: OSQP QP-only approximation"),
        ({"components": [["workflow_kind", "search"], ["solver_setting", {"solver": "gurobi"}]]},
         "Solver: Gurobi full-flux"),
        ({"components": [["solver_setting", {"solver": "osqp"}]]},
         "Solver: OSQP QP-only approximation"),
        # Not recorded: absent, null, unknown tier, unknown name. Never a raw repr.
        (None, "Solver: not recorded"),
        ({}, "Solver: not recorded"),
        ({"solver": None}, "Solver: not recorded"),
        ({"components": [["solver_setting", {"solver": None}]]}, "Solver: not recorded"),
        ({"solver": {"flux_report_status": "mystery", "flux_solver": "x"}},
         "Solver: not recorded"),
        ({"solver": "cplex"}, "Solver: not recorded"),
        ({"solver": 3}, "Solver: not recorded"),
    ],
)
def test_run_inspector_solver_label_from_real_manifest_shapes(
    manifest: object, expected: str
) -> None:
    assert _solver_text(manifest) == expected


def test_unrecorded_values_read_not_recorded_never_zero(tmp_path: Path) -> None:
    for empty in (None, "", []):
        assert "<b>x</b>: not recorded<br>" in _row("x", empty)
    assert "<b>x</b>: 0<br>" in _row("x", 0)
    assert "<b>x</b>: 0.0<br>" in _row("x", 0.0)

    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    entry.n_reactions = entry.n_metabolites = entry.n_genes = None
    entry.namespace_coverage_pct = None
    entry.biomass = []
    entry.sha256 = ""
    panel = InspectorPanel()
    panel.show_model(project, entry, None)
    lines = panel.details.toPlainText().splitlines()
    assert "Size: not recorded" in lines
    assert "BiGG namespace coverage: not recorded" in lines
    assert "Biomass: not recorded" in lines
    assert "SHA-256: not recorded" in lines  # not a bare ellipsis
    assert not any("0 reactions" in line for line in lines)

    entry.n_reactions, entry.n_metabolites, entry.n_genes = 0, 0, 0
    entry.namespace_coverage_pct = 0.0
    panel.show_model(project, entry, None)
    lines = panel.details.toPlainText().splitlines()
    assert "Size: 0 reactions · 0 metabolites · 0 genes" in lines
    assert "BiGG namespace coverage: 0.0%" in lines

    run = RunEntry(tmp_path, "search-20261013-103100", "search", "ok", "Search", 1.0)
    panel.show_run(run, {"run_hash": "", "artifact_integrity": None}, "")
    lines = panel.details.toPlainText().splitlines()
    assert "run_hash: not recorded" in lines
    assert "Artifact integrity: not recorded" in lines


def test_title_is_plain_text_not_markup(tmp_path: Path) -> None:
    panel = InspectorPanel()
    run = RunEntry(tmp_path, "search-20261013-103100", "search", "ok", "<b>bold</b> run", 1.0)
    panel.show_run(run, {}, "")
    assert panel.title_label.textFormat() == Qt.TextFormat.PlainText
    assert panel.title_label.text() == "Run · <b>bold</b> run"
    panel.show_analysis("<i>x</i>", "d", "cmig x")
    assert panel.title_label.text() == "<i>x</i>"


def test_medium_inspector_lists_rows_and_source(tmp_path: Path) -> None:
    source = tmp_path / "diet.csv"
    source.write_text("exchange,uptake\n")
    panel = InspectorPanel()
    panel.show_medium("diet", [("EX_glc__D_e", "10.0"), ("EX_o2_e", "<b>0</b>")], str(source))
    text = panel.details.toPlainText()
    assert panel.title_label.text() == "Medium · diet"
    assert str(source) in text
    assert "EX_glc__D_e" in text and "10.0" in text and "EX_o2_e" in text
    assert "<b>0</b>" in text  # escaped, shown literally
    assert not panel.exchange_list.isVisibleTo(panel)
    assert panel.current_path() == source and panel.current_command() == ""
    assert panel.reveal_btn.isEnabled() and not panel.copy_command_btn.isEnabled()
    panel.show_medium("gone", [], str(tmp_path / "missing.csv"))
    assert panel.current_path() is None and not panel.reveal_btn.isEnabled()


def test_analysis_inspector_shows_description_and_cli() -> None:
    panel = InspectorPanel()
    panel.show_analysis("Search", "Rank <member> sets.", "cmig search --target but")
    text = panel.details.toPlainText()
    assert panel.title_label.text() == "Search"
    assert "Rank <member> sets." in text and "CLI: cmig search --target but" in text
    assert panel.current_command() == "" and panel.current_path() is None
    assert not panel.copy_command_btn.isEnabled() and not panel.reveal_btn.isEnabled()


def test_clear_resets_title_exchanges_and_buttons(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    panel = InspectorPanel()
    panel.show_model(project, project.model("a"), ["EX_but_e"])
    assert panel.exchange_list.isVisibleTo(panel) and panel.exchange_list.count() == 1
    assert panel.reveal_btn.isEnabled()
    panel.clear()
    assert panel.title_label.text() == "Nothing selected"
    assert "Select a model" in panel.details.toPlainText()
    assert panel.exchange_list.count() == 0
    assert not panel.exchange_list.isVisibleTo(panel)
    assert not panel.exchange_filter.isVisibleTo(panel)
    assert not panel.copy_command_btn.isEnabled() and not panel.reveal_btn.isEnabled()
    assert panel.current_command() == "" and panel.current_path() is None


def test_copy_command_puts_it_on_the_clipboard(tmp_path: Path) -> None:
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("before")
    panel = InspectorPanel()
    run = RunEntry(tmp_path, "search-20261013-103100", "search", "ok", "Search", 1.0)
    panel.show_run(run, {}, "cmig search --out 'a b'")
    assert panel.copy_command_btn.isEnabled()
    panel.copy_command_btn.click()
    assert clipboard.text() == "cmig search --out 'a b'"


def test_activity_pane_cancel_and_command() -> None:
    runner = JobRunner(max_workers=1)
    pane = ActivityPane()
    requested: list[str] = []
    pane.cancel_requested.connect(requested.append)
    jid = runner.submit("demo", lambda ctx: {"ok": True})
    pane.jobs.refresh(runner, [jid])
    pane.jobs.selectRow(0)
    pane.cancel_btn.click()
    assert requested == [jid]
    pane.set_job_detail("line1\nline2", command_line(["search", "--out", "a b"]))
    assert pane.command_label.text() == "cmig search --out 'a b'"
    assert pane.log_view.toPlainText() == "line1\nline2"
    runner.shutdown(wait=True)


def test_job_rows_show_a_given_status_label_instead_of_the_runner_status() -> None:
    runner = JobRunner(max_workers=1)
    pane = ActivityPane()
    jid = runner.submit("demo", lambda ctx: {"ok": True})
    runner.result(jid, timeout=5)
    pane.jobs.refresh(runner, [jid])
    assert pane.jobs.item(0, 2).text() == "done"
    pane.jobs.refresh(runner, [jid], status_labels={jid: "cancelled (2 of 5 not imported)"})
    assert pane.jobs.item(0, 2).text() == "cancelled (2 of 5 not imported)"
    runner.shutdown(wait=True)


def test_job_rows_name_the_job_for_people_not_by_its_internal_kind() -> None:
    runner = JobRunner(max_workers=1)
    pane = ActivityPane()
    jids = [runner.submit(kind, lambda ctx: None)
            for kind in ("search_fixture", "import_models", "agora2_fetch", "gene_ko_search",
                         "something_new")]
    for jid in jids:
        runner.result(jid, timeout=5)
    pane.jobs.refresh(runner, jids)
    kinds = [pane.jobs.item(row, 1).text() for row in range(len(jids))]
    assert kinds == ["Search", "Import Models", "AGORA2 Download", "Gene KO", "something_new"]
    runner.shutdown(wait=True)
