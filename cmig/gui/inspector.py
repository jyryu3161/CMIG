"""Right-hand inspector: details of the selected model, medium, run or analysis."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.project_session import RunEntry
from cmig.io.project import ModelEntry, Project, model_path

_SOLVER_TEXT = {
    "gurobi": "Gurobi full-flux",
    "osqp": "OSQP QP-only approximation",
}


def _row(label: str, value: object) -> str:
    shown = "not recorded" if value in (None, "", []) else value
    return f"<b>{html.escape(label)}</b>: {html.escape(str(shown))}<br>"


class InspectorPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(240)
        self.setMaximumWidth(420)
        self.title_label = QLabel("Nothing selected")
        self.title_label.setWordWrap(True)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        self.exchange_filter = QLineEdit("")
        self.exchange_filter.setPlaceholderText("Filter exchanges")
        self.exchange_filter.textChanged.connect(self._filter_exchanges)
        self.exchange_list = QListWidget()
        self.copy_command_btn = QPushButton("Copy Command")
        self.copy_command_btn.clicked.connect(self._copy_command)
        self.reveal_btn = QPushButton("Show in Finder")
        self.reveal_btn.clicked.connect(self._reveal)
        buttons = QHBoxLayout()
        buttons.addWidget(self.copy_command_btn)
        buttons.addWidget(self.reveal_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.details, 2)
        layout.addWidget(self.exchange_filter)
        layout.addWidget(self.exchange_list, 1)
        layout.addLayout(buttons)
        self._command = ""
        self._path: Path | None = None
        self.clear()

    def clear(self) -> None:
        self.title_label.setText("Nothing selected")
        self.details.setHtml("<i>Select a model, medium, analysis or run.</i>")
        self._set_exchanges(None)
        self._set_actions("", None)

    def _set_actions(self, command: str, path: Path | None) -> None:
        self._command, self._path = command, path
        self.copy_command_btn.setEnabled(bool(command))
        self.reveal_btn.setEnabled(path is not None)

    def _set_exchanges(self, exchanges: list[str] | None) -> None:
        self.exchange_list.clear()
        visible = exchanges is not None
        self.exchange_filter.setVisible(visible)
        self.exchange_list.setVisible(visible)
        self.exchange_filter.setText("")
        for exchange in exchanges or []:
            self.exchange_list.addItem(exchange)

    def _filter_exchanges(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.exchange_list.count()):
            item = self.exchange_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def show_model(
        self, project: Project, entry: ModelEntry, exchanges: list[str] | None
    ) -> None:
        self.title_label.setText(f"Model · {entry.id}")
        integrity = {
            "ok": "matches the checksum recorded when it was added",
            "changed": "changed since it was added — excluded from analyses",
            "missing": "missing from the project folder — excluded from analyses",
        }.get(entry.integrity, entry.integrity)
        counts = (
            f"{entry.n_reactions} reactions · {entry.n_metabolites} metabolites · "
            f"{entry.n_genes} genes"
            if entry.n_reactions is not None else None
        )
        coverage = (
            None if entry.namespace_coverage_pct is None
            else f"{entry.namespace_coverage_pct:.1f}%"
        )
        body = (
            _row("Check", entry.status)
            + _row("Error", entry.error)
            + _row("Size", counts)
            + _row("Biomass", ", ".join(entry.biomass))
            + _row("BiGG namespace coverage", coverage)
            + _row("Warnings", "; ".join(entry.warnings))
            + _row("File", integrity)
            + _row("SHA-256", entry.sha256[:12] + "…")
            + _row("Original", entry.source_path)
            + _row("Format", entry.format)
        )
        self.details.setHtml(body)
        self._set_exchanges(exchanges)
        self._set_actions("", model_path(project, entry))

    def show_medium(self, title: str, rows: list[tuple[str, str]], source: str) -> None:
        self.title_label.setText(f"Medium · {title}")
        table = "".join(
            f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in rows
        )
        self.details.setHtml(
            _row("Source", source)
            + f"<table><tr><th>Exchange</th><th>Uptake</th></tr>{table}</table>"
        )
        self._set_exchanges(None)
        self._set_actions("", Path(source) if source and Path(source).exists() else None)

    def show_run(self, entry: RunEntry, inspected: dict[str, object], command: str) -> None:
        self.title_label.setText(f"Run · {entry.label}")
        manifest = inspected.get("manifest")
        solver = manifest.get("solver") if isinstance(manifest, dict) else None
        body = (
            _row("Status", inspected.get("status", entry.status))
            + _row("Artifact integrity", inspected.get("artifact_integrity"))
            + _row("run_hash", inspected.get("run_hash"))
            + _row("Solver", _SOLVER_TEXT.get(str(solver), solver))
            + _row("Folder", entry.path)
        )
        self.details.setHtml(body)
        self._set_exchanges(None)
        self._set_actions(command, entry.path)

    def show_analysis(self, title: str, description: str, cli: str) -> None:
        self.title_label.setText(title)
        self.details.setHtml(f"{html.escape(description)}<br><br>" + _row("CLI", cli))
        self._set_exchanges(None)
        self._set_actions("", None)

    def current_command(self) -> str:
        return self._command

    def current_path(self) -> Path | None:
        return self._path

    def _copy_command(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and self._command:
            clipboard.setText(self._command)

    def _reveal(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if self._path is not None:
            target = self._path if self._path.is_dir() else self._path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
