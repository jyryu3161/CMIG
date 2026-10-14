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



class _Hints:
    def __init__(self) -> None:
        self.schemes: list[object] = []

    def setColorScheme(self, scheme: object) -> None:  # noqa: N802 - Qt name
        self.schemes.append(scheme)


class _App:
    def __init__(self) -> None:
        self.hints = _Hints()

    def styleHints(self) -> _Hints:  # noqa: N802 - Qt name
        return self.hints


@pytest.mark.parametrize(
    ("choice", "scheme"), [("light", "Light"), ("dark", "Dark"), ("system", "Unknown")]
)
def test_apply_appearance_sets_the_colour_scheme(choice: str, scheme: str) -> None:
    # The offscreen platform ignores colour schemes, so the call itself is what is checked.
    from PySide6.QtCore import Qt

    from cmig.gui.__main__ import apply_appearance

    app = _App()
    apply_appearance(app, choice)
    assert app.hints.schemes == [getattr(Qt.ColorScheme, scheme)]


def _recorded_appearance(monkeypatch) -> list[str]:
    import cmig.gui.__main__ as launcher

    seen: list[str] = []
    monkeypatch.setattr(launcher, "apply_appearance", lambda _app, choice: seen.append(choice))
    return seen


def test_launcher_is_light_by_default(monkeypatch) -> None:
    _no_block(monkeypatch)
    seen = _recorded_appearance(monkeypatch)
    assert gui_main(["--lang", "en"]) == 0
    assert seen == ["light"]


def test_launcher_and_cli_pass_the_appearance(monkeypatch) -> None:
    from cmig.cli.main import main as cli_main

    _no_block(monkeypatch)
    seen = _recorded_appearance(monkeypatch)
    assert gui_main(["--appearance", "system"]) == 0
    assert cli_main(["gui", "--appearance", "dark"]) == 0
    assert cli_main(["gui"]) == 0
    assert seen == ["system", "dark", "light"]
