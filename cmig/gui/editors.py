"""GUI Editors — Medium Editor · Model Manager (Roadmap Phase 0.4 GUI, §11).

Design Ref: §11 (Medium Editor·Model Manager) / cmig-gui-editors.design. Plan SC: ME1~ME4·MM1~MM3.

테이블 기반(offscreen 클린). MediumEditor 는 core.medium_spec(MediumSpec) 소비/생산,
ModelManagerPanel 은 io.model_import(ModelSummary) 표시. 검증 실패 → 명시 에러(silent 위장 금지).
"""

from __future__ import annotations

import csv
import io
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.core.medium_spec import MediumSpec, load_medium
from cmig.gui.builder import make_read_only, read_only_item
from cmig.io.model_import import ModelSummary

_NUTRIENT_ROLE = "nutrient"
_POOL_CLOSURE_ROLE = "pool_closure"
_ROW_ROLES = frozenset({_NUTRIENT_ROLE, _POOL_CLOSURE_ROLE})


def _editor_text(strings: Mapping[str, str], key: str, fallback: str) -> str:
    """Return one translated editor string with an English standalone fallback."""
    return strings.get(key, fallback)


class MediumEditor(QWidget):
    """Editable medium plus thin GUI wiring inputs for CLI-backed analyses.

    Columns zero and one retain the original ``exchange_id``/``uptake_limit`` contract.
    ``row_role`` is an additive, conditionally visible presentation column; core loading and
    every analysis request still pass through :func:`load_medium` or the CLI.
    """

    medium_changed = Signal()

    def __init__(
        self,
        strings: Mapping[str, str] | None = None,
        *,
        preset_dir: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.strings = strings or {}
        self.preset_dir = (
            Path(preset_dir)
            if preset_dir is not None
            else Path(__file__).resolve().parents[2] / "medium_presets"
        )
        self.current_preset: Path | None = None
        self._has_row_roles = False
        layout = QVBoxLayout(self)
        self.title = QLabel(_editor_text(self.strings, "medium_title", "Medium Editor"))

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(_editor_text(self.strings, "medium_preset", "Preset")))
        self.preset_combo = QComboBox()
        self.load_preset_btn = QPushButton(
            _editor_text(self.strings, "medium_load_preset", "Load preset")
        )
        self.nutrients_only_check = QCheckBox(
            _editor_text(self.strings, "medium_nutrients_only", "Nutrients only")
        )
        self.load_preset_btn.clicked.connect(self.load_selected_preset)
        self.nutrients_only_check.toggled.connect(self._apply_role_view)
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.load_preset_btn)
        preset_row.addWidget(self.nutrients_only_check)
        self.pool_closure_warning = QLabel(
            _editor_text(
                self.strings,
                "medium_pool_closure_warning",
                "Pool-closure rows are bookkeeping for the bundled model pool. Removing them "
                "is safe only with exact-medium semantics (including use with another pool); "
                "never use a nutrients-only file in merge mode.",
            )
        )
        self.pool_closure_warning.setWordWrap(True)
        self.pool_closure_warning.setVisible(False)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [
                _editor_text(self.strings, "medium_col_exchange", "Exchange"),
                _editor_text(
                    self.strings,
                    "medium_col_uptake",
                    "Uptake limit (mmol gDW⁻¹ h⁻¹; positive magnitude)",
                ),
                _editor_text(self.strings, "medium_col_row_role", "Row role"),
            ]
        )
        self.table.setColumnHidden(2, True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(lambda _item: self.medium_changed.emit())
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton(_editor_text(self.strings, "medium_add_row", "Add row"))
        self.add_btn.clicked.connect(lambda: self.add_row())
        self.remove_btn = QPushButton(
            _editor_text(self.strings, "medium_remove_selected", "Remove selected")
        )
        self.remove_btn.clicked.connect(self._remove_selected_row)
        self.clear_btn = QPushButton(
            _editor_text(self.strings, "medium_clear_all", "Clear all")
        )
        self.clear_btn.clicked.connect(self.clear_rows)
        self.paste_btn = QPushButton(
            _editor_text(self.strings, "medium_paste_csv", "Paste CSV")
        )
        self.paste_btn.clicked.connect(lambda: self.paste_csv())
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.paste_btn)
        btn_row.addStretch(1)
        self.status = QLabel(
            _editor_text(
                self.strings,
                "medium_status_ready",
                "Advanced editor: load, paste, or edit a medium, then run a CLI-backed check.",
            )
        )
        self.status.setWordWrap(True)

        taxonomy_row = QHBoxLayout()
        self.taxonomy_input = QLineEdit("")
        self.taxonomy_input.setPlaceholderText(
            _editor_text(self.strings, "medium_taxonomy_placeholder", "Community taxonomy CSV")
        )
        self.browse_taxonomy_btn = QPushButton(
            _editor_text(self.strings, "medium_browse_taxonomy", "Taxonomy…")
        )
        taxonomy_row.addWidget(
            QLabel(_editor_text(self.strings, "medium_taxonomy_label", "Taxonomy"))
        )
        taxonomy_row.addWidget(self.taxonomy_input, 1)
        taxonomy_row.addWidget(self.browse_taxonomy_btn)

        namespace_row = QHBoxLayout()
        self.assume_bigg_check = QCheckBox(
            _editor_text(
                self.strings,
                "medium_assume_bigg",
                "I reviewed the models and confirm BiGG namespace",
            )
        )
        self.namespace_decisions_input = QLineEdit("")
        self.namespace_decisions_input.setPlaceholderText(
            _editor_text(
                self.strings,
                "medium_namespace_placeholder",
                "Or a reviewed namespace-decisions JSON file",
            )
        )
        self.browse_namespace_btn = QPushButton(
            _editor_text(self.strings, "medium_namespace_button", "Decisions…")
        )
        namespace_row.addWidget(self.assume_bigg_check)
        namespace_row.addWidget(self.namespace_decisions_input, 1)
        namespace_row.addWidget(self.browse_namespace_btn)

        solve_options_row = QHBoxLayout()
        self.exact_medium_check = QCheckBox(
            _editor_text(
                self.strings,
                "medium_exact_mode",
                "Exact medium (unchecked = merge overlay)",
            )
        )
        self.allow_unknown_check = QCheckBox(
            _editor_text(
                self.strings,
                "medium_allow_unknown",
                "Allow unknown IDs and report every dropped ID",
            )
        )
        self.check_growth_btn = QPushButton(
            _editor_text(self.strings, "medium_check_growth", "Check Growth")
        )
        self.exact_medium_check.toggled.connect(lambda _checked: self.medium_changed.emit())
        solve_options_row.addWidget(self.exact_medium_check)
        solve_options_row.addWidget(self.allow_unknown_check)
        solve_options_row.addStretch(1)
        solve_options_row.addWidget(self.check_growth_btn)
        self.growth_label = QLabel("")
        self.growth_label.setWordWrap(True)
        self.dropped_ids_label = QLabel("")
        self.dropped_ids_label.setWordWrap(True)
        self.profile_delta_label = QLabel("")
        self.profile_delta_label.setWordWrap(True)

        model_row = QHBoxLayout()
        self.model_path_input = QLineEdit("")
        self.model_path_input.setPlaceholderText(
            _editor_text(
                self.strings,
                "medium_model_placeholder",
                "Single SBML/JSON/MAT model for minimal-medium",
            )
        )
        self.browse_model_btn = QPushButton(
            _editor_text(self.strings, "medium_browse_model", "Model…")
        )
        self.min_growth_spin = QDoubleSpinBox()
        self.min_growth_spin.setDecimals(6)
        self.min_growth_spin.setRange(0.000001, 1_000_000.0)
        self.min_growth_spin.setValue(0.1)
        self.oxygen_mode_combo = QComboBox()
        self.oxygen_mode_combo.addItem(
            _editor_text(self.strings, "medium_oxygen_aerobic", "Aerobic"), "aerobic"
        )
        self.oxygen_mode_combo.addItem(
            _editor_text(self.strings, "medium_oxygen_anaerobic", "Anaerobic"), "anaerobic"
        )
        self.minimal_medium_btn = QPushButton(
            _editor_text(self.strings, "medium_run_minimal", "Find Minimal Medium")
        )
        model_row.addWidget(QLabel(_editor_text(self.strings, "medium_model_label", "Model")))
        model_row.addWidget(self.model_path_input, 1)
        model_row.addWidget(self.browse_model_btn)
        model_row.addWidget(
            QLabel(_editor_text(self.strings, "medium_min_growth", "Minimum growth"))
        )
        model_row.addWidget(self.min_growth_spin)
        model_row.addWidget(self.oxygen_mode_combo)
        model_row.addWidget(self.minimal_medium_btn)
        self.minimal_table = QTableWidget(0, 3)
        self.minimal_table.setHorizontalHeaderLabels(
            [
                _editor_text(self.strings, "medium_col_exchange", "Exchange"),
                _editor_text(self.strings, "medium_minimal_uptake", "Candidate uptake"),
                _editor_text(self.strings, "medium_limiting", "Limiting (leave-one-out)"),
            ]
        )
        self.minimal_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.minimal_table)
        self.minimal_status = QLabel("")
        self.minimal_status.setWordWrap(True)

        layout.addWidget(self.title)
        layout.addLayout(preset_row)
        layout.addWidget(self.pool_closure_warning)
        layout.addWidget(self.table)
        layout.addLayout(btn_row)
        layout.addLayout(taxonomy_row)
        layout.addLayout(namespace_row)
        layout.addLayout(solve_options_row)
        layout.addWidget(self.growth_label)
        layout.addWidget(self.dropped_ids_label)
        layout.addWidget(self.profile_delta_label)
        layout.addLayout(model_row)
        layout.addWidget(self.minimal_table)
        layout.addWidget(self.minimal_status)
        layout.addWidget(self.status)
        self.refresh_presets()

    def _remove_selected_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._update_role_presentation()
            self.medium_changed.emit()

    def clear_rows(self) -> None:
        self.table.setRowCount(0)
        self.current_preset = None
        self._has_row_roles = False
        self.table.setColumnHidden(2, True)
        self.pool_closure_warning.setVisible(False)
        self.nutrients_only_check.setChecked(False)
        self.medium_changed.emit()

    def add_row(
        self,
        exchange: str = "",
        limit: float = 0.0,
        row_role: str = "",
        *,
        notify: bool = True,
    ) -> None:
        r = self.table.rowCount()
        blocked = self.table.blockSignals(True)
        self.table.insertRow(r)
        exchange_item = QTableWidgetItem(exchange)
        limit_item = QTableWidgetItem(str(limit))
        role_item = read_only_item(row_role)
        self.table.setItem(r, 0, exchange_item)
        self.table.setItem(r, 1, limit_item)
        self.table.setItem(r, 2, role_item)
        self.table.blockSignals(blocked)
        self._style_role_row(r, row_role)
        if notify:
            if row_role:
                self._update_role_presentation()
            self.medium_changed.emit()

    def load_spec(self, spec: MediumSpec) -> None:
        """MediumSpec(또는 preset) → 표 채움."""
        spec.validate()
        blocked = self.table.blockSignals(True)
        self.table.setRowCount(0)
        for ex, lim in sorted(spec.uptake.items()):
            self.add_row(ex, lim, notify=False)
        self.table.blockSignals(blocked)
        self.current_preset = None
        self._has_row_roles = False
        self.table.setColumnHidden(2, True)
        self.pool_closure_warning.setVisible(False)
        self.nutrients_only_check.setChecked(False)
        self.medium_changed.emit()

    def refresh_presets(self) -> None:
        """Enumerate shipped medium CSVs without mistaking provenance metadata for a preset."""
        current = self.preset_combo.currentData()
        blocked = self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem(
            _editor_text(self.strings, "medium_choose_preset", "Choose a preset…"), None
        )
        if self.preset_dir.is_dir():
            for path in sorted(self.preset_dir.glob("*.csv")):
                if path.name == "provenance_rows.csv":
                    continue
                self.preset_combo.addItem(path.name, str(path.resolve()))
        if current is not None:
            index = self.preset_combo.findData(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(blocked)

    def load_selected_preset(self) -> bool:
        selected = self.preset_combo.currentData()
        if not selected:
            self.status.setText(
                _editor_text(
                    self.strings,
                    "medium_select_preset",
                    "Choose a preset before loading it.",
                )
            )
            return False
        try:
            self.load_preset(Path(str(selected)))
        except (OSError, ValueError) as error:
            self.status.setText(
                _editor_text(
                    self.strings,
                    "medium_preset_failed",
                    "Preset failed validation: {error}",
                ).format(error=error)
            )
            return False
        return True

    def load_preset(self, path: str | Path) -> MediumSpec:
        """Load a preset through the real core loader, then add its display-only row roles."""
        preset_path = Path(path)
        spec = load_medium(preset_path)
        with preset_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [
                (
                    str(row.get("exchange_id") or "").strip(),
                    str(row.get("row_role") or "").strip(),
                )
                for row in reader
                if str(row.get("exchange_id") or "").strip()
            ]
        blocked = self.table.blockSignals(True)
        self.table.setRowCount(0)
        for exchange, role in rows:
            self.add_row(
                exchange,
                spec.uptake[exchange],
                role,
                notify=False,
            )
        self.table.blockSignals(blocked)
        self.current_preset = preset_path.resolve()
        self._update_role_presentation()
        self.status.setText(
            _editor_text(
                self.strings,
                "medium_preset_loaded",
                "Loaded {name}: {count} validated rows.",
            ).format(name=preset_path.name, count=len(spec.uptake))
        )
        self.medium_changed.emit()
        return spec

    def paste_csv(self, text: str | None = None) -> bool:
        """Validate pasted CSV via ``load_medium`` and replace the table atomically.

        A header is optional, but each nonblank data row must have exactly two or three cells.
        Row numbers and exchange ids are kept in every validation error; no malformed row is
        omitted merely because the core CSV loader treats a blank exchange as an empty line.
        """
        source = QApplication.clipboard().text() if text is None else text
        if not source.strip():
            self.status.setText(
                _editor_text(self.strings, "medium_paste_empty", "Clipboard CSV is empty.")
            )
            return False
        try:
            parsed = [
                (line_no, row)
                for line_no, row in enumerate(csv.reader(io.StringIO(source)), start=1)
                if any(cell.strip() for cell in row)
            ]
        except csv.Error as error:
            self.status.setText(
                _editor_text(
                    self.strings,
                    "medium_paste_parse_failed",
                    "CSV paste could not be parsed: {error}",
                ).format(error=error)
            )
            return False
        if not parsed:
            self.status.setText(
                _editor_text(self.strings, "medium_paste_empty", "Clipboard CSV is empty.")
            )
            return False

        first_line, first_row = parsed[0]
        has_header = bool(first_row) and first_row[0].strip() == "exchange_id"
        data_rows = parsed[1:] if has_header else parsed
        if has_header:
            header = [cell.strip() for cell in first_row]
            if header not in (
                ["exchange_id", "uptake_limit"],
                ["exchange_id", "uptake_limit", "row_role"],
            ):
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_bad_header",
                        "CSV paste row {row}: header must be "
                        "exchange_id,uptake_limit[,row_role].",
                    ).format(row=first_line)
                )
                return False
            column_count = len(header)
        else:
            column_count = len(first_row)
            if column_count not in (2, 3):
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_bad_column_count",
                        "CSV paste row {row}: expected 2 or 3 columns, got {count}.",
                    ).format(row=first_line, count=column_count)
                )
                return False
            header = ["exchange_id", "uptake_limit"]
            if column_count == 3:
                header.append("row_role")

        normalized: list[tuple[int, str, str, str]] = []
        first_seen: dict[str, int] = {}
        for line_no, raw_row in data_rows:
            if len(raw_row) != column_count:
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_bad_columns",
                        "CSV paste row {row}: expected {expected} columns, got {count}.",
                    ).format(row=line_no, expected=column_count, count=len(raw_row))
                )
                return False
            exchange = raw_row[0].strip()
            if not exchange:
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_blank_exchange",
                        "CSV paste row {row}: exchange_id is blank.",
                    ).format(row=line_no)
                )
                return False
            if exchange in first_seen:
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_duplicate",
                        "CSV paste row {row} ({exchange}) duplicates row {first}.",
                    ).format(row=line_no, exchange=exchange, first=first_seen[exchange])
                )
                return False
            first_seen[exchange] = line_no
            role = raw_row[2].strip() if column_count == 3 else ""
            if column_count == 3 and role not in _ROW_ROLES:
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_bad_role",
                        "CSV paste row {row} ({exchange}): row_role must be nutrient or "
                        "pool_closure.",
                    ).format(row=line_no, exchange=exchange)
                )
                return False
            normalized.append((line_no, exchange, raw_row[1].strip(), role))

        with tempfile.TemporaryDirectory(prefix="cmig-medium-paste-") as temp_dir:
            validation_path = Path(temp_dir) / "pasted_medium.csv"
            with validation_path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                for _line_no, exchange, limit, role in normalized:
                    row = [exchange, limit]
                    if column_count == 3:
                        row.append(role)
                    writer.writerow(row)
            try:
                spec = load_medium(validation_path)
            except (OSError, ValueError) as error:
                named_rows = ", ".join(
                    f"{line_no} ({exchange})" for line_no, exchange, _limit, _role in normalized
                )
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_paste_validation_failed",
                        "CSV paste validation failed; data rows {rows}: {error}",
                    ).format(rows=named_rows, error=error)
                )
                return False

        blocked = self.table.blockSignals(True)
        self.table.setRowCount(0)
        for _line_no, exchange, _limit, role in normalized:
            self.add_row(exchange, spec.uptake[exchange], role, notify=False)
        self.table.blockSignals(blocked)
        self.current_preset = None
        self._update_role_presentation()
        self.status.setText(
            _editor_text(
                self.strings,
                "medium_paste_loaded",
                "Pasted {count} validated CSV rows.",
            ).format(count=len(normalized))
        )
        self.medium_changed.emit()
        return True

    def _style_role_row(self, row: int, role: str) -> None:
        if role != _POOL_CLOSURE_ROLE:
            return
        warning = self.pool_closure_warning.text()
        background = QBrush(QColor("#fff1bf"))
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item is not None:
                item.setBackground(background)
                item.setToolTip(warning)

    def _update_role_presentation(self) -> None:
        roles: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item is not None:
                roles.append(item.text().strip())
        self._has_row_roles = any(role in _ROW_ROLES for role in roles)
        has_closure = _POOL_CLOSURE_ROLE in roles
        self.table.setColumnHidden(2, not self._has_row_roles)
        self.pool_closure_warning.setVisible(has_closure)
        self.nutrients_only_check.setEnabled(has_closure)
        if not has_closure and self.nutrients_only_check.isChecked():
            self.nutrients_only_check.setChecked(False)
        self._apply_role_view(self.nutrients_only_check.isChecked(), notify=False)

    def _apply_role_view(self, checked: bool, *, notify: bool = True) -> None:
        for row in range(self.table.rowCount()):
            role_item = self.table.item(row, 2)
            role = role_item.text().strip() if role_item is not None else ""
            self.table.setRowHidden(row, checked and role == _POOL_CLOSURE_ROLE)
        if checked and not self.exact_medium_check.isChecked():
            self.status.setText(
                _editor_text(
                    self.strings,
                    "medium_nutrients_merge_unsafe",
                    "Nutrients-only filtering cannot run in merge mode; choose Exact medium. "
                    "Merge would reopen undeclared model defaults.",
                )
            )
        if notify:
            self.medium_changed.emit()

    def namespace_policy(self) -> tuple[list[str], str]:
        decisions = self.namespace_decisions_input.text().strip()
        assumed = self.assume_bigg_check.isChecked()
        if assumed and decisions:
            return [], _editor_text(
                self.strings,
                "medium_namespace_choice",
                "Choose only one namespace policy: reviewed decisions or BiGG confirmation.",
            )
        if assumed:
            return ["--assume-bigg-namespace"], ""
        if decisions:
            return ["--namespace-decisions", decisions], ""
        return [], _editor_text(
            self.strings,
            "medium_namespace_required",
            "Namespace review is required: choose reviewed decisions or confirm BiGG namespace.",
        )

    def medium_mode_error(self) -> str:
        if self.nutrients_only_check.isChecked() and not self.exact_medium_check.isChecked():
            return _editor_text(
                self.strings,
                "medium_nutrients_merge_unsafe",
                "Nutrients-only filtering cannot run in merge mode; choose Exact medium. "
                "Merge would reopen undeclared model defaults.",
            )
        return ""

    def to_spec(self) -> MediumSpec:
        """표 → MediumSpec(검증). 빈 행 무시, 잘못된 값 → ValueError(status 표시)."""
        uptake: dict[str, float] = {}
        first_rows: dict[str, int] = {}
        for r in range(self.table.rowCount()):
            if self.table.isRowHidden(r):
                continue
            ex_item = self.table.item(r, 0)
            lim_item = self.table.item(r, 1)
            ex = ex_item.text().strip() if ex_item else ""
            if not ex:
                continue
            if ex in uptake:
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_table_duplicate",
                        "Duplicate exchange_id {exchange}: rows {first} and {row}.",
                    ).format(exchange=ex, first=first_rows[ex], row=r + 1)
                )
                raise ValueError(f"duplicate exchange_id {ex}: rows {first_rows[ex]} and {r + 1}")
            try:
                uptake[ex] = float(lim_item.text()) if lim_item else 0.0
            except ValueError as e:
                self.status.setText(
                    _editor_text(
                        self.strings,
                        "medium_invalid_uptake",
                        "Invalid uptake_limit (row {row}: {exchange})",
                    ).format(row=r + 1, exchange=ex)
                )
                raise ValueError(f"uptake_limit is not numeric (row {r + 1})") from e
            first_rows[ex] = r + 1
        spec = MediumSpec(uptake=uptake)
        try:
            spec.validate()
        except ValueError as e:
            # Without this the slot returned silently (`except ValueError: return ""`) and
            # nothing in the UI changed — a negative uptake made Check Growth a total no-op.
            self.status.setText(
                _editor_text(
                    self.strings,
                    "medium_validation_failed",
                    "{error} — enter a POSITIVE uptake magnitude in mmol gDW⁻¹ h⁻¹ "
                    "(e.g. 10, not -10); CMIG applies the uptake sign internally.",
                ).format(error=e)
            )
            raise
        self.status.setText(
            _editor_text(
                self.strings,
                "medium_valid_exchanges",
                "{count} valid exchanges",
            ).format(count=len(uptake))
        )
        return spec

    def load_minimal_result(self, payload: Mapping[str, Any]) -> None:
        """Display CLI-emitted components and leave-one-out limiting labels verbatim."""
        components = [str(item) for item in payload.get("components", [])]
        uptake = payload.get("uptake_bounds", {})
        uptake_map = uptake if isinstance(uptake, Mapping) else {}
        limiting = {str(item) for item in payload.get("limiting_nutrients", [])}
        self.minimal_table.setRowCount(len(components))
        for row, exchange in enumerate(components):
            value = uptake_map.get(exchange)
            cells = [
                exchange,
                "—" if value is None else f"{float(value):.6g}",
                _editor_text(self.strings, "medium_yes", "Yes")
                if exchange in limiting
                else _editor_text(self.strings, "medium_no", "No"),
            ]
            for column, cell in enumerate(cells):
                self.minimal_table.setItem(row, column, read_only_item(cell))
        warnings = [str(item) for item in payload.get("warnings", [])]
        warning_note = "" if not warnings else " · " + "; ".join(warnings)
        self.minimal_status.setText(
            _editor_text(
                self.strings,
                "medium_minimal_result",
                "Minimal-medium status: {status}; {count} components; achieved growth: "
                "{growth}; {limiting} limiting nutrients{warnings}",
            ).format(
                status=payload.get("status", "unknown"),
                count=len(components),
                growth=(
                    "—"
                    if payload.get("achieved_growth") is None
                    else f"{float(payload['achieved_growth']):.6g}"
                ),
                limiting=len(limiting),
                warnings=warning_note,
            )
        )


class ModelManagerPanel(QWidget):
    """Model Manager — import 된 GEM 요약 표시(reaction/metabolite/gene·exchange·biomass)."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary_label = QLabel("Import a model.")
        self.exchange_table = QTableWidget(0, 1)
        self.exchange_table.setHorizontalHeaderLabels(["Exchange reactions"])
        self.exchange_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.exchange_table)
        self.biomass_label = QLabel("")
        layout.addWidget(self.summary_label)
        layout.addWidget(self.exchange_table)
        layout.addWidget(self.biomass_label)

    def load_summary(self, summary: ModelSummary) -> None:
        """ModelSummary → 카운트 요약 + exchange 목록 + biomass."""
        self.summary_label.setText(
            f"{summary.model_id} [{summary.source_format}] — "
            f"{summary.n_reactions} reactions · {summary.n_metabolites} metabolites · "
            f"{summary.n_genes} genes"
        )
        self.exchange_table.setRowCount(len(summary.exchanges))
        for i, ex in enumerate(summary.exchanges):
            self.exchange_table.setItem(i, 0, read_only_item(ex))
        bio = ", ".join(summary.biomass_reactions) or "(not detected)"
        self.biomass_label.setText(f"Biomass: {bio}")

    def as_summary_dict(self, summary: ModelSummary) -> dict[str, Any]:
        return summary.as_dict()
