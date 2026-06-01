"""Host Impact Dashboard — 미생물→host 영향 GUI (Roadmap Phase 3.2, §12).

Design Ref: §12 (host impact dashboard) / cmig-host-view.design. Plan SC: SC-HV1~HV4.

테이블 기반(offscreen 클린). HostSolveResult(viability·2-interface flux) + HostImpact(microbe→host
cross-feeding)를 표시. 실 backend 산출 소비(orphan 아님). 비viable 명시(silent 위장 금지).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_IFACE_COLOR = {"lumen": "#2c7fb8", "blood": "#d95f0e"}
_LABEL_COLOR = {"secretion": "#31a354", "uptake": "#756bb1"}


class HostImpactView(QWidget):
    """Host Impact Dashboard — viability·2-interface flux·microbe→host cross-feeding."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Host Impact")
        self.viability_label = QLabel("")
        # 2-interface flux 표
        self.iface_table = QTableWidget(0, 4)
        self.iface_table.setHorizontalHeaderLabels(["Interface", "Metabolite", "Flux", "Direction"])
        self.iface_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # microbe→host cross-feeding 표
        self.cross_label = QLabel("Microbe → Host cross-feeding")
        self.cross_table = QTableWidget(0, 2)
        self.cross_table.setHorizontalHeaderLabels(["Metabolite", "Flux (lumen 횡단)"])
        self.cross_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for w in (self.title, self.viability_label, self.iface_table,
                  self.cross_label, self.cross_table):
            layout.addWidget(w)

    def load_host_result(self, host_result: Any) -> None:
        """HostSolveResult → viability + 2-interface flux 표(interface/sign 색)."""
        if host_result.viable:
            self.viability_label.setText(
                f"✅ viable · host biomass = {host_result.biomass:.4g}")
            self.viability_label.setStyleSheet("color: #31a354;")
        else:
            self.viability_label.setText(
                f"❌ non-viable (status={host_result.status}) — 미생물 의존 충족 실패")
            self.viability_label.setStyleSheet("color: #d62728;")
        rows = host_result.interface_fluxes
        self.iface_table.setRowCount(len(rows))
        for i, f in enumerate(rows):
            cells = [f.interface, f.metabolite, f"{f.flux:.4g}", f.label or "—"]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0 and f.interface in _IFACE_COLOR:
                    item.setForeground(QColor(_IFACE_COLOR[f.interface]))
                if c == 3 and f.label in _LABEL_COLOR:
                    item.setForeground(QColor(_LABEL_COLOR[f.label]))
                self.iface_table.setItem(i, c, item)

    def load_impact(self, impact: Any) -> None:
        """HostImpact → microbe→host cross-feeding 표."""
        items = sorted(impact.microbe_to_host.items())
        self.cross_table.setRowCount(len(items))
        for i, (met, flux) in enumerate(items):
            self.cross_table.setItem(i, 0, QTableWidgetItem(met))
            self.cross_table.setItem(i, 1, QTableWidgetItem(f"{flux:.4g}"))
