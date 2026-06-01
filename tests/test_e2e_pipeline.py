"""Track-B — End-to-end 수직 슬라이스 (6-hop 계약 매트릭스). Plan SC: SC-H2.

Design Ref(hardening): §3 — 실 3-member community solve 1회로 전 파이프라인을 관통하며
각 hop 경계 계약을 단언한다. baseline 은 조각을 *격리* 단위 테스트만 했고, 결합부(전 체인이
한 번에 통과하는가)는 미증명이었다. 본 테스트가 그 통합을 1-pass 로 보장한다.

  H1 model→engine   : status, 전 멤버 growth 키(silent-drop 금지)
  H2 engine→tidy    : schema_version, run_hash 11구성·결정성([HASH-SINGLE]), sign 규약
  H3 tidy→graph     : 노드 보존(members+pool == tidy nodes == graph nodes)
  H4 profile→R fig  : sign 일관 데이터 계약 + R 실산출(SVG)  (bar 방향=R 내부, 데이터 계약으로 검증)
  H5 graph→GUI      : offscreen DOM count == tidy nodes
  교차              : profile label ↔ edges edge_type 부호 일관(100%)
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("micom")

from cmig.core.manifest import RUN_HASH_COMPONENTS, compute_run_hash  # noqa: E402
from cmig.golden_fixture import _run_hash_components, solve  # noqa: E402
from cmig.gui.graph_data import to_elements  # noqa: E402
from cmig.render.client import FigureSpec, RenderClient, render_profile  # noqa: E402

SOLVER = "gurobi"  # 결정적 — golden sign 테스트와 동일 경로


@pytest.fixture(scope="module")
def pipeline():
    """실 solve 1회 → 전 hop 에서 공유(비용 절감)."""
    result, bundle = solve(SOLVER)
    return result, bundle


def test_h1_engine_status_and_all_members(pipeline):
    """H1: solve 결과 status optimal + 전 멤버 growth 키 존재(I-1 silent-drop 금지)."""
    result, _ = pipeline
    assert result.status == "optimal"
    assert result.objective > 0
    # 모든 member_id 가 growth dict 의 키로 존재(누락 None 허용, 키 자체는 필수)
    assert set(result.member_growth) == set(result.members)
    assert set(result.abundances) == set(result.members)


def test_h2_tidy_contract(pipeline):
    """H2: tidy schema_version·sign 규약·run_hash 11구성 결정성([HASH-SINGLE])."""
    result, bundle = pipeline
    # schema_version 존재(모든 테이블 첫 계약)
    for tbl in (bundle.nodes, bundle.edges, bundle.profile):
        assert "schema_version" in tbl.column_names, "tidy 테이블에 schema_version 누락"
    # sign 규약: net_flux>0 → secretion, <0 → uptake
    for r in bundle.profile.to_pylist():
        if r["net_flux"] > 0:
            assert r["label"] == "secretion"
        elif r["net_flux"] < 0:
            assert r["label"] == "uptake"
        assert r["ui_flux"] >= 0.0
    # run_hash: 단일 canonical 경로, 11구성, 결정적
    comps = _run_hash_components(result)
    h1 = compute_run_hash(comps)
    h2 = compute_run_hash(_run_hash_components(result))
    assert h1 == h2, "run_hash 비결정 — [HASH-SINGLE] 위반"
    assert len(RUN_HASH_COMPONENTS) == 11
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)


def test_h3_node_preservation(pipeline):
    """H3: tidy → graph elements 에서 노드 보존(members + environment_pool)."""
    result, bundle = pipeline
    expected = len(result.members) + 1  # + environment_pool
    assert bundle.nodes.num_rows == expected
    els = to_elements(bundle)
    graph_nodes = [e for e in els if "source" not in e["data"]]
    assert len(graph_nodes) == expected, "graph 노드 != tidy 노드(보존 위반)"
    graph_edges = [e for e in els if "source" in e["data"]]
    assert len(graph_edges) == bundle.edges.num_rows


def test_h4_render_produces_figure(pipeline, tmp_path):
    """H4: profile → R figure 실산출 + figure_spec sidecar(재현 자산)."""
    _, bundle = pipeline
    if not RenderClient().available():
        pytest.skip("Rscript 부재 — R hop skip (fallback 경로는 test_render 가 커버)")
    out = tmp_path / "profile.svg"
    spec = FigureSpec(format="svg", seed=42)
    rendered = render_profile(bundle, spec, out)
    assert rendered.exists() and rendered.stat().st_size > 0, "R figure 미산출/빈 파일"
    sidecar = Path(str(out) + ".figure_spec.json")
    assert sidecar.exists(), "figure_spec sidecar 누락(재현성)"


def test_h5_gui_dom_count(pipeline):
    """H5: graph → GUI offscreen DOM count == tidy 노드(track-A 게이트 재사용)."""
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from cmig.gui.graph_view import InteractionGraphView

    _, bundle = pipeline
    _app = QApplication.instance() or QApplication([])

    view = InteractionGraphView()
    view.resize(480, 360)
    if not view._ready:
        loop = QEventLoop()
        view._web.loadFinished.connect(lambda _ok: loop.quit())
        QTimer.singleShot(10_000, loop.quit)
        loop.exec()
    view.set_bundle(bundle)

    loop = QEventLoop()
    box: dict = {}
    view._web.page().runJavaScript(
        "cy ? cy.nodes().length : -1", lambda res: (box.__setitem__("n", res), loop.quit())
    )
    QTimer.singleShot(4000, loop.quit)
    loop.exec()
    assert int(box.get("n", -1)) == bundle.nodes.num_rows, "GUI DOM 노드 수 != tidy 노드"


def test_cross_hop_sign_consistency(pipeline):
    """교차: profile label ↔ edges edge_type 부호 일관(전 체인 부호 무결성, 100%)."""
    _, bundle = pipeline
    # secretion/uptake edge 의 label 컬럼이 edge_type 부호와 일치
    for e in bundle.edges.to_pylist():
        if e["edge_type"] in ("secretion", "uptake"):
            assert e["label"] == e["edge_type"], "edge label↔edge_type 부호 불일치"
        # cross_feeding 은 분비측 부호(secretion) 기준
        elif e["edge_type"] == "cross_feeding":
            assert e["label"] == "secretion"
    # profile 의 secretion metabolite 는 적어도 하나의 secretion/cross_feeding edge 로 연결
    prof_secretion = {
        r["metabolite"] for r in bundle.profile.to_pylist() if r["label"] == "secretion"
    }
    edge_secretion_metab = {
        e["metabolite"] for e in bundle.edges.to_pylist()
        if e["edge_type"] in ("secretion", "cross_feeding")
    }
    assert prof_secretion <= edge_secretion_metab, "profile secretion 이 edge 에 미반영"
