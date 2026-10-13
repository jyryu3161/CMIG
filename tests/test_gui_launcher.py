"""Rec-1: GUI launcher smoke tests (offscreen).

Verifies that the `cmig-gui` console entry point and the `cmig gui` CLI subcommand
build the main window and enter/exit the Qt event loop. `QApplication.exec` is
patched to return immediately so the tests do not block on a live event loop.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from gui_project_helpers import make_project  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.__main__ import main as gui_main  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402


@pytest.fixture(autouse=True)
def _no_recent_projects(monkeypatch):
    """The launcher reopens the last project; never let a test open (and lock) a real one."""
    monkeypatch.setattr(RecentProjects, "paths", lambda self: [])
    monkeypatch.setattr(RecentProjects, "add", lambda self, path: None)


def _no_block(monkeypatch) -> None:
    monkeypatch.setattr(QApplication, "exec", lambda self: 0, raising=False)


def _built_windows(monkeypatch) -> list:
    import cmig.gui.app as app_module

    built: list = []
    real = app_module.build_main_window

    def build(*args, **kwargs):
        window = real(*args, **kwargs)
        built.append(window)
        return window

    monkeypatch.setattr(app_module, "build_main_window", build)
    return built


def test_launcher_builds_and_runs(monkeypatch):
    _no_block(monkeypatch)
    assert gui_main(["--lang", "en", "--width", "800", "--height", "600"]) == 0


def test_launcher_korean(monkeypatch):
    _no_block(monkeypatch)
    assert gui_main(["--lang", "ko"]) == 0


def test_cli_gui_subcommand(monkeypatch):
    _no_block(monkeypatch)
    from cmig.cli.main import main as cli_main

    assert cli_main(["gui", "--lang", "en"]) == 0


def test_launcher_reopens_the_last_project(monkeypatch, tmp_path):
    make_project(tmp_path / "study", ["a"])
    monkeypatch.setattr(RecentProjects, "paths", lambda self: [(tmp_path / "study").resolve()])
    _no_block(monkeypatch)
    built = _built_windows(monkeypatch)
    assert gui_main(["--lang", "en"]) == 0
    window = built[0]
    assert window.session.project is not None
    assert window.session.project.name == "study"
    window.close_project()


def test_launcher_shows_why_the_last_project_did_not_reopen(monkeypatch, tmp_path):
    gone = tmp_path / "gone"
    monkeypatch.setattr(RecentProjects, "paths", lambda self: [gone])
    _no_block(monkeypatch)
    built = _built_windows(monkeypatch)
    assert gui_main(["--lang", "en"]) == 0
    window = built[0]
    assert window.session.project is None
    assert window.pages.currentWidget() is window.welcome_page
    assert "gone" in window.welcome_message.text()
