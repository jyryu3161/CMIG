"""tidy → Cytoscape.js elements/style 변환 (순수 데이터 브릿지).

Design Ref: §11 Interaction Graph Viewer / FR-1b.1·1b.2·1b.3 / Option C (gui=presentation).
QWebEngineView 에 로드되는 Cytoscape.js payload 를 tidy 계약(nodes/edges)에서 생성한다.
이 모듈은 Qt 비의존 — 단위 테스트 가능. 부호 범례 상시(§11).
"""

from __future__ import annotations

from typing import Any

from cmig.core.namespace import NamespaceGateResult
from cmig.core.tidy import TidyBundle

# 부호 범례 (상시 노출, §11·glossary §1.A)
SIGN_LEGEND: list[dict[str, str]] = [
    {"symbol": "+", "meaning": "secretion to the environment or pool"},
    {"symbol": "−", "meaning": "uptake from the environment or pool"},
    {"symbol": "→", "meaning": "cross-feeding from secretor to consumer, weight=min"},
]

# Cytoscape.js stylesheet — node_type/edge_type 인코딩 (§11 노드/엣지 인코딩).
STYLESHEET: list[dict[str, Any]] = [
    {"selector": "node",
     "style": {"font-size": 12, "min-zoomed-font-size": 8, "font-weight": 600,
               "color": "#1f2933", "text-outline-width": 2, "text-outline-color": "#ffffff",
               "text-wrap": "wrap", "text-max-width": 110, "text-valign": "bottom",
               "text-halign": "center", "text-margin-y": 8, "width": 42, "height": 42}},
    {"selector": "node[ntype = 'member']",
     "style": {"background-color": "#2c7fb8", "shape": "ellipse", "label": "data(label)"}},
    {"selector": "node[ntype = 'environment_pool']",
     "style": {"background-color": "#999999", "shape": "round-rectangle", "label": "data(label)",
               "width": 58, "height": 42}},
    {"selector": "edge",
     "style": {"curve-style": "bezier", "opacity": 0.72, "target-arrow-shape": "triangle",
               "arrow-scale": 0.75}},
    {"selector": "edge[etype = 'cross_feeding']",
     "style": {"line-color": "#d95f0e", "target-arrow-color": "#d95f0e",
               "width": "mapData(weight, 0, 10, 1, 6)"}},
    {"selector": "edge[etype = 'secretion']",
     "style": {"line-color": "#31a354", "target-arrow-color": "#31a354",
               "line-style": "solid", "width": "mapData(weight, 0, 10, 1, 4)"}},
    {"selector": "edge[etype = 'uptake']",
     "style": {"line-color": "#756bb1", "target-arrow-color": "#756bb1",
               "line-style": "dashed", "width": "mapData(weight, 0, 10, 1, 4)"}},
    {"selector": ".faded",
     "style": {"opacity": 0.16, "text-opacity": 0.16}},
]

# 결정적 레이아웃 권장(§9 stress); padding 은 dense graph 라벨 겹침을 줄인다.
DEFAULT_LAYOUT = {"name": "cose", "animate": False, "padding": 100}


def _node_element(row: dict[str, Any]) -> dict[str, Any]:
    return {"data": {
        "id": row["node_id"],
        "label": row.get("label") or row["node_id"],
        "ntype": row["node_type"],
        "growth": row.get("growth"),
        "abundance": row.get("abundance"),
    }}


def _edge_element(i: int, row: dict[str, Any]) -> dict[str, Any]:
    return {"data": {
        "id": f"e{i}",
        "source": row["source_id"],
        "target": row["target_id"],
        "etype": row["edge_type"],
        "metabolite": row["metabolite"],
        "weight": row["weight"],
        "label": row.get("label"),
    }}


def to_elements(bundle: TidyBundle) -> list[dict[str, Any]]:
    """TidyBundle → Cytoscape.js elements (nodes + edges)."""
    bundle.validate()
    elements: list[dict[str, Any]] = [_node_element(r) for r in bundle.nodes.to_pylist()]
    elements += [_edge_element(i, r) for i, r in enumerate(bundle.edges.to_pylist())]
    return elements


def filter_elements(
    elements: list[dict[str, Any]],
    *,
    edge_types: set[str] | None = None,
    min_weight: float | None = None,
    node_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """필터 (FR-1b.2). edge_types/min_weight/node_ids 로 부분집합 추출.

    edge 가 남으려면 양 끝 노드도 유지된다(linked selection 일관성).
    """
    nodes = [e for e in elements if "source" not in e["data"]]
    edges = [e for e in elements if "source" in e["data"]]
    if edge_types is not None:
        edges = [e for e in edges if e["data"]["etype"] in edge_types]
    if min_weight is not None:
        edges = [e for e in edges if (e["data"]["weight"] or 0.0) >= min_weight]
    if node_ids is not None:
        nodes = [n for n in nodes if n["data"]["id"] in node_ids]
        keep = {n["data"]["id"] for n in nodes}
        edges = [e for e in edges if e["data"]["source"] in keep and e["data"]["target"] in keep]
    # node_ids 미지정 시 모든 노드 유지(고립 노드도 표시)
    return nodes + edges


def gate_ui_data(gate: NamespaceGateResult) -> dict[str, Any]:
    """Gate UI (FR-1b.3) — coverage%·차단 상태·unresolved 바로가기 데이터."""
    return {
        "blocked": gate.blocked,
        "coverage_pct": round(gate.coverage_pct, 2),
        "unresolved_high": [d.metabolite for d in gate.unresolved_high],
        "warned_low": [d.metabolite for d in gate.warned_low],
        "status_text": (
            "BLOCKED — unresolved high-confidence mapping blocks solve"
            if gate.blocked else f"OK — coverage {gate.coverage_pct:.0f}%"
        ),
    }


def graph_payload(
    bundle: TidyBundle, gate: NamespaceGateResult | None = None
) -> dict[str, Any]:
    """QWebEngineView 로 전달할 전체 payload (elements+style+layout+legend+gate)."""
    payload: dict[str, Any] = {
        "elements": to_elements(bundle),
        "style": STYLESHEET,
        "layout": DEFAULT_LAYOUT,
        "legend": SIGN_LEGEND,
    }
    if gate is not None:
        payload["gate"] = gate_ui_data(gate)
    return payload
