from __future__ import annotations

import json
import os
import threading
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

from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402

APP = QApplication.instance() or QApplication([])

_TERMINAL = (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)


def _runs(w) -> list[str]:
    """The RUNS rows exactly as the sidebar shows them."""
    group = w.sidebar.topLevelItem(3)
    return [group.child(i).text(0) for i in range(group.childCount())]


def _settle(w, jid: str) -> None:
    deadline = time.time() + 10
    while w.runner.poll(jid).status not in _TERMINAL and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    assert w.runner.poll(jid).status in _TERMINAL
    w._poll_completed_jobs()


class _Main:
    """Stand-in for `cmig.cli.main.main`: optionally leaves a partial file, then returns `rc`."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, rc: int, partial: str | None = None):
        import cmig.cli.main

        self.rc, self.partial = rc, partial
        self.started, self.release = threading.Event(), threading.Event()
        self.release.set()
        monkeypatch.setattr(cmig.cli.main, "main", self)

    def __call__(self, argv: list[str]) -> int:
        self.started.set()
        assert self.release.wait(10)
        if self.partial is not None:
            (Path(argv[argv.index("--out") + 1]) / self.partial).write_text("partial")
        return self.rc


@pytest.fixture
def w(tmp_path: Path):
    window = build_main_window(runner=JobRunner(max_workers=1))
    open_test_project(window, tmp_path / "p", ["a", "b"])
    yield window
    window.close_project()


def test_cancel_marks_any_job_pending_until_it_ends(tmp_path: Path) -> None:
    window = build_main_window()
    open_test_project(window, tmp_path / "p", ["a"])
    gate = threading.Event()
    jid = window.submit_job("strain_growth", lambda ctx: gate.wait(5) and {"ok": True})
    window.jobs_panel.selectRow(0)
    window.activity.cancel_btn.click()
    status = window.jobs_panel.item(0, 2).text()
    assert status == "cancelling (solver still running)"
    window._poll_completed_jobs()
    assert window.jobs_panel.item(0, 2).text() == "cancelling (solver still running)"
    gate.set()
    deadline = time.time() + 5
    while window.runner.poll(jid).status.value in ("pending", "running") and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    window._poll_completed_jobs()
    window.bridge.refresh()
    assert window.jobs_panel.item(0, 2).text() in ("cancelled", "done")
    assert jid not in window.bridge.cancelling, "an ended job no longer counts as cancelling"
    window.close_project()


def test_finished_run_appears_in_runs(tmp_path: Path) -> None:
    window = build_main_window()
    project = open_test_project(window, tmp_path / "p", ["a"])
    run = project.runs_dir / "search-20261013-120000"
    run.mkdir()
    (run / "search_summary.json").write_text('{"status": "ok", "targets": ["but"]}')
    window._register_run_output(run)
    runs = window.sidebar.topLevelItem(3)
    assert runs.child(0).text(0) == "✓ Search · but · 12:00"
    window.close_project()


def test_readback_rejection_shows_failed_in_runs_and_clears_when_fixed(
    w, tmp_path: Path
) -> None:
    run = w.session.project.runs_dir / "search-20261013-120000"
    run.mkdir()
    summary = run / "search_summary.json"
    summary.write_text('{"status": "ok", "targets": ["but"]}')  # no ranking: the GUI rejects it
    (run / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "search", "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(run, "search", ["search_summary.json"]),
    }))
    w.refresh_workspace()
    assert _runs(w) == ["✓ Search · but · 12:00"], "the folder alone looks fine"
    assert w.load_search_dir(run) is False
    assert _runs(w) == ["✗ Search · but · 12:00"], "the GUI rejected it, so RUNS says so"
    assert "unreadable" in w.sidebar.topLevelItem(3).child(0).toolTip(0)
    assert "unreadable" in w.inspector.details.toPlainText().lower()

    summary.write_text(json.dumps({
        "status": "ok", "targets": ["but"], "top_ranked": [], "warnings": [],
    }))
    (run / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "search", "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(run, "search", ["search_summary.json"]),
    }))
    assert w.load_search_dir(run) is True
    assert _runs(w) == ["✓ Search · but · 12:00"], "a rejection that no longer holds is cleared"


def test_failed_job_leaves_a_failed_run_never_a_question_mark(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Main(monkeypatch, rc=1, partial="half.tmp")
    w.search_view.model_picker.set_selected(["a"])
    w.search_view.ko_members_input.setText("a")
    jid = w.run_gene_ko_search()
    _settle(w, jid)
    assert w.runner.poll(jid).status is JobStatus.FAILED
    [row] = _runs(w)
    assert row.startswith("✗ "), row
    assert jid not in w.bridge.cancelling


def test_failed_job_with_an_empty_folder_still_shows_failed(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Main(monkeypatch, rc=1)
    w.search_view.model_picker.set_selected(["a"])
    w.search_view.ko_members_input.setText("a")
    jid = w.run_gene_ko_search()
    _settle(w, jid)
    [row] = _runs(w)
    assert row.startswith("✗ "), row
    assert next(w.session.project.runs_dir.glob("gene-ko-*")).is_dir(), "evidence is not removed"


def test_cancelled_job_with_partial_output_shows_cancelled(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _Main(monkeypatch, rc=130, partial="half.tmp")
    main.release.clear()
    w.search_view.model_picker.set_selected(["a"])
    jid = w.run_search_fixture()
    assert main.started.wait(10)
    w._cancel_job_id(jid)
    main.release.set()
    _settle(w, jid)
    assert w.runner.poll(jid).status is JobStatus.CANCELLED
    [row] = _runs(w)
    assert row.startswith("⊘ "), row
    assert (next(w.session.project.runs_dir.glob("search-*")) / "half.tmp").read_text() == "partial"


def test_job_cancelled_before_it_starts_leaves_no_empty_run(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _Main(monkeypatch, rc=0)
    gate = threading.Event()
    blocker = w.submit_job("blocker", lambda ctx: gate.wait(10))  # holds the only worker
    w.search_view.model_picker.set_selected(["a"])
    w.search_view.ko_members_input.setText("a")
    jid = w.run_gene_ko_search()
    assert w.runner.poll(jid).status is JobStatus.PENDING
    w._cancel_job_id(jid)
    gate.set()
    _settle(w, blocker)
    _settle(w, jid)
    assert w.runner.poll(jid).status is JobStatus.CANCELLED
    assert not main.started.is_set(), "the CLI never ran"
    assert _runs(w) == [], "an empty folder from a job that never started is removed"
    assert sorted(p.name for p in w.session.project.runs_dir.iterdir()) == ["_inputs"]


def test_refused_run_leaves_nothing_in_runs(w) -> None:
    project = w.session.project
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    w.search_view.model_picker.set_selected(["a", "b"])
    assert w.run_search_fixture() == ""
    assert _runs(w) == []
