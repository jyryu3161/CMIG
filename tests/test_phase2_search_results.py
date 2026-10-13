from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from cmig.gui.builder import SearchView  # noqa: E402
from cmig.gui.search_results import SearchResultsPanel  # noqa: E402

APP = QApplication.instance() or QApplication([])

SUMMARY = {
    "status": "ok", "strategy": "exhaustive", "target": "but",
    "top_ranked": [{"members": ["a", "b"], "score": 1.5, "target_flux": 1.5,
                    "community_growth": 0.4, "status": "optimal"}],
}


def test_panel_loads_and_invalidates_on_its_own() -> None:
    request = {"models": "a,b"}
    status = QLabel()
    panel = SearchResultsPanel(lambda kind: dict(request) if kind == "search" else {},
                               status=status)
    assert panel.status is status
    panel.load_summary(SUMMARY)
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "a+b"
    panel.invalidate_results(True)  # same request: kept
    assert panel.table.rowCount() == 1
    request["models"] = "a"
    panel.invalidate_results(True)
    assert panel.table.rowCount() == 0
    assert "Inputs changed" in status.text()


def test_search_view_delegates_to_its_panel() -> None:
    view = SearchView()
    assert isinstance(view.results_panel, SearchResultsPanel)
    assert view.table is view.results_panel.table
    view.current_run_dir = None
    view._displayed_kind = "search"
    assert view.results_panel._displayed_kind == "search"
    view.load_summary(SUMMARY)
    assert view.results_panel.table.rowCount() == 1
