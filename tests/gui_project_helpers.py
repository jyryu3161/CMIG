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


def open_test_project(
    window, root: Path, model_names: list[str], *, statuses: dict[str, str] | None = None
) -> proj.Project:
    """`make_project`, then open it in `window`; recent projects go to a file beside it,
    never to the user's settings. Returns the project the window has open."""
    from PySide6.QtCore import QSettings

    from cmig.gui.project_session import RecentProjects

    make_project(root, model_names, statuses=statuses)
    window.recent = RecentProjects(
        QSettings(str(root.parent / f"{root.name}-recent.ini"), QSettings.Format.IniFormat)
    )
    assert window.open_project(root)
    return window.session.require()


def add_test_medium(window, path: Path, text: str = "id,flux\nEX_glc__D_e,10\n") -> str:
    """Write `path`, add it to the window's open project and return its medium picker ref."""
    path.write_text(text)
    entry = proj.add_medium_file(window.session.require(), path)
    window.session.add_medium(entry)
    return f"medium:{entry.id}"


def taxonomy_ids(argv: list[str]) -> list[str]:
    """Model ids in the `--taxonomy` file an analysis argv points at."""
    import csv

    path = Path(argv[argv.index("--taxonomy") + 1])
    with path.open(newline="") as handle:
        return [row["id"] for row in csv.DictReader(handle)]


def textbook_sbml(path: Path) -> Path:
    """cobra's bundled e_coli_core ("textbook") written as SBML at `path` (no network)."""
    import cobra

    path.parent.mkdir(parents=True, exist_ok=True)
    cobra.io.write_sbml_model(cobra.io.load_model("textbook"), str(path))
    return path


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
