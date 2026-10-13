from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    QTableWidget,
)

from cmig.gui.analysis_page import (  # noqa: E402
    AnalysisPage,
    ResultsArea,
    hide_row_numbers,
)
from cmig.gui.pickers import MediumPicker, ModelPicker  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _page() -> tuple[AnalysisPage, dict[str, object]]:
    page = AnalysisPage("Demo", "One line about the demo.")
    models = ModelPicker("Models")
    models.set_choices([("a", True, ""), ("b", True, ""), ("gone", False, "missing")])
    medium = MediumPicker()
    medium.set_choices(["western_diet"], [])
    size = QSpinBox()
    size.setRange(1, 10)
    size.setValue(2)
    fraction = QDoubleSpinBox()
    fraction.setValue(0.5)
    combo = QComboBox()
    combo.addItems(["auto", "exhaustive"])
    check = QCheckBox("FVA")
    text = QLineEdit("but")
    page.add_input_row(models, "Medium", medium)
    page.add_input_row("Size", size)
    page.advanced.add_row("Fraction", fraction, "Strategy", combo, check, text)
    page.advanced.track(fraction, combo, check, text)
    widgets = {"models": models, "medium": medium, "size": size, "fraction": fraction,
               "strategy": combo, "fva": check, "target": text}
    for name, widget in widgets.items():
        page.register(name, widget)  # type: ignore[arg-type]
    return page, widgets


def test_snapshot_and_restore_round_trip() -> None:
    page, w = _page()
    w["models"].set_selected(["b"])  # type: ignore[attr-defined]
    w["medium"].set_ref("preset:western_diet")  # type: ignore[attr-defined]
    w["size"].setValue(3)  # type: ignore[attr-defined]
    w["strategy"].setCurrentText("exhaustive")  # type: ignore[attr-defined]
    saved = page.snapshot()
    assert saved == {"models": ["b"], "medium": "preset:western_diet", "size": 3,
                     "fraction": 0.5, "strategy": "exhaustive", "fva": False, "target": "but"}
    other, _ = _page()
    assert other.restore(saved) == []
    assert other.snapshot() == saved


def test_restore_reports_values_that_cannot_be_chosen_now() -> None:
    page, _w = _page()
    notes = page.restore({"models": ["a", "gone", "never"], "medium": "medium:deleted",
                          "strategy": "ga"})
    assert page.snapshot()["models"] == ["a"]
    assert page.snapshot()["medium"] == ""
    joined = " ".join(notes)
    assert "gone" in joined and "never" in joined
    assert "deleted" in joined and "ga" in joined


def test_advanced_counts_values_changed_from_their_defaults() -> None:
    page, w = _page()
    assert page.advanced.changed_count() == 0
    assert page.advanced.toggle.text() == "Advanced options"
    w["fraction"].setValue(0.25)  # type: ignore[attr-defined]
    w["fva"].setChecked(True)  # type: ignore[attr-defined]
    assert page.advanced.changed_count() == 2
    assert page.advanced.toggle.text() == "Advanced options · 2 changed"
    w["fraction"].setValue(0.5)  # type: ignore[attr-defined]
    assert page.advanced.toggle.text() == "Advanced options · 1 changed"
    assert page.advanced.body.isHidden(), "collapsed by default"
    page.advanced.set_expanded(True)
    assert not page.advanced.body.isHidden()


def test_results_area_starts_empty_and_shows_content() -> None:
    area = ResultsArea()
    table = QTableWidget(0, 2)
    area.add(table)
    assert not area.has_results()
    assert area.empty_label.text() == ResultsArea.EMPTY_TEXT
    assert table.isHidden() or area.content.isHidden()
    area.show_results()
    assert area.has_results() and area.empty_label.isHidden()
    area.show_empty()
    assert not area.has_results()


def test_page_frame_and_banner() -> None:
    page, _w = _page()
    assert page.status is page.results.status
    assert page.banner.isHidden()
    page.show_banner("Inputs restored from search-1")
    assert not page.banner.isHidden() and "search-1" in page.banner.text()
    page.clear_banner()
    assert page.banner.isHidden()
    assert not page.cancel_btn.isEnabled()


def test_hide_row_numbers() -> None:
    table = hide_row_numbers(QTableWidget(2, 2))
    assert table.verticalHeader().isHidden()
