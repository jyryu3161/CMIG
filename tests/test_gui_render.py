"""Track-A — GUI offscreen 실행 검증 (closes G-7). Plan SC: SC-H1.

Design Ref(hardening): §2 — PySide6 위젯을 QT_QPA_PLATFORM=offscreen 에서 *실제로*
인스턴스화·렌더한다. baseline 에서 GUI 는 한 번도 실행된 적 없음(G-7, "never executed").
본 테스트는 그것을 '실행 + 산출' 증거로 전환한다.

정직성 경계: offscreen 렌더 = 위젯이 예외 없이 실행되고 DOM/픽셀 산출을 낸다는 증거이며,
human 시각 디자인 QA 가 아니다(후자는 G-7b, 별도). 1차 게이트는 QWebEngine 비동기 픽셀이
아니라 **DOM count**(runJavaScript)로 둔다 — Cytoscape 가 payload 를 실제로 수신했는지 검증.

cytoscape.js 는 로컬 번들(assets/cytoscape.min.js) — 네트워크 비의존(결정성).
"""

from __future__ import annotations

import pytest

# Qt 미설치(=gui extra 없음) 환경에서는 전체 skip.
pytest.importorskip("PySide6.QtWebEngineWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.core.namespace import (  # noqa: E402
    Confidence,
    DecisionStatus,
    NamespaceDecision,
    evaluate_gate,
)
from cmig.gui.graph_view import GateBadge, InteractionGraphView  # noqa: E402

_LOAD_TIMEOUT_MS = 10_000


def _bundle():
    # A 가 ac 분비(+8), B 가 ac 흡수(−5) → nodes {A, B, medium}=3, cf+secretion+uptake.
    r = SolveResult(
        objective=0.9, member_growth={"A": 0.5, "B": 0.4},
        abundances={"A": 0.5, "B": 0.5}, external_exchange={"ac": 3.0},
        member_exchange={"A": {"ac": 8.0}, "B": {"ac": -5.0}},
        status="optimal", flux_report_status="full", growth_solver="gurobi",
        flux_solver="gurobi", members=["A", "B"],
    )
    return build_tidy(r)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _run_js(view: InteractionGraphView, script: str, *, timeout_ms: int = 4000):
    """QWebEngineView.runJavaScript 를 동기 대기로 감싼다(테스트 결정성)."""
    loop = QEventLoop()
    box: dict = {}

    def _cb(result):
        box["result"] = result
        loop.quit()

    view._web.page().runJavaScript(script, _cb)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return box.get("result")


def _wait_loaded(view: InteractionGraphView) -> None:
    """graph.html loadFinished 까지 이벤트 루프 대기."""
    if view._ready:
        return
    loop = QEventLoop()
    view._web.loadFinished.connect(lambda _ok: loop.quit())
    QTimer.singleShot(_LOAD_TIMEOUT_MS, loop.quit)
    loop.exec()


def test_widget_constructs_and_renders_without_error(qapp):
    """위젯이 offscreen 에서 예외 없이 생성·로드된다(바인딩/asset/JS bridge 무결)."""
    view = InteractionGraphView()
    view.resize(640, 480)
    _wait_loaded(view)
    assert view._ready is True, "graph.html loadFinished 실패 — asset/JS bridge 결함"


def test_cytoscape_receives_all_nodes(qapp):
    """DOM gate: graph defaults to cross-feeding focus and can restore full graph."""
    bundle = _bundle()
    expected_nodes = bundle.nodes.num_rows  # A, B, medium = 3

    view = InteractionGraphView()
    view.resize(640, 480)
    _wait_loaded(view)
    view.set_bundle(bundle)
    # cytoscape 레이아웃은 동기 — 주입 직후 노드 수 조회.
    n = _run_js(view, "cy ? cy.nodes().length : -1")
    assert n is not None, "runJavaScript 무응답 — QWebEngine JS 실행 불가"
    assert int(n) == 2, "default cross-feeding view should hide isolated medium node"

    e = _run_js(view, "cy ? cy.edges().length : -1")
    assert int(e) == 1, "default graph should focus on cross-feeding edges"
    assert view.edge_table.rowCount() == 1
    assert view.edge_table.item(0, 3).text() == "cross_feeding"

    view.set_edge_filters(cross_feeding=True, secretion=True, uptake=True)
    n_all = _run_js(view, "cy ? cy.nodes().length : -1")
    assert int(n_all) == expected_nodes, f"Cytoscape 노드 {n_all} != tidy 노드 {expected_nodes}"
    e_all = _run_js(view, "cy ? cy.edges().length : -1")
    assert int(e_all) == bundle.edges.num_rows, "edge filter did not restore all edges"
    assert view.edge_table.rowCount() == bundle.edges.num_rows


def test_gate_blocked_reflected_in_dom(qapp):
    """gate 정책(high=block)이 DOM 에 반영(FR-1b.3 실행 검증)."""
    bundle = _bundle()
    gate = evaluate_gate([
        NamespaceDecision("ac", "s", None, Confidence.HIGH, DecisionStatus.UNRESOLVED),
    ])
    view = InteractionGraphView()
    view.resize(640, 480)
    _wait_loaded(view)
    view.set_bundle(bundle, gate)
    klass = _run_js(view, "document.getElementById('gate').className")
    text = _run_js(view, "document.getElementById('gate').textContent")
    assert klass == "gate-blocked", f"차단 상태인데 class={klass}"
    assert "BLOCKED" in (text or ""), f"gate 텍스트에 BLOCKED 없음: {text}"


def test_grab_produces_nonempty_image(qapp):
    """위젯 grab() 이 non-empty 이미지 산출(픽셀 레벨 실행 증거, best-effort)."""
    view = InteractionGraphView()
    view.resize(320, 240)
    _wait_loaded(view)
    view.set_bundle(_bundle())
    img = view.grab().toImage()
    assert not img.isNull(), "grab 이미지 null"
    assert img.width() >= 320 and img.height() == 240
    # 픽셀 분산은 QWebEngine 비동기 paint 에 의존 → 결정적 게이트는
    # '크기 있는 non-null surface 산출'까지. 콘텐츠 검증은 DOM 게이트가 대체.


def test_cytoscape_can_export_nonblank_png(qapp):
    """Cytoscape renderer produces real graph pixels, independent of QWidget grab timing."""
    view = InteractionGraphView()
    view.resize(640, 480)
    _wait_loaded(view)
    view.set_bundle(_bundle())
    data_uri = _run_js(
        view,
        "cy ? cy.png({full: true, scale: 1, bg: 'white'}) : ''",
        timeout_ms=6000,
    )
    assert isinstance(data_uri, str)
    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 3000, "Cytoscape PNG export is unexpectedly small/blank"


def test_gate_badge_widget_sync(qapp):
    """GateBadge(QLabel, 동기) — gate 결과 텍스트/색 반영(JS 무관 결정적 검증)."""
    badge = GateBadge()
    badge.set_gate(evaluate_gate([
        NamespaceDecision("ac", "s", None, Confidence.HIGH, DecisionStatus.UNRESOLVED),
    ]))
    assert "BLOCKED" in badge.text()
    assert "a50f15" in badge.styleSheet()  # 차단=빨강

    badge.set_gate(evaluate_gate([
        NamespaceDecision("glc", "s", "bigg:glc", Confidence.HIGH, DecisionStatus.RESOLVED),
    ]))
    assert "OK" in badge.text()
    assert "137" in badge.styleSheet()  # 정상=파랑
