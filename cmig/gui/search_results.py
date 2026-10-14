"""Ranked-result view shared by Search, Gene KO, Strain Growth, Ratio Impact and Host Search pages."""  # noqa: E501

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, QUrl
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.analysis_page import ResultsArea, mark_computed_headers, paint_computed

#: Default SearchView column labels. Adapters may override them per workflow so a growth
#: rate is never displayed under a header that says "Flux" (round-5 P2 F7/F21).
SEARCH_COLUMNS = ("Members", "Target", "Score", "Flux", "Growth", "FVA Range", "Status")

_DIAGNOSTIC_COLOR = QColor("#d62728")
#: Score, Flux, Growth and FVA Range are computed; Members and Target are the inputs
_COMPUTED_COLUMNS = (2, 3, 4, 5)

MERGE_MEDIUM_WARNING = (
    "Metabolites missing from the medium file stay at the model defaults (e.g. unlimited "
    "oxygen); use exact for reported results."
)


def medium_mode_text(medium: str, mode: str) -> str:
    """One line naming the Search medium mode explicitly (merge carries its warning)."""
    if not medium:
        return "medium: model default (medium mode not applied)"
    if mode == "merge":
        return f"medium: merge — {MERGE_MEDIUM_WARNING}"
    return "medium: exact"


def validate_search_summary(summary: dict[str, object]) -> None:
    """Validate the ranking fields consumed by SearchView before publishing a run.

    Missing or null numeric readouts mean unknown in older and failed-run schemas.
    A present value of another type cannot silently become that unknown readout.
    """
    if "warnings" in summary and not isinstance(summary["warnings"], list):
        raise ValueError("search summary warnings must be a list")
    if "n_pareto_points" in summary and summary["n_pareto_points"] is not None:
        try:
            int(str(summary["n_pareto_points"]))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("search summary n_pareto_points must be an integer") from exc
    ranked = summary.get("top_ranked")
    if isinstance(ranked, list):
        groups = [("top_ranked", ranked)]
    elif isinstance(ranked, dict):
        if not all(isinstance(key, str) for key in ranked):
            raise ValueError("search ranking target names must be strings")
        groups = [(f"top_ranked.{key}", rows) for key, rows in ranked.items()]
    else:
        raise ValueError("search summary has no valid top_ranked collection")

    def numeric(value: object, field: str) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f"{field} must be numeric or null")
        try:
            if not math.isfinite(float(value)):
                raise ValueError(f"{field} must be finite or null")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{field} must be numeric or null") from exc

    for group, rows in groups:
        if not isinstance(rows, list):
            raise ValueError(f"{group} must be a list")
        for index, row in enumerate(rows):
            where = f"{group}[{index}]"
            if not isinstance(row, dict):
                raise ValueError(f"{where} must be an object")
            if "members" in row and (
                not isinstance(row["members"], list)
                or not all(isinstance(member, str) for member in row["members"])
            ):
                raise ValueError(f"{where}.members must be a list of names")
            for field in (
                "score", "weighted_score", "target_flux", "community_growth",
                "robustness_fva_lo", "robustness_fva_hi",
            ):
                if field in row:
                    numeric(row[field], f"{where}.{field}")
            if "target_fluxes" in row:
                fluxes = row["target_fluxes"]
                if not isinstance(fluxes, dict) or not all(
                    isinstance(target, str) for target in fluxes
                ):
                    raise ValueError(f"{where}.target_fluxes must be an object")
                for target, flux in fluxes.items():
                    numeric(flux, f"{where}.target_fluxes.{target}")
            for field in ("status", "robustness_status", "aux_text"):
                if field in row and row[field] is not None and not isinstance(row[field], str):
                    raise ValueError(f"{where}.{field} must be text or null")
            if "diagnostic" in row:
                diagnostic = row["diagnostic"]
                if diagnostic is not None and not isinstance(diagnostic, (str, dict)):
                    raise ValueError(f"{where}.diagnostic must be text or an object")
                if isinstance(diagnostic, dict):
                    for field in ("code", "message", "detail"):
                        if (field in diagnostic and diagnostic[field] is not None
                                and not isinstance(diagnostic[field], str)):
                            raise ValueError(f"{where}.diagnostic.{field} must be text or null")


class _NoEditorDelegate(QStyledItemDelegate):
    """Item delegate that can never produce an editor.

    `setEditTriggers(NoEditTriggers)` closes every *user* path into edit mode, but it is not
    the whole guarantee: `QAbstractItemView.edit(index, AllEditTriggers, None)` bypasses the
    trigger check entirely, and the items themselves still carry `ItemIsEditable`. Refusing
    to build an editor closes the remaining door in one place, for every read-only table,
    without touching the ~15 population loops that create the items.
    """

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        # Qt accepts a null QWidget pointer to refuse editing, while PySide6's stub declares
        # a non-optional QWidget return. The cast keeps the exact override signature without
        # changing the runtime null-pointer contract.
        return cast(QWidget, None)


def make_read_only(table: QTableWidget) -> QTableWidget:
    """Mark a table as *computed output*: the user must not be able to type into it.

    A hand-typed 999.9 is visually indistinguishable from a solved flux, so every table
    that renders a computed number is read-only. Input tables (medium, bounds, community
    members) deliberately stay editable.

    Two layers, because neither alone is sufficient (see `_NoEditorDelegate`): edit triggers
    close the user paths, and the delegate closes the programmatic `edit()` path. Populate
    these tables with `read_only_item()` so the *model* also reports the cell as
    non-editable — that third layer is per-item because doing it from here (via an
    `itemChanged` hook) costs a Python round trip per cell and measured 46 ms on a 2712-row
    profile against a 3 ms baseline.
    """
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setItemDelegate(_NoEditorDelegate(table))  # parented, so it outlives this call
    return table


def read_only_item(text: str) -> QTableWidgetItem:
    """Build a cell for a computed value, with `ItemIsEditable` already cleared.

    Clearing the flag before the item is inserted costs one C++ call and emits nothing,
    where clearing it afterwards would emit `itemChanged` for every cell in the table.
    """
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item



class SearchResultsPanel(QWidget):
    """Ranking table, run details, candidate inspector and saved figure of one result."""

    def __init__(
        self,
        request_fields: Callable[[str], dict[str, str]],
        status: QLabel | None = None,
        area: ResultsArea | None = None,
    ) -> None:
        super().__init__()
        self._request_fields = request_fields
        self._area = area
        self._own_status = status is None
        self.status = QLabel("") if status is None else status
        if self._own_status:
            self.status.setWordWrap(True)
            self.status.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
        self.export_figure_btn = QPushButton("Export Figure")
        self.export_figure_btn.setEnabled(False)
        self.figure_mode_combo = QComboBox()
        self.figure_mode_combo.currentTextChanged.connect(self.refresh_figure_mode)
        figure_row = QHBoxLayout()
        figure_row.addWidget(QLabel("Figure"))
        figure_row.addWidget(self.figure_mode_combo)
        figure_row.addWidget(self.export_figure_btn)
        figure_row.addStretch(1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(115)
        self.details.setPlaceholderText("Run conditions, warnings and diagnostics appear here.")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(list(SEARCH_COLUMNS))
        mark_computed_headers(self.table, _COMPUTED_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.table)
        self.pareto_label = QLabel("")
        # Read-only candidate inspector: shows the recorded summary/evaluation values of the
        # ONE selected row. Each row carries the index of its own summary record, so the
        # mapping never depends on table order or on members alone.
        self.inspector_label = QLabel("Selected candidate — recorded values (read-only)")
        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setMaximumHeight(160)
        self.inspector.setPlaceholderText(
            "Select a ranking row to see that candidate's recorded details."
        )
        self._row_records: list[tuple[str, dict[object, object]]] = []
        self._inspector_summary: dict[str, object] = {}
        self._evaluations: dict[str, object] | None = None
        self._evaluations_error: str | None = None
        self.table.itemSelectionChanged.connect(self._refresh_inspector)
        self.current_run_dir: Path | None = None
        try:
            from PySide6.QtSvgWidgets import QSvgWidget

            self.figure_view: QWidget = QSvgWidget()
            # A saved figure is dark text on a transparent page, made for white paper: show it
            # on white in a dark appearance too (the web fallback below does the same).
            page = self.figure_view.palette()
            page.setColor(QPalette.ColorRole.Window, QColor(Qt.GlobalColor.white))
            self.figure_view.setPalette(page)
            self.figure_view.setAutoFillBackground(True)
        except ImportError:  # pragma: no cover - optional GUI extra
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView

                self.figure_view = QWebEngineView()
            except ImportError:
                self.figure_view = QLabel("SVG preview is unavailable.")
        self.figure_placeholder = QLabel("No search result loaded.")
        self.figure_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.figure_stack = QStackedWidget()
        self.figure_stack.setMinimumHeight(320)
        self.figure_stack.addWidget(self.figure_view)
        self.figure_stack.addWidget(self.figure_placeholder)
        self.figure_stack.setCurrentWidget(self.figure_placeholder)
        self._displayed_kind: str | None = None
        self._displayed_request: dict[str, str] | None = None
        self._executed_request: dict[str, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(figure_row)
        if self._own_status:
            layout.addWidget(self.status)
        layout.addWidget(self.details)
        layout.addWidget(self.table)
        layout.addWidget(self.inspector_label)
        layout.addWidget(self.inspector)
        layout.addWidget(self.pareto_label)
        layout.addWidget(self.figure_stack)

    def superseded_note(self, requested: dict[str, str], kind: str) -> str:
        """Describe how the inputs on screen have moved away from a completed request.

        Invalidation only covers the *idle* case. A search that is already solving keeps its
        result, so on completion the numbers for the OLD inputs would repopulate the table
        under the NEW ones with nothing to say so. The run is real and stays on screen — it
        is labelled, not discarded.
        """
        current = self._request_fields(kind)
        changed = [
            (key, was, current[key])
            for key, was in requested.items()
            if key in current and current[key] != was
        ]
        if not changed:
            return ""
        detail = "; ".join(f"{key}: {was} → {now}" for key, was, now in changed)
        return (
            f" ⚠ computed for a superseded request ({detail}) — "
            f"the inputs on screen have changed since; re-run to match them"
        )

    def effective_note(self, requested: dict[str, str], kind: str) -> str:
        medium = requested.get("medium") or "model default"
        policy = "exact replacement" if requested.get("medium") else "model default"
        if kind == "gene_ko":
            return (f"Executed Gene KO: medium={medium} ({policy}); "
                    f"direction={requested['direction']}; target growth fraction="
                    f"{requested['growth_fraction']}")
        if kind in ("strain_growth", "abundance_impact"):
            return (f"Executed {kind}: medium={medium} ({policy}); "
                    f"cooperative tradeoff f={requested['cooperative_tradeoff']}; "
                    "single-medium=community for Strain Growth; Search direction and "
                    "target growth fraction do not apply")
        return ""

    def invalidate_results(self, *_args: object) -> None:
        """Drop the displayed ranking when the request that produced it no longer applies."""
        if self.table.rowCount() == 0 and self.current_run_dir is None:
            return
        if _args and self._displayed_request is not None and self._displayed_kind is not None:
            if self._request_fields(self._displayed_kind) == self._displayed_request:
                return
        self._clear_inspector()
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(list(SEARCH_COLUMNS))
        mark_computed_headers(self.table, _COMPUTED_COLUMNS)
        self.pareto_label.setText("")
        self.current_run_dir = None
        self._displayed_kind = None
        self._displayed_request = None
        self._executed_request = None
        self._refresh_figure_choices()
        self.figure_stack.setCurrentWidget(self.figure_placeholder)
        self.figure_placeholder.setText("Inputs changed — no figure loaded.")
        self.export_figure_btn.setEnabled(False)
        self.details.clear()
        self.status.setText("Inputs changed — previous result cleared; re-run to update.")
        if self._area is not None:
            self._area.show_empty()

    def _clear_inspector(self) -> None:
        self._row_records = []
        self._inspector_summary = {}
        self._evaluations = None
        self._evaluations_error = None
        self.inspector.clear()

    def row_record(self, row: int) -> dict[object, object] | None:
        """The summary record the given table row was built from (None if none)."""
        item = self.table.item(row, 0)
        index = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int) and 0 <= index < len(self._row_records):
            return self._row_records[index][1]
        return None

    def _refresh_inspector(self) -> None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            self.inspector.clear()
            return
        item = self.table.item(rows.pop(), 0)
        index = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(self._row_records):
            self.inspector.clear()
            return
        group, record = self._row_records[index]
        self.inspector.setPlainText("\n".join(self._inspector_lines(group, record)))

    def _inspector_lines(self, group: str, record: dict[object, object]) -> list[str]:
        """Render only recorded values; anything absent is "not recorded", never 0."""
        summary = self._inspector_summary
        pareto_metric = summary.get("metric") == "pareto"
        lines = [
            f"Rank: {_recorded(record, 'rank')}",
            f"Members: {_recorded(record, 'members')}",
            f"Effective members: {_recorded(record, 'effective_members')}",
            f"Status: {_recorded(record, 'status')}",
        ]
        fluxes = record.get("target_fluxes")
        if isinstance(fluxes, dict):
            scores = record.get("target_scores")
            score_map = scores if isinstance(scores, dict) else {}
            listed = summary.get("targets")
            order = [str(t) for t in listed] if isinstance(listed, list) else []
            order += [str(t) for t in (*fluxes, *score_map) if str(t) not in order]
            lines.append(f"Weighted score: {_recorded(record, 'weighted_score')}")
            lines.append("Per-target flux and contribution:")
            for target in order:
                if target not in fluxes and target not in score_map:
                    continue
                flux = _format_recorded(fluxes.get(target))
                contribution = _format_recorded(score_map.get(target))
                lines.append(f"  {target}: flux {flux} · contribution {contribution}")
            basis = record.get("flux_basis")
            basis_text = (
                _NOT_RECORDED if basis is None
                else f"{_FLUX_BASIS_TEXT[basis]} ({basis})" if basis in _FLUX_BASIS_TEXT
                else str(basis)
            )
            lines.append(f"Flux basis: {basis_text}")
            missing = record.get("missing_targets")
            lines.append("Missing targets: " + (
                _NOT_RECORDED if missing is None
                else "none" if isinstance(missing, list) and not missing
                else ", ".join(str(m) for m in missing) if isinstance(missing, list)
                else str(missing)
            ))
            lines.append(f"Sampling status: {_recorded(record, 'sampling_status')}")
            if pareto_metric:
                lines.append(f"On Pareto frontier: {_recorded(record, 'pareto')}")
        else:
            lines.append(f"Target: {group or _NOT_RECORDED}")
            lines.append(f"Score: {_recorded(record, 'score')}")
            lines.append(f"Target flux: {_recorded(record, 'target_flux')}")
            lo = _optional_float(record.get("robustness_fva_lo"))
            hi = _optional_float(record.get("robustness_fva_hi"))
            lines.append("FVA range: " + (
                f"{lo:.6g}..{hi:.6g}" if lo is not None and hi is not None else _NOT_RECORDED
            ))
            if "robustness_status" in record:
                lines.append(f"FVA status: {_recorded(record, 'robustness_status')}")
        lines.append(f"Community growth: {_recorded(record, 'community_growth')}")
        lines.append(f"Member growth: {_recorded(record, 'member_growth')}")
        lines.append(f"Abundances: {_recorded(record, 'abundances')}")
        diagnostic = record.get("diagnostic", _ABSENT)
        lines.append("Diagnostic: " + (
            _NOT_RECORDED if diagnostic is _ABSENT
            else "none" if diagnostic is None or diagnostic == ""
            else _diagnostic_text(diagnostic)
        ))
        if self._displayed_kind != "search" or self.current_run_dir is None:
            return lines
        if self._evaluations_error is not None:
            lines.append(f"search_evaluations.json: unreadable ({self._evaluations_error})")
            lines.append("Timings: unreadable")
            if pareto_metric:
                lines.append("Pareto ε attempts: unreadable")
            return lines
        evaluations = self._evaluations or {}
        match = _matching_evaluation(record, evaluations.get("rows"))
        timings = None if match is None else match.get("timings")
        lines.append(f"Timings: {_format_recorded(timings)}")
        if pareto_metric:
            lines.extend(_pareto_attempt_lines(record, evaluations))
        return lines

    def selected_figure_artifact(self) -> str:
        return str(self.figure_mode_combo.currentData() or "")

    def _refresh_figure_choices(self) -> None:
        choices = (
            ("Ranking", "search_plot.svg"), ("Scatter", "search_scatter.svg"),
            ("Ranking", "host_search_plot.svg"), ("Ranking", "gene_ko_plot.svg"),
            ("Ranking", "strain_growth_plot.svg"),
            ("Ranking", "abundance_impact_plot.svg"),
            ("Pareto trade-off", "search_pareto.svg"),
        )
        self.figure_mode_combo.blockSignals(True)
        self.figure_mode_combo.clear()
        if self.current_run_dir is not None:
            for label, name in choices:
                if (self.current_run_dir / name).is_file():
                    self.figure_mode_combo.addItem(label, name)
        self.figure_mode_combo.blockSignals(False)

    def refresh_figure_mode(self, _mode: str | None = None) -> None:
        """Load the selected saved search SVG into the preview pane."""
        name = self.selected_figure_artifact()
        if self.current_run_dir is None or not name:
            self.figure_stack.setCurrentWidget(self.figure_placeholder)
            self.figure_placeholder.setText("No figure artifact is available for this run.")
            self.export_figure_btn.setEnabled(False)
            return
        artifact = self.current_run_dir / name
        if not artifact.is_file():
            self.figure_stack.setCurrentWidget(self.figure_placeholder)
            self.figure_placeholder.setText(f"Figure artifact missing: {name}")
            self.export_figure_btn.setEnabled(False)
            return
        self.export_figure_btn.setEnabled(True)
        self.figure_stack.setCurrentWidget(self.figure_view)
        if hasattr(self.figure_view, "load"):
            self.figure_view.load(str(artifact))
            if hasattr(self.figure_view, "renderer"):
                if not self.figure_view.renderer().isValid():
                    self.figure_stack.setCurrentWidget(self.figure_placeholder)
                    self.figure_placeholder.setText(f"Figure artifact unreadable: {name}")
                    self.export_figure_btn.setEnabled(False)
                    return
                self.figure_view.renderer().setAspectRatioMode(
                    Qt.AspectRatioMode.KeepAspectRatio
                )
            return
        if hasattr(self.figure_view, "setHtml"):
            uri = artifact.as_uri()
            self.figure_view.setHtml(
                "<!doctype html><html><head><style>"
                "html,body{margin:0;width:100%;height:100%;overflow:hidden;background:white;}"
                "img{width:100%;height:100%;object-fit:contain;display:block;}"
                "</style></head><body>"
                f"<img src='{uri}' alt='{artifact.name}'>"
                "</body></html>",
                QUrl.fromLocalFile(str(artifact.parent)),
            )

    def load_summary(
        self,
        summary: dict[str, object],
        *,
        run_dir: Path | None = None,
        request_note: str = "",
        workflow_kind: str = "search",
        executed_request: dict[str, str] | None = None,
        source_summary: dict[str, object] | None = None,
    ) -> None:
        """search_advanced_summary.json 형태를 표로 표시.

        `request_note` names the request the numbers belong to when the user has edited the
        inputs while the run was in flight (see `superseded_note`).
        """
        validate_search_summary(summary)
        self._clear_inspector()
        self.current_run_dir = None if run_dir is None else run_dir.resolve()
        self._inspector_summary = summary
        if workflow_kind == "search" and self.current_run_dir is not None:
            self._evaluations, self._evaluations_error = _read_search_evaluations(
                self.current_run_dir
            )
        self._displayed_kind = workflow_kind
        self._displayed_request = self._request_fields(workflow_kind)
        self._executed_request = None if executed_request is None else dict(executed_request)
        self._refresh_figure_choices()
        labels = summary.get("column_labels")
        headers = (
            [str(x) for x in labels]
            if isinstance(labels, list) and len(labels) == self.table.columnCount()
            else list(SEARCH_COLUMNS)
        )
        self.table.setHorizontalHeaderLabels(headers)
        mark_computed_headers(self.table, _COMPUTED_COLUMNS)
        strategy = str(summary.get("strategy", ""))
        warnings = summary.get("warnings")
        warning_list = [str(w) for w in warnings] if isinstance(warnings, list) else []
        status_text = f"status: {summary.get('status', 'unknown')} · strategy: {strategy}"
        if warning_list:
            status_text += f" · {len(warning_list)} warning(s); see details"
        details = [f"Run: {self.current_run_dir or 'unknown'}", f"Strategy: {strategy}"]
        for key in (
            "status", "score_unit", "normalizer", "solution_semantics", "metric",
            "directions", "weights", "normalization_ranges", "ga_metadata",
            "effective_request", "effective_conditions", "growth_fraction",
            "min_member_growth", "min_community_growth", "seed", "target_scales",
            "ga_max_evaluations", "n_candidates_total",
            "n_candidates_evaluated", "n_candidates_failed", "n_candidates_ranked",
            "n_pareto_points", "n_pareto_attempts", "n_pareto_resolved_attempts",
            "n_pareto_failed_attempts", "pareto_attempts", "candidate_sampling_status",
            "cli_exit_code", "cli_error", "input_diagnostic", "output_dir",
            "medium_not_applicable", "medium_not_applicable_to_pool",
        ):
            if key in summary:
                details.append(f"{key}: {summary[key]}")
        # The candidates the run could not evaluate, and why, come before the run warnings: in
        # a failed run they are the answer to "what went wrong".
        unevaluated = summary.get("unevaluated")
        if isinstance(unevaluated, list):
            for i, candidate in enumerate(unevaluated, 1):
                if isinstance(candidate, dict):
                    details.append(
                        f"Unevaluated {i}: {candidate.get('members')} · "
                        f"{candidate.get('status')} · "
                        f"{_diagnostic_text(candidate.get('diagnostic'))}"
                    )
        not_ranked = summary.get("not_ranked")
        if isinstance(not_ranked, list):
            for i, row in enumerate(not_ranked, 1):
                if isinstance(row, dict):
                    details.append(
                        f"Not ranked {i} (the run failed): {row.get('members')} · "
                        f"{row.get('status')} · {_diagnostic_text(row.get('diagnostic'))}"
                    )
        details.extend(f"Warning {i}: {warning}" for i, warning in enumerate(warning_list, 1))
        if request_note:
            details.append(request_note)
        if executed_request:
            if workflow_kind == "search" and "medium_mode" in executed_request:
                details.append("Medium mode: " + medium_mode_text(
                    executed_request.get("medium", ""), executed_request["medium_mode"]
                ).removeprefix("medium: "))
            details.append(f"Executed request: {executed_request}")
        details.append("Recorded summary JSON:\n" + json.dumps(
            source_summary if source_summary is not None else summary,
            ensure_ascii=False, indent=2, default=str,
        ))
        self.details.setPlainText("\n".join(details))
        ranked = summary.get("top_ranked", {})
        rows: list[tuple[str, str, float | None, float | str | None, float | None, str, str]] = []
        diagnostics: list[object] = []
        records: list[tuple[str, dict[object, object]]] = []
        if isinstance(ranked, dict):
            groups = [
                (str(target), items) for target, items in ranked.items() if isinstance(items, list)
            ]
        elif isinstance(ranked, list):
            groups = [(str(summary.get("target", "")), ranked)]
        else:
            groups = []
        for target, items in groups:
            group_target = target
            for item in items:
                if not isinstance(item, dict):
                    continue
                members = item.get("members", [])
                score = _optional_float(item.get("score", item.get("weighted_score")))
                target_flux: float | str | None = _optional_float(item.get("target_flux"))
                fluxes = item.get("target_fluxes")
                if isinstance(fluxes, dict):
                    target = ", ".join(str(key) for key in fluxes)
                    target_flux = ", ".join(
                        f"{key}={float(value):.4g}" if isinstance(value, (int, float))
                        else f"{key}=—" for key, value in fluxes.items()
                    )
                growth = _optional_float(item.get("community_growth"))
                aux = item.get("aux_text")
                aux_text = _fva_range_text(item) if aux is None else str(aux)
                diagnostic = item.get("diagnostic")
                diagnostics.append(diagnostic)
                records.append((group_target, item))
                status = str(item.get("status", "ok"))
                if diagnostic:
                    # The CSV/JSON carry the diagnostic; the table used to print a bare
                    # "optimal" for a row whose flux stage had actually failed.
                    status = f"{status} ⚠ diagnostic"
                rows.append(
                    (
                        "+".join(str(x) for x in members) if isinstance(members, list) else "",
                        target,
                        score,
                        # No fallback to `score`: a missing target_flux renders as "—" like every
                        # other missing value, never as a different quantity wearing its label.
                        target_flux,
                        growth,
                        aux_text,
                        status,
                    )
                )
        n_flagged = sum(1 for d in diagnostics if d)
        if n_flagged:
            status_text += f" · {n_flagged} row(s) carry a solver diagnostic"
        self.status.setText(status_text + request_note)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            diagnostic = diagnostics[r]
            tooltip = "" if not diagnostic else _diagnostic_text(diagnostic)
            for c, value in enumerate(row):
                text = (
                    "—"
                    if value is None
                    else f"{value:.4g}"
                    if isinstance(value, float)
                    else str(value)
                )
                item_widget = read_only_item(text)
                if diagnostic:
                    item_widget.setForeground(_DIAGNOSTIC_COLOR)
                    item_widget.setToolTip(tooltip)
                if c == 0:
                    # The row's own summary record, by identity: not table order, not members.
                    item_widget.setData(Qt.ItemDataRole.UserRole, r)
                self.table.setItem(r, c, item_widget)
        paint_computed(self.table, _COMPUTED_COLUMNS, status_column=6)
        self._row_records = records
        pareto = summary.get("pareto_frontier")
        try:
            pareto_count = (len(pareto) if isinstance(pareto, list)
                            else int(str(summary.get("n_pareto_points", 0))))
        except (TypeError, ValueError):
            pareto_count = 0
        self.pareto_label.setText(
            "" if not pareto_count else f"Pareto frontier candidates: {pareto_count}"
        )
        self.refresh_figure_mode()
        if self._area is not None:
            self._area.show_results()


_NOT_RECORDED = "not recorded"
_ABSENT = object()
_FLUX_BASIS_TEXT = {
    "joint_weighted_lp": "joint — all target fluxes achieved together in one solution",
    "per_target_capability_not_simultaneous": (
        "per-target capability — each target solved separately; "
        "not simultaneously achievable"
    ),
    "unevaluated": "unevaluated — no flux solution was recorded",
}


def _format_recorded(value: object) -> str:
    """Format one recorded value; missing, null or empty never becomes 0."""
    if value is None:
        return _NOT_RECORDED
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{float(value):.6g}" if math.isfinite(float(value)) else _NOT_RECORDED
    if isinstance(value, list):
        return " + ".join(str(v) for v in value) if value else _NOT_RECORDED
    if isinstance(value, dict):
        return (", ".join(f"{k}={_format_recorded(v)}" for k, v in value.items())
                if value else _NOT_RECORDED)
    text = str(value)
    return text if text else _NOT_RECORDED


def _recorded(record: dict[object, object], key: str) -> str:
    return _format_recorded(record.get(key))


def _read_search_evaluations(run_dir: Path) -> tuple[dict[str, object] | None, str | None]:
    """Read search_evaluations.json; every failure is reported, none escapes."""
    path = run_dir / "search_evaluations.json"
    if not path.is_file():
        return None, "file missing"
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        return None, str(exc) or type(exc).__name__
    if not isinstance(payload, dict) or not isinstance(payload.get("rows", []), list):
        return None, "not a search evaluations object"
    attempts = payload.get("pareto_attempts")
    if attempts is not None and not isinstance(attempts, list):
        return None, "pareto_attempts is not a list"
    return cast(dict[str, object], payload), None


def _matching_evaluation(
    record: dict[object, object], rows: object
) -> dict[object, object] | None:
    """The single evaluation row with this record's rank, members and flux vector.

    Pareto archive rows are renumbered in report order, so their rank need not equal the
    evaluation ledger's; members plus the exact flux vector is then the identity.
    """
    if not isinstance(rows, list):
        return None
    keys = ("rank", "members", "target_fluxes", "target_flux")
    wanted = {key: record[key] for key in keys if key in record}
    if "rank" not in wanted or not any(k in wanted for k in ("target_fluxes", "target_flux")):
        return None
    for criteria in (wanted, {k: v for k, v in wanted.items() if k != "rank"}):
        matches = [
            row for row in rows
            if isinstance(row, dict) and all(row.get(k) == v for k, v in criteria.items())
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return None
    return None


def _pareto_attempt_lines(
    record: dict[object, object], evaluations: dict[str, object]
) -> list[str]:
    attempts = evaluations.get("pareto_attempts")
    if not isinstance(attempts, list):
        return [f"Pareto ε attempts: {_NOT_RECORDED}"]
    members = record.get("members")
    own = [a for a in attempts if isinstance(a, dict) and a.get("members") == members]
    if not own:
        return ["Pareto ε attempts: none recorded for these members"]

    def condition(value: object) -> str:
        return "none" if value == {} else _format_recorded(value)

    def diagnostic_text(value: object) -> str:
        return "none" if value is None or value == "" else _diagnostic_text(value)

    lines = [f"Pareto ε attempts ({len(own)}):"]
    for attempt in own:
        lines.append(
            f"  {_format_recorded(attempt.get('attempt_key'))} · "
            f"{_format_recorded(attempt.get('outcome'))} · "
            f"phase={_format_recorded(attempt.get('phase'))} · "
            f"target={_format_recorded(attempt.get('target'))} · "
            f"direction={_format_recorded(attempt.get('direction'))} · "
            f"weights: {condition(attempt.get('objective_weights'))} · "
            f"floors: {condition(attempt.get('constraint_floors'))} · "
            f"achieved: {condition(attempt.get('achieved_vector'))} · "
            f"diagnostic: {diagnostic_text(attempt.get('diagnostic'))}"
        )
    return lines


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _diagnostic_text(diagnostic: object) -> str:
    """Render a structured Diagnostic (or free text) for a table tooltip, losslessly enough
    that the researcher can see *why* the row is flagged without opening the CSV."""
    if isinstance(diagnostic, dict):
        code = diagnostic.get("code", "diagnostic")
        message = diagnostic.get("message") or diagnostic.get("detail") or ""
        return f"{code}: {message}".strip().rstrip(":")
    return str(diagnostic)


def _fva_range_text(item: dict[object, object]) -> str:
    lo = _optional_float(item.get("robustness_fva_lo"))
    hi = _optional_float(item.get("robustness_fva_hi"))
    status = item.get("robustness_status")
    if lo is not None and hi is not None:
        return f"{lo:.4g}..{hi:.4g}"
    return "" if status is None else str(status)
