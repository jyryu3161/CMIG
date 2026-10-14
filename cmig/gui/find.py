"""Project search (⌘F): the search table, ranking, and the toolbar search field."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QFocusEvent, QFont, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QWidget

GROUPS = (("model", "Models"), ("reaction", "Reactions"), ("metabolite", "Metabolites"),
          ("gene", "Genes"), ("medium", "Media"), ("run", "Runs"))
#: the kinds a model index holds (SearchTable.entities)
_ENTITY_KINDS = ("reaction", "metabolite", "gene")


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
    # Each entity is ranked once, however many models have it; only the rows shown are
    # expanded per model (a few thousand shared ids x hundreds of models must stay cheap).
    entities: dict[str, list[tuple[int, str, str, list[str]]]] = {}
    for (kind, key), (name, model_ids) in table.entities.items():
        if kind not in _ENTITY_KINDS:
            continue
        rank = _rank(q, key, name)
        if rank is not None:
            entities.setdefault(kind, []).append((rank, key, name, model_ids))
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
        rows: list[FindRow] = []
        if kind in entities:
            matches = sorted(entities[kind], key=lambda match: (match[0], match[1]))
            best, total = matches[0][0], 0
            for _r, key, name, model_ids in matches:
                total += len(model_ids)
                if len(rows) < per_group:
                    for model_id in sorted(model_ids)[: per_group - len(rows)]:
                        text = f"{key} · {model_id}" + (f" — {name}" if name else "")
                        rows.append(FindRow(kind, key, text, model_id))
        else:
            hits = sorted(found[kind], key=lambda hit: (hit[0], hit[1]))
            if not hits:
                continue
            best, total = hits[0][0], len(hits)
            rows = [hit[2] for hit in hits[:per_group]]
        ranked.append((best, position, FindGroup(kind, title, tuple(rows), total - len(rows))))
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
        host.installEventFilter(self)  # a resized window would leave the list misplaced

    def refresh(self) -> None:
        """Redraw an open result list (e.g. new search rows arrived)."""
        if self.popup.isVisible():
            self._refresh(self.text())

    def _selectable(self) -> list[int]:
        return [i for i in range(self.popup.count())
                if self.popup.item(i).data(Qt.ItemDataRole.UserRole) is not None]

    def _refresh(self, text: str) -> None:
        self.popup.clear()
        if len(text.strip()) < 2:
            self.popup.setVisible(False)  # nothing to find: the table is not even built
            return
        table = self._source()
        groups = find(table, text)
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
        if watched is self._host and event.type() == QEvent.Type.Resize:
            self.popup.setVisible(False)
        elif watched is self and event.type() == QEvent.Type.FocusOut and isinstance(
            event, QFocusEvent
        ):
            # Focus moved elsewhere: the list goes too (the list itself never takes focus;
            # the field's own context menu does not count as leaving it).
            if event.reason() != Qt.FocusReason.PopupFocusReason:
                self.popup.setVisible(False)
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
