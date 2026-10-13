"""Project model and medium pickers used by every analysis page."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeyEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

_MAX_SHOWN_ID = 28  # longer single-model ids are elided on the button (full id in the tooltip)


class ModelPicker(QToolButton):
    """"Models: n selected ▾" — the project's models to choose from.

    A multi-model picker opens a list that stays open while models are ticked, with a filter
    field and Select All / Select None (both act on the rows the filter shows). A single-model
    picker is a menu that closes on the pick.
    A model that cannot be run (failed check, changed or missing copy) is shown greyed out
    with the reason as its tooltip and can never be part of `selected_ids()`.
    `selection_changed` fires only when the selection actually changes.
    """

    selection_changed = Signal()

    _VISIBLE_ROWS = 12  # rows the multi-model list shows before it scrolls

    def __init__(self, label: str = "Models", single: bool = False) -> None:
        super().__init__()
        self._label = label
        self._single = single
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        self.setMenu(menu)
        self._actions: dict[str, QAction] = {}  # single-model picker: one menu action per model
        self._items: dict[str, QListWidgetItem] = {}  # multi-model picker: one list row per model
        self._group = QActionGroup(self)
        self._group.setExclusive(single)
        self._current: list[str] = []
        if not single:
            self._build_list(menu)
        self._update_text()

    def _build_list(self, menu: QMenu) -> None:
        """The multi-model list, hosted in the menu so clicks inside it never close it."""
        panel = QWidget()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter models")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self._apply_filter)
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setToolTip("Tick every runnable model shown")
        self.select_all_btn.clicked.connect(lambda: self._tick_shown(True))
        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.setToolTip("Untick every model shown")
        self.select_none_btn.clicked.connect(lambda: self._tick_shown(False))
        self.choice_list = QListWidget()
        self.choice_list.setUniformItemSizes(True)
        self.choice_list.setMinimumWidth(260)
        self.choice_list.itemClicked.connect(self._toggle)
        self.choice_list.installEventFilter(self)
        buttons = QHBoxLayout()
        buttons.addWidget(self.select_all_btn)
        buttons.addWidget(self.select_none_btn)
        buttons.addStretch(1)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.filter_input)
        layout.addLayout(buttons)
        layout.addWidget(self.choice_list)
        holder = QWidgetAction(menu)
        holder.setDefaultWidget(panel)
        menu.addAction(holder)
        menu.aboutToShow.connect(self._prepare_list)

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
        if self._single:
            self._set_menu_choices(entries)
        else:
            self._set_list_choices(entries)
        self._sync()

    def _set_menu_choices(self, entries: list[tuple[str, bool, str]]) -> None:
        previous = set(self.selected_ids())
        menu = self.menu()
        for action in self._group.actions():
            self._group.removeAction(action)
        menu.clear()
        self._actions.clear()
        for model_id, selectable, reason in entries:
            action = QAction(model_id, menu)
            action.setCheckable(True)
            action.setEnabled(selectable)
            if not selectable:
                action.setToolTip(reason)
            action.setChecked(selectable and model_id in previous)
            action.triggered.connect(self._sync)
            self._group.addAction(action)
            menu.addAction(action)
            self._actions[model_id] = action

    def _set_list_choices(self, entries: list[tuple[str, bool, str]]) -> None:
        previous = set(self.selected_ids())
        first = not self._items  # the first choices offered are all ticked by default
        self.choice_list.clear()
        self._items.clear()
        for model_id, selectable, reason in entries:
            item = QListWidgetItem(model_id)
            # Not user-checkable: a click anywhere on the row toggles it (see _toggle).
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                if selectable else Qt.ItemFlag.NoItemFlags
            )
            if not selectable:
                item.setToolTip(reason)
            ticked = selectable and (model_id in previous or first)
            item.setCheckState(Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked)
            self.choice_list.addItem(item)
            self._items[model_id] = item
        self._apply_filter(self.filter_input.text())

    def choice_ids(self) -> list[str]:
        """Every model offered, runnable or not, in list order."""
        return list(self._actions if self._single else self._items)

    def selected_ids(self) -> list[str]:
        if self._single:
            chosen = [k for k, a in self._actions.items() if a.isChecked() and a.isEnabled()]
            return chosen[:1]
        return [k for k, item in self._items.items() if self._ticked(item)]

    @staticmethod
    def _runnable(item: QListWidgetItem) -> bool:
        return bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)

    def _ticked(self, item: QListWidgetItem) -> bool:
        return self._runnable(item) and item.checkState() == Qt.CheckState.Checked

    def set_selected(self, ids: list[str]) -> None:
        """Check exactly these runnable ids (single mode: the first runnable one only).

        Signals are not blocked: the exclusive action group tracks its checked action through
        them. Only `triggered` (a user click) is connected, so nothing else reacts here.
        """
        if self._single:
            wanted = [i for i in ids if i in self._actions and self._actions[i].isEnabled()][:1]
            for model_id, action in self._actions.items():
                action.setChecked(model_id in wanted)
        else:
            for model_id, item in self._items.items():
                ticked = model_id in ids and self._runnable(item)
                item.setCheckState(Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked)
        self._sync()

    def _toggle(self, item: QListWidgetItem) -> None:
        if not self._runnable(item):
            return
        ticked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if ticked else Qt.CheckState.Checked)
        self._sync()

    def _tick_shown(self, ticked: bool) -> None:
        state = Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked
        for item in self._items.values():
            if not item.isHidden() and self._runnable(item):
                item.setCheckState(state)
        self._sync()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for model_id, item in self._items.items():
            item.setHidden(bool(needle) and needle not in model_id.lower())

    def _prepare_list(self) -> None:
        """On open: the whole list, sized to its rows, with the filter field ready to type in."""
        self.filter_input.clear()
        rows = min(max(len(self._items), 1), self._VISIBLE_ROWS)
        row_height = self.choice_list.sizeHintForRow(0) if self._items else 0
        frame = 2 * self.choice_list.frameWidth()
        self.choice_list.setFixedHeight(max(rows * row_height, 24) + frame)
        QTimer.singleShot(0, self.filter_input.setFocus)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        """Space on the list toggles the current row, like a click."""
        if (
            watched is getattr(self, "choice_list", None)
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Space
        ):
            item = self.choice_list.currentItem()
            if item is not None:
                self._toggle(item)
            return True
        return super().eventFilter(watched, event)

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
