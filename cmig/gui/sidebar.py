"""Workspace source list: MODELS, MEDIA, ANALYSES and RUNS (two levels, HIG sidebar)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from cmig.gui.project_session import RunEntry
from cmig.io.project import MediumEntry, ModelEntry, model_import_candidates

ANALYSIS_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Community", [("search", "Combination Search"), ("gene_ko", "Gene Knockout"),
                   ("strain_growth", "Strain Growth"), ("ratio_impact", "Ratio Impact"),
                   ("community", "Community Solve")]),
    ("Host", [("host", "Host–Microbe"), ("host_search", "Host Combination Search")]),
    ("Dynamics", [("dfba", "dFBA"), ("spatial", "Spatial Preview")]),
    ("Tools", [("medium", "Medium Editor"), ("sweep", "Sweep"),
               ("sandbox", "Constraint Sandbox"), ("compare", "Compare Runs")]),
]
ANALYSES: list[tuple[str, str]] = [item for _title, items in ANALYSIS_GROUPS for item in items]
_GROUPS = ("models", "media", "analyses", "runs")
_ROLE = Qt.ItemDataRole.UserRole


_STATUS_SYMBOLS = {
    "ok": "✓",
    "warning": "⚠",
    "degraded": "⚠",
    "failed": "✗",
    "unreadable": "✗",
    "cancelled": "⊘",
    "pending": "…",
}
_INTEGRITY_TIPS = {
    "changed": "File changed since it was added",
    "missing": "File missing from the project",
}


def status_symbol(status: str, integrity: str = "ok") -> str:
    """Worst of status and integrity: a failure stays ✗, any other file problem shows ⚠."""
    symbol = _STATUS_SYMBOLS.get(status, "?")
    if symbol != "✗" and integrity != "ok":
        return "⚠"
    return symbol


def _integrity_tip(integrity: str) -> str | None:
    if integrity == "ok":
        return None
    return _INTEGRITY_TIPS.get(integrity, f"File integrity: {integrity}")


def droppable_paths(urls: list[QUrl]) -> tuple[list[Path], int]:
    """The dropped folders and model-named files, and how many dropped items were left out.

    Runs inside Qt drag handlers on the GUI thread, so nothing is listed or read here: a
    folder is taken as it is and a file by its name. The import job searches the folders,
    skips what is not a model and reports a folder it cannot read.
    """
    local = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
    found, skipped = model_import_candidates(local)
    return found, skipped + len(urls) - len(local)


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
        self._drag_ok = False
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
        for index, (_title, items) in enumerate(ANALYSIS_GROUPS):
            if index:
                separator = QTreeWidgetItem(["──────────"])
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setData(0, _ROLE, None)
                group.addChild(separator)
            for key, label in items:
                item = QTreeWidgetItem([label])
                item.setData(0, _ROLE, key)
                group.addChild(item)

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
            problems = [_integrity_tip(entry.integrity), entry.error]
            item.setToolTip(0, "\n".join(p for p in problems if p) or entry.source_path)
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
            item.setToolTip(0, _integrity_tip(entry.integrity) or entry.source_path)
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
        self._drag_ok = bool(files)
        if self._drag_ok:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt override
        # Keep the decision made on enter: re-accepting here would make a rejected drag droppable.
        if self._drag_ok:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt override
        urls = list(event.mimeData().urls())
        files, _skipped = droppable_paths(urls)
        local = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
        self._drag_ok = False
        if files:
            self.files_dropped.emit(local)
            event.acceptProposedAction()
        else:
            event.ignore()
