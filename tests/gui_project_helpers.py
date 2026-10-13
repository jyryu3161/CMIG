"""Shared helpers for GUI workspace tests: fake projects and deterministic Qt teardown."""

from __future__ import annotations

import gc
from pathlib import Path

import pytest

from cmig.io import project as proj


def ok_check(_path: Path) -> proj.ModelCheck:
    return proj.ModelCheck("ok", None, 10, 8, 3, ["BIOMASS"], 99.0, [])


def make_project(
    root: Path, model_names: list[str], *, statuses: dict[str, str] | None = None
) -> proj.Project:
    """A saved project whose models are tiny placeholder files marked as checked."""
    project = proj.create_project(root)
    source = root.parent / f"{root.name}-sources"
    source.mkdir(parents=True, exist_ok=True)
    for name in model_names:
        path = source / f"{name}.xml"
        path.write_text(f"<sbml id='{name}'/>")
        entry = proj.add_model_file(project, path, check=ok_check)
        entry.status = (statuses or {}).get(name, "ok")
    proj.save_project(project)
    return project


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown():
    """Close and delete top-level Qt widgets after each test (avoids macOS exit segfaults)."""
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    gc.collect()
