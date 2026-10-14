"""Project search (⌘F): the search table, ranking, and the toolbar search field."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QWidget

GROUPS = (("model", "Models"), ("reaction", "Reactions"), ("metabolite", "Metabolites"),
          ("gene", "Genes"), ("medium", "Media"), ("run", "Runs"))


@dataclass(frozen=True)
class FindRow:
    kind: str
    key: str
    text: str
    model: str | None = None


@dataclass(frozen=True)
class FindGroup:
    kind: str
    title: str
    rows: tuple[FindRow, ...]
    more: int


@dataclass
class SearchTable:
    models: list[tuple[str, str]] = field(default_factory=list)
    #: (kind, id) -> (name, ids of the models that have it): one entry, however many models
    entities: dict[tuple[str, str], tuple[str, list[str]]] = field(default_factory=dict)
    media: list[tuple[str, str, list[str]]] = field(default_factory=list)
    runs: list[tuple[str, str, str]] = field(default_factory=list)
    indexing: int = 0
    unreadable: int = 0


def build_table(
    models: list[tuple[str, str]],
    rows_by_model: dict[str, list[tuple[str, str, str]]],
    media: list[tuple[str, str, list[str]]],
    runs: list[tuple[str, str, str]],
    *,
    indexing: int = 0,
    unreadable: int = 0,
) -> SearchTable:
    table = SearchTable(models=list(models), media=list(media), runs=list(runs),
                        indexing=indexing, unreadable=unreadable)
    for model_id, rows in rows_by_model.items():
        for kind, key, name in rows:
            slot = table.entities.get((kind, key))
            if slot is None:
                table.entities[(kind, key)] = (name, [model_id])
            else:
                slot[1].append(model_id)
    return table


def _rank(query: str, key: str, *texts: str) -> int | None:
    lowered = key.lower()
    if lowered == query:
        return 0
    if lowered.startswith(query):
        return 1
    if query in lowered or any(query in text.lower() for text in texts):
        return 2
    return None


def find(table: SearchTable, query: str, per_group: int = 8) -> list[FindGroup]:
    q = query.strip().lower()
    if len(q) < 2:
        return []
    found: dict[str, list[tuple[int, str, FindRow]]] = {kind: [] for kind, _t in GROUPS}
    for model_id, file_name in table.models:
        rank = _rank(q, model_id, file_name)
        if rank is not None:
            found["model"].append(
                (rank, model_id, FindRow("model", model_id, f"{model_id} · {file_name}",
                                         model_id))
            )
    for (kind, key), (name, model_ids) in table.entities.items():
        rank = _rank(q, key, name)
        if rank is None or kind not in found:
            continue
        for model_id in model_ids:
            text = f"{key} · {model_id}" + (f" — {name}" if name else "")
            found[kind].append((rank, f"{key}\0{model_id}",
                                FindRow(kind, key, text, model_id)))
    for ref, label, exchanges in table.media:
        rank = _rank(q, label, *exchanges)
        if rank is not None:
            found["medium"].append((rank, label, FindRow("medium", ref, label)))
    for path, name, label in table.runs:
        rank = _rank(q, name, label)
        if rank is not None:
            found["run"].append((rank, name, FindRow("run", path, label)))
    # Groups go by their best match (an exact id first), then in GROUPS order.
    ranked: list[tuple[int, int, FindGroup]] = []
    for position, (kind, title) in enumerate(GROUPS):
        hits = sorted(found[kind], key=lambda hit: (hit[0], hit[1]))
        if hits:
            ranked.append((hits[0][0], position,
                           FindGroup(kind, title, tuple(h[2] for h in hits[:per_group]),
                                     max(0, len(hits) - per_group))))
    return [group for _rank_, _position, group in sorted(ranked, key=lambda r: r[:2])]


def footer_lines(table: SearchTable) -> list[str]:
    lines = []
    if table.indexing:
        lines.append(f"{table.indexing} model{'' if table.indexing == 1 else 's'} "
                     "still indexing")
    if table.unreadable:
        lines.append(f"{table.unreadable} model{'' if table.unreadable == 1 else 's'} "
                     "could not be searched")
    return lines


class FindField(QLineEdit):
    """The toolbar search field and its result list (shown under it, inside the window)."""

    activated = Signal(str, str, object)

    def __init__(self, source: Callable[[], SearchTable], host: QWidget) -> None:
        super().__init__()
        self._source = source
        self._host = host
        self.setPlaceholderText("Search project")
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(260)
        self.popup = QListWidget(host)
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setVisible(False)
        self.popup.itemClicked.connect(self._activate_item)
        self.textChanged.connect(self._refresh)
        self.installEventFilter(self)

    def _selectable(self) -> list[int]:
        return [i for i in range(self.popup.count())
                if self.popup.item(i).data(Qt.ItemDataRole.UserRole) is not None]

    def _refresh(self, text: str) -> None:
        self.popup.clear()
        table = self._source()
        groups = find(table, text)
        if not groups and len(text.strip()) < 2:
            self.popup.setVisible(False)
            return
        bold = QFont(self.popup.font())
        bold.setBold(True)
        for group in groups:
            header = QListWidgetItem(group.title)
            header.setFont(bold)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.popup.addItem(header)
            for row in group.rows:
                item = QListWidgetItem("   " + row.text)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.popup.addItem(item)
            if group.more:
                more = QListWidgetItem(f"   +{group.more} more — refine the search")
                more.setFlags(Qt.ItemFlag.NoItemFlags)
                self.popup.addItem(more)
        if not groups:
            none = QListWidgetItem("No matches")
            none.setFlags(Qt.ItemFlag.NoItemFlags)
            self.popup.addItem(none)
        for line in footer_lines(table):
            note = QListWidgetItem(line)
            note.setFlags(Qt.ItemFlag.NoItemFlags)
            self.popup.addItem(note)
        selectable = self._selectable()
        if selectable:
            self.popup.setCurrentRow(selectable[0])
        corner = self.mapTo(self._host, QPoint(0, self.height()))
        width = max(self.width(), 420)
        x = min(corner.x(), max(0, self._host.width() - width))
        height = min(max(self.popup.sizeHintForRow(0), 18) * self.popup.count() + 6, 420)
        self.popup.setGeometry(x, corner.y(), width, height)
        self.popup.setVisible(True)
        self.popup.raise_()

    def _move(self, step: int) -> None:
        selectable = self._selectable()
        if not selectable:
            return
        current = self.popup.currentRow()
        later = [i for i in selectable if (i > current if step > 0 else i < current)]
        target = (later[0] if step > 0 else later[-1]) if later else current
        self.popup.setCurrentRow(target)

    def _activate_item(self, item: QListWidgetItem | None) -> None:
        row = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if isinstance(row, FindRow):
            self.popup.setVisible(False)
            self.activated.emit(row.kind, row.key, row.model)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self and event.type() == QEvent.Type.KeyPress and isinstance(
            event, QKeyEvent
        ):
            key = event.key()
            if key == Qt.Key.Key_Down and self.popup.isVisible():
                self._move(1)
                return True
            if key == Qt.Key.Key_Up and self.popup.isVisible():
                self._move(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.popup.isVisible():
                self._activate_item(self.popup.currentItem())
                return True
            if key == Qt.Key.Key_Escape:
                if self.popup.isVisible():
                    self.popup.setVisible(False)
                else:
                    self.clear()
                return True
        return super().eventFilter(watched, event)
