from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.sidebar import ANALYSES, ANALYSIS_GROUPS  # noqa: E402

APP = QApplication.instance() or QApplication([])
KEYS = ["search", "gene_ko", "strain_growth", "ratio_impact", "community", "host",
        "host_search", "dfba", "spatial", "medium", "sweep", "sandbox", "compare"]


def test_thirteen_analyses_in_four_groups() -> None:
    assert [key for key, _label in ANALYSES] == KEYS
    assert [title for title, _items in ANALYSIS_GROUPS] == ["Community", "Host", "Dynamics",
                                                            "Tools"]


def test_sidebar_separates_the_groups() -> None:
    w = build_main_window()
    group = w.sidebar.topLevelItem(2)
    keys = [group.child(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(group.childCount())]
    assert keys == ["search", "gene_ko", "strain_growth", "ratio_impact", "community", None,
                    "host", "host_search", None, "dfba", "spatial", None,
                    "medium", "sweep", "sandbox", "compare"]


def test_every_key_has_a_page_a_menu_action_and_a_description() -> None:
    w = build_main_window()
    assert list(w.analysis_pages) == KEYS
    assert set(w.analysis_actions) == set(KEYS)
    assert set(w._DESCRIPTIONS) == set(KEYS)
    for key in KEYS:
        w.show_analysis(key)
        assert w.pages.currentWidget() is w.analysis_pages[key]
        assert w.inspector.title_label.text() == dict(ANALYSES)[key]
