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
from PySide6.QtCore import QSettings, QTimer  # noqa: E402
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
