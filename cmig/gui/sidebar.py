"""Workspace source list: MODELS, MEDIA, ANALYSES and RUNS (two levels, HIG sidebar)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from cmig.gui.project_session import RunEntry
from cmig.io.project import MediumEntry, ModelEntry, ProjectError, supported_model_paths

ANALYSES: list[tuple[str, str]] = [
    ("search", "Combination Search"),
    ("gene_ko", "Gene Knockout"),
    ("growth", "Strain Growth & Ratio"),
    ("host", "Host–Microbe"),
    ("dynamics", "Dynamics"),
    ("community", "Community Solve"),
    ("medium", "Medium Editor"),
    ("sweep", "Sweep"),
    ("sandbox", "Constraint Sandbox"),
    ("compare", "Compare Runs"),
]
ANALYSIS_SEPARATOR_AFTER = "dynamics"
_GROUPS = ("models", "media", "analyses", "runs")
_ROLE = Qt.ItemDataRole.UserRole


def status_symbol(status: str, integrity: str = "ok") -> str:
    if integrity != "ok":
        return "⚠"
    return {
        "ok": "✓",
        "warning": "⚠",
        "degraded": "⚠",
        "failed": "✗",
        "unreadable": "✗",
        "cancelled": "⊘",
        "pending": "…",
    }.get(status, "?")


def droppable_paths(urls: list[QUrl]) -> tuple[list[Path], int]:
    """Model files found under the dropped URLs (folders recurse) and the skipped count.

    Runs inside Qt drag handlers, so an unreadable folder must not raise: the drop is
    treated as carrying nothing droppable and the import step reports the real error.
    """
    local = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
    skipped = len(urls) - len(local)
    try:
        files, unsupported = supported_model_paths(local)
    except ProjectError:
        return [], len(urls)
    return files, skipped + unsupported


class WorkspaceSidebar(QTreeWidget):
    selection_changed = Signal(str, str)
    files_dropped = Signal(list)
    context_requested = Signal(str, list)

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)
        self._groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for name in _GROUPS:
            item = QTreeWidgetItem([name.upper()])
            item.setFont(0, bold)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(0, _ROLE, None)
            self.addTopLevelItem(item)
            item.setExpanded(True)
            self._groups[name] = item
        self._fill_analyses()
        self.currentItemChanged.connect(self._emit_selection)
        self.customContextMenuRequested.connect(self._emit_context)

    def _fill_analyses(self) -> None:
        group = self._groups["analyses"]
        for key, label in ANALYSES:
            item = QTreeWidgetItem([label])
            item.setData(0, _ROLE, key)
            group.addChild(item)
            if key == ANALYSIS_SEPARATOR_AFTER:
                separator = QTreeWidgetItem(["──────────"])
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setData(0, _ROLE, None)
                group.addChild(separator)

    def _reset(self, name: str) -> QTreeWidgetItem:
        group = self._groups[name]
        group.takeChildren()
        return group

    def set_models(self, entries: list[ModelEntry], pending: list[str]) -> None:
        group = self._reset("models")
        group.setText(0, f"MODELS ({len(entries)})")
        for entry in entries:
            item = QTreeWidgetItem([f"{status_symbol(entry.status, entry.integrity)} {entry.id}"])
            item.setData(0, _ROLE, entry.id)
            item.setToolTip(0, entry.error or entry.source_path)
            group.addChild(item)
        for name in pending:
            item = QTreeWidgetItem([f"… {name}"])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(0, _ROLE, None)
            group.addChild(item)

    def set_media(self, presets: list[str], user: list[MediumEntry]) -> None:
        group = self._reset("media")
        for name in presets:
            item = QTreeWidgetItem([name])
            item.setData(0, _ROLE, f"preset:{name}")
            item.setToolTip(0, "Installed medium preset")
            group.addChild(item)
        for entry in user:
            item = QTreeWidgetItem([f"{status_symbol('ok', entry.integrity)} {entry.id}"])
            item.setData(0, _ROLE, f"medium:{entry.id}")
            item.setToolTip(0, entry.source_path)
            group.addChild(item)

    def set_runs(self, entries: list[RunEntry], external: list[RunEntry]) -> None:
        group = self._reset("runs")
        for entry in [*entries, *external]:
            suffix = " (opened)" if entry in external else ""
            item = QTreeWidgetItem([f"{status_symbol(entry.status)} {entry.label}{suffix}"])
            item.setData(0, _ROLE, str(entry.path))
            item.setToolTip(0, f"{entry.status} · {entry.path}")
            group.addChild(item)

    def _group_of(self, item: QTreeWidgetItem | None) -> str | None:
        parent = None if item is None else item.parent()
        for name, group in self._groups.items():
            if parent is group:
                return name
        return None

    def _emit_selection(self, current: QTreeWidgetItem | None, _previous: object) -> None:
        group = self._group_of(current)
        key = None if current is None else current.data(0, _ROLE)
        if group is not None and isinstance(key, str):
            self.selection_changed.emit(group, key)

    def select(self, group: str, key: str) -> None:
        parent = self._groups[group]
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, _ROLE) == key:
                self.setCurrentItem(child)
                return

    def selected_keys(self, group: str) -> list[str]:
        parent = self._groups[group]
        return [
            str(parent.child(i).data(0, _ROLE))
            for i in range(parent.childCount())
            if parent.child(i).isSelected() and isinstance(parent.child(i).data(0, _ROLE), str)
        ]

    def _emit_context(self, point: QPoint) -> None:
        item = self.itemAt(point)
        group = self._group_of(item)
        if item is None or group is None:
            return
        clicked = item.data(0, _ROLE)
        if not isinstance(clicked, str):
            return  # separator and pending rows have nothing to act on
        keys = self.selected_keys(group)
        if not keys:
            keys = [clicked]
        self.context_requested.emit(group, keys)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt override
        files, _skipped = droppable_paths(list(event.mimeData().urls()))
        if files:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt override
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt override
        local = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if local:
            self.files_dropped.emit(local)
            event.acceptProposedAction()
        else:
            event.ignore()
