from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401
from PySide6.QtCore import QEventLoop, QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    make_project(tmp_path / "p", ["a"])
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def test_run_inspection_never_runs_on_the_gui_thread(window, monkeypatch) -> None:
    seen: list[bool] = []

    def fake_inspect(run_dir):  # type: ignore[no-untyped-def]
        seen.append(threading.current_thread() is threading.main_thread())
        return {"artifact_integrity": "verified", "kind": "search", "status": "ok"}

    monkeypatch.setattr("cmig.cli.main._inspect_run_dir", fake_inspect)
    run_dir = window.session.require().runs_dir / "search-20261014-101010"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({}))
    window._inspect_gui_run(run_dir)
    assert seen and not any(seen)


def test_agora2_list_runs_the_cli_off_the_gui_thread(window, monkeypatch) -> None:
    seen: list[bool] = []

    def fake_main(argv):  # type: ignore[no-untyped-def]
        seen.append(threading.current_thread() is threading.main_thread())
        print(json.dumps({"models": [{"id": "Roseburia_x", "published_size": "1M"}]}))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    found = window._agora2_list("Roseburia")
    assert [str(s) for s in found] == ["Roseburia_x"]
    assert seen == [False]


def test_off_thread_errors_propagate(window) -> None:
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        window._run_off_thread(boom)


def test_a_poll_that_fires_during_a_readback_does_not_re_enter(window, monkeypatch) -> None:
    """The nested event loop lets the 500 ms completion timer fire mid-inspection."""
    monkeypatch.setattr(
        "cmig.cli.main._inspect_run_dir",
        lambda run_dir: (time.sleep(0.15), {"artifact_integrity": "verified"})[1],
    )
    run_dir = window.session.require().runs_dir / "search-20261014-101011"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({}))
    passes: list[int] = []

    def one_pass() -> None:
        passes.append(len(passes))
        QTimer.singleShot(20, window._poll_completed_jobs)  # fires inside the nested loop
        window._inspect_gui_run(run_dir)

    monkeypatch.setattr(window, "_poll_completed_jobs_pass", one_pass)
    window._poll_completed_jobs()
    assert passes == [0]
    window._poll_completed_jobs()  # the guard is released afterwards
    assert passes == [0, 1]


def test_the_nested_loop_excludes_user_input(window, monkeypatch) -> None:
    flags: list[object] = []

    class RecordingLoop(QEventLoop):
        def exec(self, flag=QEventLoop.ProcessEventsFlag.AllEvents):  # type: ignore[no-untyped-def]
            flags.append(flag)
            return super().exec(flag)

    monkeypatch.setattr("cmig.gui.app.QEventLoop", RecordingLoop)
    window._run_off_thread(time.sleep, 0.05)
    assert flags and all(f == QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents for f in flags)


def test_off_thread_calls_leave_no_timers_or_loops_behind(window) -> None:
    import gc

    window._run_off_thread(lambda: None)  # warm up
    gc.collect()
    timers = len(window.findChildren(QTimer))
    loops = len(window.findChildren(QEventLoop))
    for _ in range(20):
        window._run_off_thread(lambda: None)
    gc.collect()
    assert len(window.findChildren(QTimer)) == timers
    assert len(window.findChildren(QEventLoop)) == loops


def test_a_quick_job_does_not_wait_for_a_timer_tick(window) -> None:
    window._run_off_thread(lambda: None)  # warm up
    start = time.perf_counter()
    for _ in range(10):
        window._run_off_thread(lambda: None)
    assert time.perf_counter() - start < 0.15  # a 20 ms tick minimum each would be >= 0.2 s


def test_other_threads_output_is_not_captured_by_the_lookup(window, monkeypatch, capsys) -> None:
    def fake_main(argv):  # type: ignore[no-untyped-def]
        other = threading.Thread(target=lambda: print("from-another-thread"))
        other.start()
        other.join()
        print(json.dumps({"models": [{"id": "Roseburia_x", "published_size": "1M"}]}))
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    found = window._agora2_list("Roseburia")
    assert [str(s) for s in found] == ["Roseburia_x"]  # the other thread's line is not in it
    assert "from-another-thread" in capsys.readouterr().out  # and it still reached the stream


def test_installing_the_stdout_router_without_a_stdout_does_nothing(monkeypatch) -> None:
    import sys

    from cmig.gui.app import _install_stdout_router

    monkeypatch.setattr(sys, "stdout", None)
    _install_stdout_router()
    assert sys.stdout is None
