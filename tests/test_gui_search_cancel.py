"""Search cancellation pending state (GUI).

Cancellation is cooperative: the solve in progress finishes first. The Search tab must say
so the moment Cancel is clicked and keep saying so — with Run and Cancel disabled — until
the job actually ends. A cancelled run is never shown as a result.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from gui_project_helpers import open_test_project  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import SEARCH_CANCEL_PENDING, build_main_window  # noqa: E402
from cmig.service import JobCancelled, JobRunner, JobStatus  # noqa: E402

PENDING = "Cancellation requested — the solve in progress will finish first."


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown():
    """Destroy every window inside the test, not at interpreter exit (macOS exit 139).

    Same pattern as tests/test_round8_gui_sweep_overlays.py.
    """
    yield
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.processEvents()


class _BlockingMain:
    """Stand-in for `cmig.cli.main.main`: blocks like an uninterruptible solve."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import cmig.cli.main

        self.started = threading.Event()
        self.release = threading.Event()
        monkeypatch.setattr(cmig.cli.main, "main", self)

    def __call__(self, argv: list[str]) -> int:
        self.started.set()
        assert self.release.wait(timeout=10)
        # The CLI's search loop sees the cancel flag at its next boundary and exits 130.
        return 130


def _window(tmp_path: Path, lang: str = "en"):
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner, lang=lang)
    open_test_project(w, tmp_path / "p", ["a", "b"])
    return w, runner


def _assert_pending(w) -> None:
    view = w.search_view
    assert view.status.text() == PENDING
    assert not view.cancel_btn.isEnabled()
    assert not view.run_btn.isEnabled()


def test_pending_text_constant_matches_spec():
    assert SEARCH_CANCEL_PENDING == PENDING


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_cancel_shows_pending_until_job_ends(monkeypatch, tmp_path, lang):
    fake = _BlockingMain(monkeypatch)
    w, runner = _window(tmp_path, lang)
    try:
        view = w.search_view
        jid = w.run_search_fixture()
        assert jid
        assert fake.started.wait(timeout=10)
        assert view.cancel_btn.isEnabled()

        view.cancel_btn.click()
        # Same event handling: no poll, no event loop turn.
        _assert_pending(w)
        assert jid in w.bridge.cancelling

        # Poll ticks, job-panel refreshes and queued events must not revert it.
        for _ in range(3):
            QApplication.processEvents()
            w.bridge.refresh()
            w._poll_completed_jobs()
            assert runner.poll(jid).status is JobStatus.RUNNING
            _assert_pending(w)

        # Another Search-tab workflow writing the shared status label is re-covered.
        view.status.setText("gene KO search started: other")
        w._poll_completed_jobs()
        _assert_pending(w)

        fake.release.set()
        with pytest.raises(JobCancelled):
            runner.result(jid, timeout=10)
        assert runner.poll(jid).status is JobStatus.CANCELLED
        w._poll_completed_jobs()

        assert jid not in w._search_jobs
        assert view.run_btn.isEnabled()
        assert not view.cancel_btn.isEnabled()
        assert view.status.text() != PENDING
        assert "cancelled" in view.status.text()
        assert w.current_search_dir is None
        assert view.table.rowCount() == 0
        assert jid not in w.bridge.cancelling

        # A later poll does not bring the pending text back.
        w._poll_completed_jobs()
        assert view.status.text() != PENDING
    finally:
        fake.release.set()
        w.close()
        runner.shutdown()


def test_toolbar_cancel_of_search_job_enters_pending_state(monkeypatch, tmp_path):
    fake = _BlockingMain(monkeypatch)
    w, runner = _window(tmp_path)
    try:
        jid = w.run_search_fixture()
        assert fake.started.wait(timeout=10)
        monkeypatch.setattr(w.jobs_panel, "selected_job_id", lambda: jid)
        w._cancel_selected_job()
        _assert_pending(w)
        w._poll_completed_jobs()
        _assert_pending(w)
        fake.release.set()
        with pytest.raises(JobCancelled):
            runner.result(jid, timeout=10)
        w._poll_completed_jobs()
        assert w.search_view.run_btn.isEnabled()
        assert not w.search_view.cancel_btn.isEnabled()
    finally:
        fake.release.set()
        w.close()
        runner.shutdown()
