"""Robustness — 단일 3-member golden 너머의 견고성. Plan SC: SC-H4.

Design Ref(hardening): §5.3 — baseline 은 golden 이 단일 3-member community 하나뿐이라
견고성이 미지수였다. 여기서 (1) 더 큰 community(4-member, 다른 크기), (2) infeasible 입력의
파이프라인 통과(silent 금지), (3) edge-media(0 근방 flux) sign 경계를 검증한다.

2nd community 는 captured-golden(hash 스냅샷) 대신 **불변식 검증**으로 둔다 — OD-47 교훈:
OSQP cross-process 비결정성으로 captured golden 은 취약하나, 불변식(노드 보존·sign 규약·
run_hash 결정성)은 cross-process 에 강건하다.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("micom")

from cmig.core.delta import compute_delta  # noqa: E402
from cmig.core.engine import MicomEngine, SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.core.manifest import compute_run_hash  # noqa: E402
from cmig.core.sandbox import SandboxState, evaluate_sandbox  # noqa: E402
from cmig.core.sign import NOISE_FLOOR, Label, classify  # noqa: E402
from cmig.golden_fixture import TRADEOFF_F, _run_hash_components  # noqa: E402

N_LARGE = 4   # golden=3 보다 큰 community (test_taxonomy 최대)


@pytest.fixture(scope="module")
def large_result():
    """4-member community 실 solve (golden 과 다른 크기)."""
    eng = MicomEngine()
    from micom.data import test_taxonomy
    taxonomy = test_taxonomy().iloc[:N_LARGE].copy()
    community = eng.build_community(taxonomy, cmig_solver="gurobi")
    return eng.cooperative_tradeoff(community, TRADEOFF_F, cmig_solver="gurobi")


def test_larger_community_invariants(large_result):
    """4-member: 전 멤버 growth 키·노드 보존·optimal."""
    r = large_result
    assert r.status == "optimal"
    assert len(r.members) == N_LARGE
    assert set(r.member_growth) == set(r.members)        # silent-drop 없음
    bundle = build_tidy(r)
    assert bundle.nodes.num_rows == N_LARGE + 1          # 멤버 + environment_pool


def test_larger_community_sign_convention(large_result):
    """4-member: profile 부호 규약(+secretion/−uptake) 유지(크기 무관)."""
    bundle = build_tidy(large_result)
    for row in bundle.profile.to_pylist():
        if row["net_flux"] > NOISE_FLOOR:
            assert row["label"] == "secretion"
        elif row["net_flux"] < -NOISE_FLOOR:
            assert row["label"] == "uptake"
        assert row["ui_flux"] >= 0.0


def test_larger_community_run_hash_deterministic(large_result):
    """4-member: run_hash 결정성([HASH-SINGLE]) — 크기 무관."""
    h1 = compute_run_hash(_run_hash_components(large_result))
    h2 = compute_run_hash(_run_hash_components(large_result))
    assert h1 == h2 and len(h1) == 64


# ── infeasible 입력의 파이프라인 통과 (silent 금지) ──────────────────────────

def _infeasible_sr():
    """infeasible solve 의 현실적 형상 — objective NaN, status='infeasible'."""
    return SolveResult(
        objective=math.nan,
        member_growth={"A": math.nan, "B": math.nan},
        abundances={"A": 0.5, "B": 0.5},
        external_exchange={"ac": 1.0}, member_exchange={"A": {}, "B": {}},
        status="infeasible", flux_report_status="full",
        growth_solver="gurobi", flux_solver="gurobi", members=["A", "B"],
    )


def _ok_sr():
    return SolveResult(
        objective=0.5, member_growth={"A": 0.3, "B": 0.2},
        abundances={"A": 0.5, "B": 0.5},
        external_exchange={"ac": 1.0}, member_exchange={"A": {}, "B": {}},
        status="optimal", flux_report_status="full",
        growth_solver="gurobi", flux_solver="gurobi", members=["A", "B"],
    )


def test_infeasible_surfaces_through_delta_and_sandbox():
    """infeasible 입력 → delta·sandbox 가 status='failed' 로 노출(silent NaN 위장 금지)."""
    d = compute_delta(_ok_sr(), _infeasible_sr())
    assert d.status == "failed" and d.diagnostic
    sb = evaluate_sandbox(_ok_sr(), _infeasible_sr(), state=SandboxState.PREVIEW)
    assert sb.status == "failed"
    assert sb.no_significant_change is False             # '변화 없음' 위장 안 함


# ── edge-media: 0 근방 flux sign 경계 ────────────────────────────────────────

def test_near_zero_flux_is_no_flow():
    """edge: |flux| ≤ NOISE_FLOOR → 무흐름(label=None), 잡음을 secretion/uptake 오분류 안 함."""
    assert classify(5e-7) is None                        # < 1e-6 → 무흐름
    assert classify(-5e-7) is None
    assert classify(2e-6) is Label.SECRETION             # > 1e-6 → 분비
    assert classify(-2e-6) is Label.UPTAKE
