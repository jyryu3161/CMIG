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

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from cmig.core.namespace import NamespaceGateResult
from cmig.core.tidy import TidyBundle
from cmig.gui.graph_data import gate_ui_data, graph_payload

_ASSET = Path(__file__).parent / "assets" / "graph.html"


class InteractionGraphView(QWidget):
    """tidy bundle 을 Cytoscape.js 그래프로 렌더하는 위젯 (§11)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pending: dict | None = None
        self._ready = False
        self._web = QWebEngineView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._web)
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

    def set_bundle(
        self, bundle: TidyBundle, gate: NamespaceGateResult | None = None
    ) -> None:
        """그래프 데이터 주입. 페이지 로드 전이면 큐잉 후 loadFinished 시 주입."""
        payload = graph_payload(bundle, gate)
        if self._ready:
            self._inject(payload)
        else:
            self._pending = payload

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
