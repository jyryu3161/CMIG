"""Search the AGORA2 catalogue and choose strains to download into the project."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

#: Most strains one search lists (passed to `agora2-list --limit`); a genus such as
#: Escherichia has about a thousand, and a list that long is not a useful pick list.
SEARCH_LIMIT = 500


class Agora2Dialog(QDialog):
    def __init__(self, list_fn: Callable[[str], list[str]]) -> None:
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
            self.results.addItems(strains)
            cut = f" Showing the first {SEARCH_LIMIT}; narrow the search." if (
                len(strains) >= SEARCH_LIMIT) else ""
            self.status.setText(f"{len(strains)} strain(s) match {query!r}.{cut}")
        finally:
            QApplication.restoreOverrideCursor()
            self.search_btn.setEnabled(True)
            self._update_buttons()

    def _update_buttons(self) -> None:
        self.add_btn.setEnabled(bool(self.results.selectedItems()))

    def selected_strains(self) -> list[str]:
        return [item.text() for item in self.results.selectedItems()]
