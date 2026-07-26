"""GUI Editors — Medium Editor · Model Manager (Roadmap Phase 0.4 GUI, §11).

Design Ref: §11 (Medium Editor·Model Manager) / cmig-gui-editors.design. Plan SC: ME1~ME4·MM1~MM3.

테이블 기반(offscreen 클린). MediumEditor 는 core.medium_spec(MediumSpec) 소비/생산,
ModelManagerPanel 은 io.model_import(ModelSummary) 표시. 검증 실패 → 명시 에러(silent 위장 금지).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
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

from cmig.core.medium_spec import MediumSpec
from cmig.gui.builder import make_read_only, read_only_item
from cmig.io.model_import import ModelSummary


class MediumEditor(QWidget):
    """Medium Editor — exchange별 uptake_limit 표 편집 → MediumSpec 생산(검증)."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Medium Editor")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            ["Exchange", "Uptake limit (mmol gDW⁻¹ h⁻¹; positive magnitude)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add row")
        self.add_btn.clicked.connect(lambda: self.add_row())
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self._remove_selected_row)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.clicked.connect(lambda: self.table.setRowCount(0))
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        self.status = QLabel(
            "Advanced editor: build a medium, then Check Growth against a model."
        )
        model_row = QHBoxLayout()
        self.model_path_input = QLineEdit("")
        self.model_path_input.setPlaceholderText("SBML model to check growth against")
        self.browse_model_btn = QPushButton("Model")
        self.check_growth_btn = QPushButton("Check Growth")
        model_row.addWidget(QLabel("Model"))
        model_row.addWidget(self.model_path_input)
        model_row.addWidget(self.browse_model_btn)
        model_row.addWidget(self.check_growth_btn)
        self.growth_label = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.table)
        layout.addLayout(btn_row)
        layout.addLayout(model_row)
        layout.addWidget(self.growth_label)
        layout.addWidget(self.status)

    def _remove_selected_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def add_row(self, exchange: str = "", limit: float = 0.0) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(exchange))
        self.table.setItem(r, 1, QTableWidgetItem(str(limit)))

    def load_spec(self, spec: MediumSpec) -> None:
        """MediumSpec(또는 preset) → 표 채움."""
        self.table.setRowCount(0)
        for ex, lim in sorted(spec.uptake.items()):
            self.add_row(ex, lim)

    def to_spec(self) -> MediumSpec:
        """표 → MediumSpec(검증). 빈 행 무시, 잘못된 값 → ValueError(status 표시)."""
        uptake: dict[str, float] = {}
        for r in range(self.table.rowCount()):
            ex_item = self.table.item(r, 0)
            lim_item = self.table.item(r, 1)
            ex = ex_item.text().strip() if ex_item else ""
            if not ex:
                continue
            try:
                uptake[ex] = float(lim_item.text()) if lim_item else 0.0
            except ValueError as e:
                self.status.setText(f"Invalid uptake_limit (row {r + 1})")
                raise ValueError(f"uptake_limit is not numeric (row {r + 1})") from e
        spec = MediumSpec(uptake=uptake)
        try:
            spec.validate()
        except ValueError as e:
            # Without this the slot returned silently (`except ValueError: return ""`) and
            # nothing in the UI changed — a negative uptake made Check Growth a total no-op.
            self.status.setText(
                f"{e} — enter a POSITIVE uptake magnitude in mmol gDW⁻¹ h⁻¹ "
                f"(e.g. 10, not -10); CMIG applies the uptake sign internally."
            )
            raise
        self.status.setText(f"{len(uptake)} valid exchanges")
        return spec


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
