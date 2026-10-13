"""Project model and medium pickers used by every analysis page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QMenu, QStyle, QToolButton

_MAX_SHOWN_ID = 28  # longer single-model ids are elided on the button (full id in the tooltip)


class ModelPicker(QToolButton):
    """"Models: n selected ▾" — a checkable menu of the project's models.

    A model that cannot be run (failed check, changed or missing copy) is shown greyed out
    with the reason as its tooltip and can never be part of `selected_ids()`.
    `selection_changed` fires only when the selection actually changes.
    """

    selection_changed = Signal()

    def __init__(self, label: str = "Models", single: bool = False) -> None:
        super().__init__()
        self._label = label
        self._single = single
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        self.setMenu(menu)
        self._actions: dict[str, QAction] = {}
        self._group = QActionGroup(self)
        self._group.setExclusive(single)
        self._current: list[str] = []
        self._update_text()

    @property
    def single(self) -> bool:
        return self._single

    def sizeHint(self) -> QSize:
        """Leave room for the menu arrow, which QToolButton draws over the text's corner."""
        hint = super().sizeHint()
        arrow = self.style().pixelMetric(QStyle.PixelMetric.PM_MenuButtonIndicator, None, self)
        return QSize(hint.width() + 2 * arrow, hint.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def set_choices(self, entries: list[tuple[str, bool, str]]) -> None:
        """Replace the choices; (id, selectable, reason why not). Keeps the selectable picks."""
        previous = set(self.selected_ids())
        first = not self._actions
        menu = self.menu()
        for action in self._group.actions():
            self._group.removeAction(action)
        menu.clear()
        self._actions.clear()
        if not self._single:
            menu.addAction("Select All", lambda: self.set_selected(
                [k for k, a in self._actions.items() if a.isEnabled()]))
            menu.addAction("Select None", lambda: self.set_selected([]))
            menu.addSeparator()
        for model_id, selectable, reason in entries:
            action = QAction(model_id, menu)
            action.setCheckable(True)
            action.setEnabled(selectable)
            if not selectable:
                action.setToolTip(reason)
            keep = model_id in previous or (first and not self._single)
            action.setChecked(selectable and keep)
            action.triggered.connect(self._sync)
            self._group.addAction(action)
            menu.addAction(action)
            self._actions[model_id] = action
        self._sync()

    def selected_ids(self) -> list[str]:
        return [k for k, a in self._actions.items() if a.isChecked() and a.isEnabled()]

    def set_selected(self, ids: list[str]) -> None:
        wanted = [i for i in ids if i in self._actions and self._actions[i].isEnabled()]
        if self._single:
            wanted = wanted[:1]
        for model_id, action in self._actions.items():
            action.blockSignals(True)
            action.setChecked(model_id in wanted)
            action.blockSignals(False)
        self._sync()

    def _sync(self, *_args: object) -> None:
        self._update_text()
        now = self.selected_ids()
        if now != self._current:
            self._current = now
            self.selection_changed.emit()

    def _update_text(self) -> None:
        chosen = self.selected_ids()
        if self._single:
            shown = chosen[0] if chosen else "choose…"
            if len(shown) > _MAX_SHOWN_ID:
                half = (_MAX_SHOWN_ID - 1) // 2
                shown = f"{shown[:half]}…{shown[-half:]}"
            self.setText(f"{self._label}: {shown}")
            self.setToolTip(chosen[0] if chosen else "")
        else:
            self.setText(f"{self._label}: {len(chosen)} selected")
            self.setToolTip(", ".join(chosen))


class MediumPicker(QComboBox):
    """Model default, an installed preset, or a project medium; `current_ref()` names it.

    A project medium whose copy changed or went missing is listed as "(changed)" and cannot
    be picked. Rebuilding the choices only signals when the picked medium changes.
    """

    DEFAULT_TEXT = "Model default (no medium file)"

    def __init__(self) -> None:
        super().__init__()
        # Long preset names must not widen the page past the window size.
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(16)
        self.addItem(self.DEFAULT_TEXT, "")
        # The box may be narrower than a preset name: the tooltip always has all of it.
        self.currentIndexChanged.connect(lambda _index: self.setToolTip(self.currentText()))
        self.setToolTip(self.DEFAULT_TEXT)

    def set_choices(self, presets: list[str], user: list[tuple[str, bool]]) -> None:
        current = self.current_ref()
        blocked = self.blockSignals(True)
        try:
            self.clear()
            self.addItem(self.DEFAULT_TEXT, "")
            for name in presets:
                self.addItem(f"Preset · {name}", f"preset:{name}")
            model = self.model()
            for medium_id, ok in user:
                self.addItem(f"Project · {medium_id}" + ("" if ok else " (changed)"),
                             f"medium:{medium_id}")
                if not ok and isinstance(model, QStandardItemModel):
                    item = model.item(self.count() - 1)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            index = self.findData(current)
            self.setCurrentIndex(max(index, 0))  # a vanished choice shows as model default
        finally:
            self.blockSignals(blocked)
        self.setToolTip(self.currentText())
        if self.current_ref() != current:
            self.currentIndexChanged.emit(self.currentIndex())

    def current_ref(self) -> str:
        return str(self.currentData() or "")

    def set_ref(self, ref: str) -> None:
        """Pick a medium by ref; an unknown ref raises instead of silently picking another."""
        index = self.findData(ref)
        if index < 0:
            raise ValueError(f"no medium choice {ref!r}")
        self.setCurrentIndex(index)
