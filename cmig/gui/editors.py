"""GUI Editors — Medium Editor · Model Manager (Roadmap Phase 0.4 GUI, §11).

Design Ref: §11 (Medium Editor·Model Manager) / cmig-gui-editors.design. Plan SC: ME1~ME4·MM1~MM3.

테이블 기반(offscreen 클린). MediumEditor 는 core.medium_spec(MediumSpec) 소비/생산,
ModelManagerPanel 은 io.model_import(ModelSummary) 표시. 검증 실패 → 명시 에러(silent 위장 금지).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.core.medium_spec import MediumSpec
from cmig.io.model_import import ModelSummary


class MediumEditor(QWidget):
    """Medium Editor — exchange별 uptake_limit 표 편집 → MediumSpec 생산(검증)."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Medium Editor")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Exchange", "Uptake limit"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.add_btn = QPushButton("Add row")
        self.add_btn.clicked.connect(lambda: self.add_row())
        self.status = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.table)
        layout.addWidget(self.add_btn)
        layout.addWidget(self.status)

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
                self.status.setText(f"잘못된 uptake_limit (행 {r + 1})")
                raise ValueError(f"uptake_limit 숫자 아님 (행 {r + 1})") from e
        spec = MediumSpec(uptake=uptake)
        spec.validate()
        self.status.setText(f"{len(uptake)} exchange 유효")
        return spec


class ModelManagerPanel(QWidget):
    """Model Manager — import 된 GEM 요약 표시(reaction/metabolite/gene·exchange·biomass)."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary_label = QLabel("모델을 import 하세요.")
        self.exchange_table = QTableWidget(0, 1)
        self.exchange_table.setHorizontalHeaderLabels(["Exchange reactions"])
        self.exchange_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
            self.exchange_table.setItem(i, 0, QTableWidgetItem(ex))
        bio = ", ".join(summary.biomass_reactions) or "(미탐지)"
        self.biomass_label.setText(f"Biomass: {bio}")

    def as_summary_dict(self, summary: ModelSummary) -> dict[str, Any]:
        return summary.as_dict()
