"""Search the AGORA2 catalogue and choose strains to download into the project."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from cmig.io.agora2 import human_bytes

#: Most strains one search lists (passed to `agora2-list --limit`); a genus such as
#: Escherichia has about a thousand, and a list that long is not a useful pick list.
SEARCH_LIMIT = 500

#: Above this many bytes (or with any size unknown) a download asks first.
CONFIRM_BYTES = 1024**3

#: The catalogue's own size notation, as `cmig.io.agora2.estimated_bytes` reads it ("15M").
_SIZE_RE = re.compile(r"^([\d.]+)([KMG])?$")
_SIZE_SCALE = {"K": 1024, "M": 1024**2, "G": 1024**3, None: 1}


class Agora2Strain(str):
    """A strain id that also carries the size the catalogue publishes for it ("" = none)."""

    published_size: str

    def __new__(cls, strain_id: str, published_size: str = "") -> Agora2Strain:
        strain = super().__new__(cls, strain_id)
        strain.published_size = published_size
        return strain


def published_bytes(text: str) -> int | None:
    """Bytes in a published size such as "15M", or None when it is missing or unreadable."""
    match = _SIZE_RE.match(text.strip().upper())
    if match is None:
        return None
    try:
        return int(float(match.group(1)) * _SIZE_SCALE[match.group(2)])
    except ValueError:
        return None


def download_estimate(strains: Sequence[str]) -> tuple[int, int]:
    """(bytes of the strains whose size is published, how many have no usable size)."""
    known = 0
    unknown = 0
    for strain in strains:
        size = published_bytes(getattr(strain, "published_size", ""))
        if size is None:
            unknown += 1
        else:
            known += size
    return known, unknown


class Agora2Dialog(QDialog):
    def __init__(self, list_fn: Callable[[str], Sequence[str]]) -> None:
        super().__init__()
        self.setWindowTitle("Add Models from AGORA2")
        self._list_fn = list_fn
        self.search_input = QLineEdit("")
        self.search_input.setPlaceholderText("Genus or strain, e.g. Roseburia")
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.status = QLabel("Downloads come from vmh.life (AGORA2 v2.01) and are converted to "
                             "BiGG-style ids.")
        self.status.setWordWrap(True)
        self.results = QListWidget()
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results.itemSelectionChanged.connect(self._update_buttons)
        self.selection_summary = QLabel("")
        self.add_btn = QPushButton("Add to Project")
        self.add_btn.setDefault(True)
        self.add_btn.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        top = QHBoxLayout()
        top.addWidget(self.search_input)
        top.addWidget(self.search_btn)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(cancel)
        bottom.addWidget(self.add_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.status)
        layout.addWidget(self.results)
        layout.addWidget(self.selection_summary)
        layout.addLayout(bottom)
        self._update_buttons()

    def _search(self) -> None:
        query = self.search_input.text().strip()
        if not query or not self.search_btn.isEnabled():
            return
        # The lookup runs on this (GUI) thread and the first one downloads the catalogue
        # index, so say so and keep a second click or Enter out until it returns.
        self.search_btn.setEnabled(False)
        self.status.setText("Searching the AGORA2 catalogue…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            QApplication.processEvents()
            strains = self._list_fn(query)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never raised
            # A list left over from an earlier search would stay selectable under this error.
            self.results.clear()
            self.status.setText(f"Catalogue lookup failed: {exc}")
        else:
            self.results.clear()
            for strain in strains:
                item = QListWidgetItem(str(strain))
                size = getattr(strain, "published_size", "")
                item.setData(Qt.ItemDataRole.UserRole, size)
                if size:
                    item.setToolTip(f"Published size: {size}")
                self.results.addItem(item)
            cut = f" Showing the first {SEARCH_LIMIT}; narrow the search." if (
                len(strains) >= SEARCH_LIMIT) else ""
            self.status.setText(f"{len(strains)} strain(s) match {query!r}.{cut}")
        finally:
            QApplication.restoreOverrideCursor()
            self.search_btn.setEnabled(True)
            self._update_buttons()

    def _update_buttons(self) -> None:
        chosen = self.selected_entries()
        self.add_btn.setEnabled(bool(chosen))
        if not chosen:
            self.selection_summary.setText("")
            return
        known, unknown = download_estimate(chosen)
        if not unknown:
            size = f"about {human_bytes(known)} to download"
        elif known:
            size = f"{unknown} of unknown size, at least {human_bytes(known)} to download"
        else:
            size = "size unknown"
        self.selection_summary.setText(f"{len(chosen)} selected · {size}")

    def selected_entries(self) -> list[Agora2Strain]:
        """The selected strains, each with the size the catalogue published for it."""
        return [
            Agora2Strain(item.text(), str(item.data(Qt.ItemDataRole.UserRole) or ""))
            for item in self.results.selectedItems()
        ]

    def selected_strains(self) -> list[str]:
        return [item.text() for item in self.results.selectedItems()]
