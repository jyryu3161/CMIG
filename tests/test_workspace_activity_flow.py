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
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.workflow_manifest import artifact_result_digest  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
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


def _inputs(w) -> list[str]:
    return sorted(p.name for p in w.session.project.inputs_dir.iterdir())


def _only_run(w, prefix: str) -> Path:
    (run,) = w.session.project.runs_dir.glob(f"{prefix}-*")
    return run


def _reopen(w, tmp_path: Path):
    """Close `w` and open the same project in a new window, as after a restart."""
    root = w.session.project.root
    w.close_project()
    fresh = build_main_window(runner=JobRunner(max_workers=1))
    fresh.recent = RecentProjects(
        QSettings(str(tmp_path / "reopen-recent.ini"), QSettings.Format.IniFormat)
    )
    assert fresh.open_project(root)
    return fresh


def test_failed_job_leaves_a_failed_run_never_a_question_mark(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Main(monkeypatch, rc=1, partial="half.tmp")
    w.gene_ko_page.model_picker.set_selected(["a"])
    w.gene_ko_page.members_picker.set_selected(["a"])
    jid = w.run_gene_ko_search()
    _settle(w, jid)
    assert w.runner.poll(jid).status is JobStatus.FAILED
    [row] = _runs(w)
    assert row.startswith("✗ "), row
    assert jid not in w.bridge.cancelling
    run = _only_run(w, "gene-ko")
    assert sorted(p.name for p in run.iterdir()) == ["half.tmp"], "nothing added to the CLI folder"
    assert _inputs(w) == [
        f"{run.name}-request.json", f"{run.name}-state.json", f"{run.name}-taxonomy.csv"
    ]
    marker = json.loads((w.session.project.inputs_dir / f"{run.name}-state.json").read_text())
    assert marker["status"] == "failed" and marker["job_kind"] == "gene_ko_search"
    assert marker["recorded"]


def test_failed_job_with_an_empty_folder_still_shows_failed(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Main(monkeypatch, rc=1)
    w.gene_ko_page.model_picker.set_selected(["a"])
    w.gene_ko_page.members_picker.set_selected(["a"])
    jid = w.run_gene_ko_search()
    _settle(w, jid)
    [row] = _runs(w)
    assert row.startswith("✗ "), row
    assert _only_run(w, "gene-ko").is_dir(), "evidence is not removed"


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
    run = _only_run(w, "search")
    assert (run / "half.tmp").read_text() == "partial"
    assert (w.session.project.inputs_dir / f"{run.name}-taxonomy.csv").is_file(), "input kept"


def test_cancelled_search_that_published_nothing_still_shows_cancelled(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI discards its staged output on rc 130: the folder is empty but the run was tried."""
    main = _Main(monkeypatch, rc=130)
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
    run = _only_run(w, "search")
    assert list(run.iterdir()) == [], "the folder is kept, empty"
    assert _inputs(w) == [
        f"{run.name}-request.json", f"{run.name}-state.json", f"{run.name}-taxonomy.csv"
    ]


def test_job_cancelled_before_it_starts_is_listed_cancelled(
    w, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _Main(monkeypatch, rc=0)
    gate = threading.Event()
    blocker = w.submit_job("blocker", lambda ctx: gate.wait(10))  # holds the only worker
    w.gene_ko_page.model_picker.set_selected(["a"])
    w.gene_ko_page.members_picker.set_selected(["a"])
    jid = w.run_gene_ko_search()
    assert w.runner.poll(jid).status is JobStatus.PENDING
    w._cancel_job_id(jid)
    gate.set()
    _settle(w, blocker)
    _settle(w, jid)
    assert w.runner.poll(jid).status is JobStatus.CANCELLED
    assert not main.started.is_set(), "the CLI never ran"
    [row] = _runs(w)
    assert row.startswith("⊘ "), row
    run = _only_run(w, "gene-ko")
    assert list(run.iterdir()) == []
    assert (w.session.project.inputs_dir / f"{run.name}-taxonomy.csv").is_file(), "input kept"


@pytest.mark.parametrize(
    ("rc", "symbol"), [(1, "✗"), (130, "⊘")], ids=["failed", "cancelled"]
)
def test_failed_and_cancelled_marks_survive_a_restart(
    w, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rc: int, symbol: str
) -> None:
    main = _Main(monkeypatch, rc=rc)
    if rc == 130:
        w.search_view.model_picker.set_selected(["a"])
        main.release.clear()
        jid = w.run_search_fixture()
        assert main.started.wait(10)
        w._cancel_job_id(jid)
        main.release.set()
    else:
        w.gene_ko_page.model_picker.set_selected(["a"])
        w.gene_ko_page.members_picker.set_selected(["a"])
        jid = w.run_gene_ko_search()
    _settle(w, jid)
    [before] = _runs(w)
    assert before.startswith(f"{symbol} ")
    fresh = _reopen(w, tmp_path)
    try:
        assert _runs(fresh) == [before], "the marker keeps the mark after a restart"
    finally:
        fresh.close_project()


def test_refused_run_leaves_nothing_in_runs(w) -> None:
    project = w.session.project
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    w.search_view.model_picker.set_selected(["a", "b"])
    assert w.run_search_fixture() == ""
    assert _runs(w) == []
    assert sorted(p.name for p in project.runs_dir.iterdir()) == ["_inputs"]
    assert _inputs(w) == []


def test_run_refused_after_its_folder_was_claimed_is_removed_with_its_input(
    w, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkpoint inside the run folder is refused after the folder and taxonomy exist."""
    monkeypatch.setattr("cmig.io.project._stamp", lambda: "20261013-120000")
    project = w.session.project
    w.search_view.model_picker.set_selected(["a"])
    w.search_view.checkpoint_input.setText(str(project.runs_dir / "search-20261013-120000" / "ck"))
    assert w.run_search_fixture() == ""
    assert "inside this run's output folder" in w.search_view.status.text()
    assert _runs(w) == []
    assert sorted(p.name for p in project.runs_dir.iterdir()) == ["_inputs"]
    assert _inputs(w) == [], "the refused run's taxonomy goes with its folder"


# ── final review: a readback rejection is remembered across a restart ─────────────────────
def _search_run(project, *, ranked: bool) -> Path:
    run = project.runs_dir / "search-20261013-120000"
    run.mkdir(exist_ok=True)
    summary = {"status": "ok", "targets": ["but"]}
    if ranked:
        summary.update({"top_ranked": [], "warnings": []})
    (run / "search_summary.json").write_text(json.dumps(summary))
    (run / "manifest.json").write_text(json.dumps({
        "manifest_scope": "workflow", "manifest_schema_version": "1.2",
        "workflow_kind": "search", "artifacts": ["search_summary.json"],
        "result_digest": artifact_result_digest(run, "search", ["search_summary.json"]),
    }))
    return run


def _marker(run: Path) -> dict | None:
    path = run.parent / "_inputs" / f"{run.name}-state.json"
    return json.loads(path.read_text()) if path.exists() else None


def test_readback_rejection_survives_a_restart_until_a_readback_succeeds(
    w, tmp_path: Path
) -> None:
    run = _search_run(w.session.project, ranked=False)  # no ranking: the GUI rejects it
    assert w.load_search_dir(run) is False
    assert _runs(w) == ["✗ Search · but · 12:00"]
    assert _marker(run)["status"] == "unreadable"
    assert sorted(p.name for p in run.iterdir()) == ["manifest.json", "search_summary.json"]
    fresh = _reopen(w, tmp_path)
    try:
        assert _runs(fresh) == ["✗ Search · but · 12:00"], "still rejected after a restart"
        fresh.sidebar.select("runs", str(run))  # opening it reads it back again: rejected
        assert "unreadable" in fresh.inspector.details.toPlainText().lower()
        _search_run(fresh.session.project, ranked=True)
        assert fresh.load_search_dir(run) is True
        assert _runs(fresh) == ["✓ Search · but · 12:00"]
        assert _marker(run) is None, "a readback that succeeds clears the marker"
    finally:
        fresh.close_project()


def test_readback_marker_never_replaces_a_job_marker(w) -> None:
    from cmig.io import project as proj

    run = _search_run(w.session.project, ranked=False)
    proj.write_run_state(run, "cancelled", "search_fixture")
    assert w.load_search_dir(run) is False
    assert _marker(run)["status"] == "cancelled"
    _search_run(w.session.project, ranked=True)
    assert w.load_search_dir(run) is True
    assert _marker(run)["status"] == "cancelled", "the job's ending is kept"
    assert _runs(w) == ["⊘ Search · but · 12:00"]


def test_readback_rejection_of_an_outside_run_writes_nothing_beside_it(w, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    project = w.session.project
    run = _search_run(project, ranked=False)
    moved = outside / run.name
    run.rename(moved)
    assert w.load_search_dir(moved) is False
    assert sorted(p.name for p in outside.iterdir()) == [moved.name]
