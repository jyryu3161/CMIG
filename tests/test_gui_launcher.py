"""Rec-1: GUI launcher smoke tests (offscreen).

Verifies that the `cmig-gui` console entry point and the `cmig gui` CLI subcommand
build the main window and enter/exit the Qt event loop. `QApplication.exec` is
patched to return immediately so the tests do not block on a live event loop.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.__main__ import main as gui_main  # noqa: E402


def _no_block(monkeypatch) -> None:
    monkeypatch.setattr(QApplication, "exec", lambda self: 0, raising=False)


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
