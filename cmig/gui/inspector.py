"""Right-hand inspector: details of the selected model, medium, run or analysis."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.project_session import RunEntry
from cmig.io.project import (
    ModelEntry,
    Project,
    check_reason,
    check_reasons,
    confirmation_state,
    model_path,
    objective_warning_of,
)

_SOLVER_TEXT = {
    "gurobi": "Gurobi full-flux",
    "osqp": "OSQP QP-only approximation",
}
# `flux_report_status` as a solve manifest records it (see cmig.core.engine.FluxReportStatus).
# Only "full" may read as Gurobi full-flux; the two degraded tiers must not borrow that label.
_FLUX_REPORT_TEXT = {
    "full": _SOLVER_TEXT["gurobi"],
    "qp_only_approximate": _SOLVER_TEXT["osqp"],
    "fba_non_parsimonious": "Full flux, NON-parsimonious (pFBA stage failed)",
    "none": "No flux (solve failed)",
}


def _row(label: str, value: object) -> str:
    shown = "not recorded" if value in (None, "", []) else value
    return f"<b>{html.escape(label)}</b>: {html.escape(str(shown))}<br>"


def _component(components: object, name: str) -> object:
    """One entry of a workflow manifest's `components` (a list of [name, value] pairs)."""
    if isinstance(components, dict):
        return components.get(name)
    if isinstance(components, list):
        for item in components:
            if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] == name:
                return item[1]
    return None


def _solver_label(manifest: object) -> str | None:
    """The solver wording for a run, or None when the manifest does not record one.

    Solve manifests keep a dict (`flux_report_status`, `flux_solver`, `growth_solver`);
    workflow manifests only keep the requested solver inside the `solver_setting` component.
    Never returns a raw repr of whatever the manifest holds.
    """
    if not isinstance(manifest, dict):
        return None
    setting = manifest.get("solver")
    if setting is None:
        setting = _component(manifest.get("components"), "solver_setting")
    if isinstance(setting, dict):
        status = setting.get("flux_report_status")
        if isinstance(status, str) and status in _FLUX_REPORT_TEXT:
            return _FLUX_REPORT_TEXT[status]
        setting = setting.get("solver")
    return _SOLVER_TEXT.get(setting) if isinstance(setting, str) else None


class InspectorPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(240)
        self.setMaximumWidth(420)
        self.title_label = QLabel("Nothing selected")
        self.title_label.setWordWrap(True)
        # Titles carry file- and run-derived names; never let them render as markup.
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        self.copy_command_btn = QPushButton("Copy Command")
        self.copy_command_btn.clicked.connect(self._copy_command)
        self.reveal_btn = QPushButton("Show in Finder")
        self.reveal_btn.clicked.connect(self._reveal)
        buttons = QHBoxLayout()
        buttons.addWidget(self.copy_command_btn)
        buttons.addWidget(self.reveal_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.details, 1)
        layout.addLayout(buttons)
        self._command = ""
        self._path: Path | None = None
        self.clear()

    def clear(self) -> None:
        self.title_label.setText("Nothing selected")
        self.details.setHtml("<i>Select a model, medium, analysis or run.</i>")
        self._set_actions("", None)

    def _set_actions(self, command: str, path: Path | None) -> None:
        self._command, self._path = command, path
        self.copy_command_btn.setEnabled(bool(command))
        self.reveal_btn.setEnabled(path is not None)

    def show_model(self, project: Project, entry: ModelEntry) -> None:
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
        counts_ns = entry.namespace_mappings
        mappings = (None if counts_ns is None else
                    f"{counts_ns.get('resolved', 0)} of {counts_ns.get('total', 0)} reviewed")
        state = confirmation_state(entry)
        namespace = {
            "confirmed": "confirmed by you",
            "changed": "changed since confirmed",
        }.get(state, "not confirmed")
        terms = list(entry.biomass)
        warning = objective_warning_of(entry)
        objective = (None if not terms else
                     f"{terms[0]} (biomass)" if len(terms) == 1 and warning is None
                     else f"{len(terms)} {'term' if len(terms) == 1 else 'terms'} — "
                     f"{warning or 'not a single biomass reaction'}")
        # A completed check that found no error or warning says "none"; a model never checked,
        # or whose read failed before the review, keeps "not recorded".
        checked = entry.status in ("ok", "warning")
        body = (
            _row("Check", " · ".join(f"{s} {t}" for s, t in check_reasons(entry)))
            + _row("Warnings", "; ".join(entry.warnings) or ("none" if checked else None))
            + _row("Error", entry.error or ("none" if checked else None))
            + _row("Size", counts)
            + _row("Objective", objective)
            + _row("Namespace", namespace)
            + _row("Namespace mappings", mappings)
            + _row("File", integrity)
            + _row("SHA-256", entry.sha256[:12] + "…" if entry.sha256 else None)
            + _row("Original", entry.source_path)
            + _row("Format", entry.format)
        )
        self.details.setHtml(body)
        self._set_actions("", model_path(project, entry))

    def show_project_summary(self, project: Project, runs: list[RunEntry]) -> None:
        ready = sum(1 for m in project.models if check_reason(m)[0] == "✓")
        last = max(runs, key=lambda r: r.mtime, default=None)
        self.title_label.setText(f"Project · {project.name}")
        self.details.setHtml(
            _row("Models", f"{len(project.models)} ({ready} ready)")
            + _row("Project media", str(len(project.media)))
            + _row("Runs", str(len(runs)))
            + _row("Last run", None if last is None else f"{last.label} · {last.status}")
        )
        self._set_actions("", project.root)

    def show_medium(self, title: str, rows: list[tuple[str, str]], source: str) -> None:
        self.title_label.setText(f"Medium · {title}")
        table = "".join(
            f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in rows
        )
        self.details.setHtml(
            _row("Source", source)
            + f"<table><tr><th>Exchange</th><th>Uptake</th></tr>{table}</table>"
        )
        self._set_actions("", Path(source) if source and Path(source).exists() else None)

    def show_run(self, entry: RunEntry, inspected: dict[str, object], command: str) -> None:
        self.title_label.setText(f"Run · {entry.label}")
        body = (
            _row("Status", inspected.get("status", entry.status))
            + _row("Artifact integrity", inspected.get("artifact_integrity"))
            + _row("run_hash", inspected.get("run_hash"))
            + _row("Solver", _solver_label(inspected.get("manifest")))
            + _row("Folder", entry.path)
        )
        self.details.setHtml(body)
        self._set_actions(command, entry.path)

    def show_analysis(self, title: str, description: str, cli: str) -> None:
        self.title_label.setText(title)
        self.details.setHtml(f"{html.escape(description)}<br><br>" + _row("CLI", cli))
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
