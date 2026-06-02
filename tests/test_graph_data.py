"""module-1b GUI 데이터 브릿지 — tidy → Cytoscape. FR-1b.1/1b.2/1b.3 (Qt 비의존)."""

from cmig.core.engine import SolveResult
from cmig.core.interactions import build_tidy
from cmig.core.namespace import (
    Confidence,
    DecisionStatus,
    NamespaceDecision,
    evaluate_gate,
)
from cmig.gui.graph_data import (
    SIGN_LEGEND,
    STYLESHEET,
    filter_elements,
    gate_ui_data,
    graph_payload,
    to_elements,
)


def _bundle():
    # A 가 ac 분비(+8), B 가 ac 흡수(−5) → cross_feeding A→B + secretion/uptake
    r = SolveResult(
        objective=0.9, member_growth={"A": 0.5, "B": 0.4}, abundances={"A": 0.5, "B": 0.5},
        external_exchange={"ac": 3.0}, member_exchange={"A": {"ac": 8.0}, "B": {"ac": -5.0}},
        status="optimal", flux_report_status="full", growth_solver="gurobi",
        flux_solver="gurobi", members=["A", "B"],
    )
    return build_tidy(r)


def test_to_elements_nodes_and_edges():
    els = to_elements(_bundle())
    nodes = [e for e in els if "source" not in e["data"]]
    edges = [e for e in els if "source" in e["data"]]
    assert {n["data"]["id"] for n in nodes} == {"A", "B", "medium"}
    assert {n["data"]["ntype"] for n in nodes} == {"member", "environment_pool"}
    etypes = {e["data"]["etype"] for e in edges}
    assert "cross_feeding" in etypes and "secretion" in etypes and "uptake" in etypes
    # edge id 유일
    assert len({e["data"]["id"] for e in edges}) == len(edges)


def test_filter_by_edge_type():
    els = to_elements(_bundle())
    cf = filter_elements(els, edge_types={"cross_feeding"})
    edges = [e for e in cf if "source" in e["data"]]
    assert edges and all(e["data"]["etype"] == "cross_feeding" for e in edges)


def test_filter_by_min_weight():
    els = to_elements(_bundle())
    out = filter_elements(els, min_weight=6.0)        # secretion 8 만 남음(cf 5·uptake 5 제외)
    edges = [e for e in out if "source" in e["data"]]
    assert all((e["data"]["weight"] or 0) >= 6.0 for e in edges)


def test_filter_by_node_ids_keeps_internal_edges():
    els = to_elements(_bundle())
    out = filter_elements(els, node_ids={"A", "medium"})
    ids = {n["data"]["id"] for n in out if "source" not in n["data"]}
    assert ids == {"A", "medium"}
    for e in (x for x in out if "source" in x["data"]):
        assert e["data"]["source"] in ids and e["data"]["target"] in ids


def test_gate_ui_data_blocked():
    decisions = [
        NamespaceDecision("ac", "s", None, Confidence.HIGH, DecisionStatus.UNRESOLVED),
        NamespaceDecision("glc", "s", "bigg:glc", Confidence.HIGH, DecisionStatus.RESOLVED),
    ]
    data = gate_ui_data(evaluate_gate(decisions))
    assert data["blocked"] is True
    assert data["unresolved_high"] == ["ac"]
    assert "BLOCKED" in data["status_text"]


def test_graph_payload_structure():
    payload = graph_payload(_bundle())
    assert set(payload) >= {"elements", "style", "layout", "legend"}
    assert payload["style"] is STYLESHEET
    assert payload["legend"] is SIGN_LEGEND
    assert "gate" not in payload                       # gate 미전달 시 없음


def test_graph_style_has_readable_node_text_and_zoom_padding():
    node_style = next(s["style"] for s in STYLESHEET if s["selector"] == "node")
    assert node_style["font-size"] <= 12
    assert node_style["text-wrap"] == "wrap"
    assert node_style["text-max-width"] <= 120
    assert graph_payload(_bundle())["layout"]["padding"] >= 80


def test_graph_payload_with_gate():
    gate = evaluate_gate([
        NamespaceDecision("x", "s", "bigg:x", Confidence.HIGH, DecisionStatus.RESOLVED),
    ])
    payload = graph_payload(_bundle(), gate)
    assert payload["gate"]["coverage_pct"] == 100.0
    assert payload["gate"]["blocked"] is False
