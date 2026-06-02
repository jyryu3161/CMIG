"""PySide6 Interaction Graph 위젯 (Cytoscape.js in QWebEngineView).

Design Ref: §11 / FR-1b.1·1b.2·1b.3 / Option C (gui=presentation, 데이터=tidy).
실행에는 PySide6 + QtWebEngine 필요(`uv sync --extra gui`).
데이터 계약은 graph_data(순수·테스트 완비)에 있으며, 본 위젯은 그 payload 를 주입한다.

검증(hardening track-A, SC-H1): QT_QPA_PLATFORM=offscreen 에서 위젯 생성·graph.html 로드·
Cytoscape payload 주입(DOM count)·gate DOM 반영·grab 산출을 tests/test_gui_render.py 가
실행 검증한다(G-7 해소). cytoscape.js 는 로컬 번들(assets/cytoscape.min.js) — offline.
정직성 경계: offscreen=실행+산출 증거이며 human 시각 디자인 QA(G-7b)는 별도/미수행.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.core.namespace import NamespaceGateResult
from cmig.core.tidy import TidyBundle
from cmig.gui.graph_data import filter_elements, gate_ui_data, graph_payload

_ASSET = Path(__file__).parent / "assets" / "graph.html"


class InteractionGraphView(QWidget):
    """tidy bundle 을 Cytoscape.js 그래프로 렌더하는 위젯 (§11)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pending: dict | None = None
        self._base_payload: dict | None = None
        self._ready = False
        self._web = QWebEngineView(self)
        self.cross_feeding_check = QCheckBox("Cross-feeding")
        self.secretion_check = QCheckBox("+ secretion")
        self.uptake_check = QCheckBox("− uptake")
        for check in (self.cross_feeding_check, self.secretion_check, self.uptake_check):
            check.toggled.connect(self._apply_filters)
        self.edge_table = QTableWidget(0, 5)
        self.edge_table.setHorizontalHeaderLabels(
            ["Source", "Target", "Metabolite", "Type", "Flux"]
        )
        self.edge_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.edge_table.setMaximumHeight(190)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        controls.setContentsMargins(8, 4, 8, 4)
        controls.addWidget(QLabel("Edges"))
        controls.addWidget(self.cross_feeding_check)
        controls.addWidget(self.secretion_check)
        controls.addWidget(self.uptake_check)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self._web)
        layout.addWidget(self.edge_table)
        self._web.loadFinished.connect(self._on_load)
        self._web.load(self._asset_url())

    @staticmethod
    def _asset_url() -> str:
        from PySide6.QtCore import QUrl

        return QUrl.fromLocalFile(str(_ASSET)).toString()

    def _on_load(self, ok: bool) -> None:
        self._ready = ok
        if ok and self._pending is not None:
            self._inject(self._pending)
            self._pending = None

    def _inject(self, payload: dict) -> None:
        self._web.page().runJavaScript(f"window.setGraph({json.dumps(payload)});")

    def _filtered_payload(self) -> dict | None:
        if self._base_payload is None:
            return None
        edge_types: set[str] = set()
        if self.cross_feeding_check.isChecked():
            edge_types.add("cross_feeding")
        if self.secretion_check.isChecked():
            edge_types.add("secretion")
        if self.uptake_check.isChecked():
            edge_types.add("uptake")
        elements = filter_elements(
            list(self._base_payload["elements"]),
            edge_types=edge_types,
        )
        edges = [e for e in elements if "source" in e["data"]]
        if edges:
            connected = {
                node_id
                for edge in edges
                for node_id in (edge["data"]["source"], edge["data"]["target"])
            }
            elements = [
                e for e in elements
                if "source" in e["data"] or e["data"]["id"] in connected
            ]
        payload = dict(self._base_payload)
        payload["elements"] = elements
        return payload

    def _refresh_edge_table(self, elements: list[dict]) -> None:
        edges = [e["data"] for e in elements if "source" in e["data"]]
        edges.sort(
            key=lambda e: (
                e.get("etype") != "cross_feeding",
                -float(e.get("weight") or 0.0),
            )
        )
        rows = edges[:20]
        self.edge_table.setRowCount(len(rows))
        colors = {
            "cross_feeding": "#d95f0e",
            "secretion": "#31a354",
            "uptake": "#756bb1",
        }
        for row, edge in enumerate(rows):
            values = [
                str(edge.get("source", "")),
                str(edge.get("target", "")),
                str(edge.get("metabolite", "")),
                str(edge.get("etype", "")),
                f"{float(edge.get('weight') or 0.0):.4g}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 3 and edge.get("etype") in colors:
                    item.setForeground(QColor(colors[str(edge.get("etype"))]))
                self.edge_table.setItem(row, col, item)

    def _apply_filters(self) -> None:
        payload = self._filtered_payload()
        if payload is None:
            return
        self._refresh_edge_table(list(payload["elements"]))
        if self._ready:
            self._inject(payload)
        else:
            self._pending = payload

    def set_edge_filters(
        self, *, cross_feeding: bool, secretion: bool, uptake: bool
    ) -> None:
        """Set visible edge families. Used by UI controls and deterministic tests."""
        for check, value in (
            (self.cross_feeding_check, cross_feeding),
            (self.secretion_check, secretion),
            (self.uptake_check, uptake),
        ):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)
        self._apply_filters()

    def set_bundle(
        self, bundle: TidyBundle, gate: NamespaceGateResult | None = None
    ) -> None:
        """그래프 데이터 주입. 페이지 로드 전이면 큐잉 후 loadFinished 시 주입."""
        payload = graph_payload(bundle, gate)
        self._base_payload = payload
        has_cross_feeding = any(
            "source" in element["data"] and element["data"]["etype"] == "cross_feeding"
            for element in payload["elements"]
        )
        self.set_edge_filters(
            cross_feeding=has_cross_feeding,
            secretion=not has_cross_feeding,
            uptake=not has_cross_feeding,
        )

    def highlight(self, node_id: str) -> None:
        """linked selection — 노드 인접 강조 (FR-1b.2)."""
        self._web.page().runJavaScript(f"window.highlightNeighborhood({json.dumps(node_id)});")


class GateBadge(QLabel):
    """namespace gate 상태 배지 (FR-1b.3) — coverage%·차단 상태."""

    def set_gate(self, gate: NamespaceGateResult) -> None:
        data = gate_ui_data(gate)
        self.setText(data["status_text"])
        color = "#a50f15" if data["blocked"] else "#137"
        self.setStyleSheet(f"color: {color}; padding: 4px 8px;")
