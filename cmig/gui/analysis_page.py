"""The frame every analysis page uses: an inputs card with Run, Advanced options, Results.

Pages register their inputs by name; `snapshot()` is what a run records in
`runs/_inputs/<run>-request.json` and `restore()` puts it back when the run is reopened.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.pickers import MediumPicker, ModelPicker


def hide_row_numbers(table: QTableWidget) -> QTableWidget:
    table.verticalHeader().setVisible(False)
    return table


COMPUTED_TIP = "Computed by CMIG"
FLUX_LEGEND = "+ secretion / − uptake (mmol gDW⁻¹ h⁻¹)"
_FAILED_WORDS = ("failed", "error", "infeasible", "cancel", "non-viable", "non_viable",
                 "timeout", "unknown", "unreadable", "time_limit", "numeric", "undefined",
                 "no_solution", "unevaluable", "unbounded", "not_run", "unevaluated", "⚠")
_NUMBER = r"[+\-−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+\-]?\d+)?"
#: a finite number, "[lo, hi]" or "lo..hi": the only text that reads as a computed value
_VALUE_TEXT = re.compile(
    rf"{_NUMBER}|\[\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\]|{_NUMBER}\s*\.\.\s*{_NUMBER}"
)


def is_failed_status(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _FAILED_WORDS)


def mark_computed_headers(table: QTableWidget, columns: Iterable[int]) -> None:
    for column in columns:
        item = table.horizontalHeaderItem(column)
        if item is None:
            continue
        tip = item.toolTip()
        if COMPUTED_TIP not in tip:
            item.setToolTip(f"{tip}\n{COMPUTED_TIP}" if tip else COMPUTED_TIP)


def paint_computed(
    table: QTableWidget, columns: Iterable[int], *, status_column: int | None = None
) -> None:
    """Show computed values in the system accent colour; inputs keep the default colour.

    A cell that already has its own colour (a diagnostic, a significance mark) keeps it. Only
    text that reads as a finite number or a numeric range is painted: a missing value, a
    status word and every cell of a failed, warned or unevaluated row never are.
    """
    accent = QApplication.palette().color(QPalette.ColorRole.Accent)
    wanted = list(columns)
    for row in range(table.rowCount()):
        if status_column is not None:
            status = table.item(row, status_column)
            if status is not None and is_failed_status(status.text()):
                continue
        for column in wanted:
            item = table.item(row, column)
            if item is None or item.data(Qt.ItemDataRole.ForegroundRole) is not None:
                continue
            if _VALUE_TEXT.fullmatch(item.text().strip()) is None:
                continue
            item.setForeground(accent)


def widget_value(widget: QWidget) -> Any:
    if isinstance(widget, ModelPicker):
        return widget.selected_ids()
    if isinstance(widget, MediumPicker):  # before QComboBox: it is one
        return widget.current_ref()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QSlider):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QLineEdit):
        return widget.text()
    raise TypeError(f"no value for {type(widget).__name__}")


def set_widget_value(widget: QWidget, value: Any) -> str | None:
    """Put a recorded value back; returns why it could not be, or None when it was."""
    try:
        if isinstance(widget, ModelPicker):
            wanted = [str(v) for v in value]
            widget.set_selected(wanted)
            lost = [v for v in wanted if v not in widget.selected_ids()]
            return f"{', '.join(lost)} can no longer be chosen" if lost else None
        if isinstance(widget, MediumPicker):
            try:
                widget.set_ref(str(value))
            except ValueError:
                widget.set_ref("")
                return f"medium {str(value).partition(':')[2] or value} is no longer available"
            return None
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QSlider):
            widget.setValue(int(value))
        elif isinstance(widget, QComboBox):
            index = widget.findText(str(value))
            if index < 0:
                return f"{value} is not a choice any more"
            widget.setCurrentIndex(index)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        else:
            return f"{type(widget).__name__} cannot be restored"
    except (TypeError, ValueError):
        return f"{value!r} could not be restored"
    return None


def connect_change(widget: QWidget, slot: Callable[..., Any]) -> None:
    if isinstance(widget, ModelPicker):
        widget.selection_changed.connect(slot)
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(slot)
    elif isinstance(widget, QCheckBox):
        widget.toggled.connect(slot)
    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.valueChanged.connect(slot)
    elif isinstance(widget, QSlider):
        widget.valueChanged.connect(slot)
    elif isinstance(widget, QLineEdit):
        widget.textChanged.connect(slot)


def _row(items: tuple[QWidget | str, ...]) -> QHBoxLayout:
    row = QHBoxLayout()
    for item in items:
        row.addWidget(QLabel(item) if isinstance(item, str) else item)
    row.addStretch(1)
    return row


class AdvancedSection(QWidget):
    """A disclosure button and its (collapsed) body; the button counts changed settings."""

    def __init__(self, title: str = "Advanced options") -> None:
        super().__init__()
        self._title = title
        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self.set_expanded)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 0, 0, 0)
        self.body.setVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self._tracked: list[tuple[QWidget, Any]] = []
        self._refresh()

    def add_row(self, *items: QWidget | str) -> QHBoxLayout:
        row = _row(items)
        self.body_layout.addLayout(row)
        return row

    def track(self, *widgets: QWidget) -> None:
        """Count each widget as changed while its value differs from its value now."""
        for widget in widgets:
            self._tracked.append((widget, widget_value(widget)))
            connect_change(widget, lambda *_a: self._refresh())
        self._refresh()

    def changed_count(self) -> int:
        return sum(1 for widget, default in self._tracked if widget_value(widget) != default)

    def set_expanded(self, expanded: bool) -> None:
        if self.toggle.isChecked() != expanded:
            self.toggle.setChecked(expanded)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(expanded)

    def _refresh(self) -> None:
        count = self.changed_count()
        self.toggle.setText(self._title + (f" · {count} changed" if count else ""))


class ResultsArea(QWidget):
    EMPTY_TEXT = "No results yet — set the inputs above and press Run."

    def __init__(self) -> None:
        super().__init__()
        heading = QLabel("Results")
        font = QFont(heading.font())
        font.setBold(True)
        heading.setFont(font)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.empty_label = QLabel(self.EMPTY_TEXT)
        self.empty_label.setEnabled(False)  # secondary text colour in both appearances
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(heading)
        layout.addWidget(self.status)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.content, 1)
        # With no results the spare height goes here, below the empty note; once results
        # show, `content` (stretch 1) takes it all.
        layout.addStretch(0)
        self.show_empty()

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)

    def show_results(self) -> None:
        self.empty_label.setVisible(False)
        self.content.setVisible(True)

    def show_empty(self) -> None:
        self.content.setVisible(False)
        self.empty_label.setVisible(True)

    def has_results(self) -> bool:
        return not self.content.isHidden()


class AnalysisPage(QWidget):
    def __init__(
        self, title: str, description: str, run_text: str = "Run", *, cancel: bool = True
    ) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setMinimumSize(0, 0)
        outer.addWidget(self.scroll_area)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        self.scroll_area.setWidget(content)
        self.title = QLabel(title)
        title_font = QFont(self.title.font())
        title_font.setBold(True)
        title_font.setPointSizeF(title_font.pointSizeF() * 1.25)
        self.title.setFont(title_font)
        self.description = QLabel(description)
        self.description.setWordWrap(True)
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        self.banner.setMargin(6)
        self.banner.setVisible(False)
        self.card = QFrame()
        self.card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout = QVBoxLayout(self.card)
        self.inputs = QVBoxLayout()
        card_layout.addLayout(self.inputs)
        self.run_btn = QPushButton(run_text)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(cancel)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.run_btn)
        card_layout.addLayout(buttons)
        self.advanced = AdvancedSection()
        self.results = ResultsArea()
        self.status = self.results.status
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        layout.addWidget(self.banner)
        layout.addWidget(self.card)
        layout.addWidget(self.advanced)
        layout.addWidget(self.results, 1)
        self._fields: dict[str, tuple[Callable[[], Any], Callable[[Any], str | None]]] = {}

    def add_input_row(self, *items: QWidget | str) -> QHBoxLayout:
        row = _row(items)
        self.inputs.addLayout(row)
        return row

    def register(self, name: str, widget: QWidget) -> None:
        self._fields[name] = (
            lambda: widget_value(widget), lambda value: set_widget_value(widget, value)
        )

    def register_custom(
        self, name: str, getter: Callable[[], Any], setter: Callable[[Any], str | None]
    ) -> None:
        self._fields[name] = (getter, setter)

    def snapshot(self) -> dict[str, Any]:
        return {name: getter() for name, (getter, _setter) in self._fields.items()}

    def restore(self, values: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        for name, (_getter, setter) in self._fields.items():
            if name in values:
                note = setter(values[name])
                if note:
                    notes.append(note)
        return notes

    def show_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(True)

    def clear_banner(self) -> None:
        self.banner.clear()
        self.banner.setVisible(False)
