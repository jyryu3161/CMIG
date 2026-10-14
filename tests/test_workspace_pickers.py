from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gui_project_helpers import _deterministic_qt_teardown  # noqa: E402,F401
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

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


def _open(picker: ModelPicker):
    picker.show()
    picker.window().activateWindow()  # offscreen: hasFocus() is false in an inactive window
    QTest.qWait(10)
    menu = picker.menu()
    menu.popup(picker.mapToGlobal(QPoint(0, picker.height())))
    APP.processEvents()
    QTest.qWait(10)  # the filter takes focus on the next event-loop turn
    APP.processEvents()
    return menu


def _hosted(picker: ModelPicker) -> tuple[QWidget, QLineEdit]:
    """A window where another field has focus, so "focus returns to the picker" is observable."""
    host = QWidget()
    other = QLineEdit()
    layout = QVBoxLayout(host)
    layout.addWidget(other)
    layout.addWidget(picker)
    host.show()
    host.activateWindow()
    other.setFocus()
    QTest.qWait(10)
    return host, other


def test_keyboard_reaches_list_buttons_and_back() -> None:
    picker = ModelPicker()
    host, other = _hosted(picker)
    picker.set_choices([("alpha", True, ""), ("beta", True, ""), ("gamma", True, "")])
    picker.set_selected([])
    menu = _open(picker)
    assert picker.filter_input.hasFocus()
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Down)
    assert picker.choice_list.hasFocus()
    assert picker.choice_list.currentItem().text() == "alpha"
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["alpha"] and menu.isVisible()
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Up)
    assert picker.filter_input.hasFocus(), "Up on the first row goes back to the filter"
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Tab)
    assert picker.choice_list.hasFocus()
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Tab)
    assert picker.select_all_btn.hasFocus()
    QTest.keyClick(picker.select_all_btn, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["alpha", "beta", "gamma"]
    QTest.keyClick(picker.select_all_btn, Qt.Key.Key_Tab)
    assert picker.select_none_btn.hasFocus()
    QTest.keyClick(picker.select_none_btn, Qt.Key.Key_Tab)
    assert picker.filter_input.hasFocus()
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Backtab)
    assert picker.select_none_btn.hasFocus()
    QTest.keyClick(picker.select_none_btn, Qt.Key.Key_Return)
    QTest.qWait(10)  # the picker button takes focus on the next event-loop turn
    assert not menu.isVisible()
    picker.window().activateWindow()  # offscreen has no window manager to re-activate it
    QTest.qWait(10)
    assert picker.hasFocus() and not other.hasFocus(), "focus returns to the picker button"
    assert picker.selected_ids() == ["alpha", "beta", "gamma"], "Return closes, it does not act"


def test_filter_then_down_starts_at_first_shown_row() -> None:
    picker = ModelPicker()
    host, other = _hosted(picker)
    picker.set_choices([("alpha", True, ""), ("beta", True, ""), ("bravo", True, "")])
    picker.set_selected([])
    menu = _open(picker)
    QTest.keyClicks(picker.filter_input, "br")
    QTest.keyClick(picker.filter_input, Qt.Key.Key_Down)
    assert picker.choice_list.currentItem().text() == "bravo"
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Space)
    assert picker.selected_ids() == ["bravo"]
    QTest.keyClick(picker.choice_list, Qt.Key.Key_Escape)
    QTest.qWait(10)
    assert not menu.isVisible()
    picker.window().activateWindow()  # offscreen has no window manager to re-activate it
    QTest.qWait(10)
    assert picker.hasFocus() and not other.hasFocus()


def test_single_picker_return_picks_and_closes() -> None:
    picker = ModelPicker("Model", single=True)
    picker.set_choices([("a", True, ""), ("b", True, "")])
    picker.show()
    menu = picker.menu()
    menu.popup(picker.mapToGlobal(QPoint(0, picker.height())))
    APP.processEvents()
    QTest.keyClick(menu, Qt.Key.Key_Down)
    QTest.keyClick(menu, Qt.Key.Key_Down)
    QTest.keyClick(menu, Qt.Key.Key_Return)
    APP.processEvents()
    assert not menu.isVisible()
    assert picker.selected_ids() == ["b"]
