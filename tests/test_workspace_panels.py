from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.activity import ActivityPane, command_line  # noqa: E402
from cmig.gui.inspector import InspectorPanel  # noqa: E402
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
