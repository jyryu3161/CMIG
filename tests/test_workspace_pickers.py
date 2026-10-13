from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.pickers import ModelPicker  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _shown(picker: ModelPicker) -> list[str]:
    listing = picker.choice_list
    return [listing.item(i).text() for i in range(listing.count())
            if not listing.item(i).isHidden()]


def _click(picker: ModelPicker, model_id: str) -> None:
    listing = picker.choice_list
    (item,) = listing.findItems(model_id, Qt.MatchFlag.MatchExactly)
    listing.scrollToItem(item)
    APP.processEvents()
    QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, listing.visualItemRect(item).center())
    APP.processEvents()


def test_multi_picker_toggles_several_models_in_one_open() -> None:
    picker = ModelPicker()
    picker.set_choices([(f"m{i:03d}", True, "") for i in range(200)])
    picker.set_selected([])
    picker.show()
    menu = picker.menu()
    menu.popup(picker.mapToGlobal(QPoint(0, picker.height())))
    APP.processEvents()
    assert menu.isVisible()
    for model_id in ("m001", "m100", "m199"):
        _click(picker, model_id)
        assert menu.isVisible(), "the list stays open while models are ticked"
    assert picker.selected_ids() == ["m001", "m100", "m199"]
    assert picker.text() == "Models: 3 selected"
    _click(picker, "m100")  # a second click unticks
    assert picker.selected_ids() == ["m001", "m199"]
    menu.close()


def test_multi_picker_filter_narrows_the_list_and_select_all_takes_the_shown_rows() -> None:
    picker = ModelPicker()
    picker.set_choices([
        ("Bacteroides_a", True, ""), ("Roseburia", True, ""), ("Bacteroides_b", True, ""),
        ("Bacteroides_bad", False, "its file is missing"),
    ])
    picker.set_selected([])
    picker.filter_input.setText("bacter")
    assert _shown(picker) == ["Bacteroides_a", "Bacteroides_b", "Bacteroides_bad"]
    picker.select_all_btn.click()
    assert picker.selected_ids() == ["Bacteroides_a", "Bacteroides_b"], (
        "Select All takes the rows shown, never a model that cannot run"
    )
    picker.filter_input.setText("")
    assert len(_shown(picker)) == 4
    picker.select_none_btn.click()
    assert picker.selected_ids() == []
    (bad,) = picker.choice_list.findItems("Bacteroides_bad", Qt.MatchFlag.MatchExactly)
    assert bad.toolTip() == "its file is missing"
    assert not bad.flags() & Qt.ItemFlag.ItemIsEnabled


def test_multi_picker_keyboard_space_toggles_the_current_row() -> None:
    picker = ModelPicker()
    picker.set_choices([("a", True, ""), ("b", True, "")])
    picker.set_selected([])
    picker.choice_list.setCurrentRow(1)
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["b"]
