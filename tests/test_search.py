"""Phase 3.4 — Consortium Search core (target-max + 랭킹). Plan SC: SC-SR1~SR5.

R-OBJ(검증): growth-floor 제약 + objective 오버라이드 → target-max(status=optimal). gurobi 전제.
3-member 번들 fixture(동종 E.coli → 대칭 결과)로 검증.
"""

from __future__ import annotations

import pytest

pytest.importorskip("micom")

from cmig.core.engine import MicomEngine  # noqa: E402
from cmig.core.search import (  # noqa: E402
    Direction,
    TargetSpec,
    rank_consortia,
    score_target_result,
    target_max_solve,
    target_objective_direction,
)
from cmig.golden_fixture import build_taxonomy  # noqa: E402


def _spec() -> TargetSpec:
    return TargetSpec(metabolite="ac", direction=Direction.MAX_SECRETION, weight=1.0)


def test_target_spec_exchange_id():
    assert TargetSpec(metabolite="ac").exchange_id() == "EX_ac_m"


def test_target_objective_direction_respects_exchange_sign():
    """흡수 최대화는 exchange 부호상 objective=min 이어야 한다."""
    assert target_objective_direction(Direction.MAX_SECRETION) == "max"
    assert target_objective_direction(Direction.MIN_SECRETION) == "min"
    assert target_objective_direction(Direction.MAX_UPTAKE) == "min"
    assert target_objective_direction(Direction.MIN_UPTAKE) == "max"


def test_target_max_solve_optimal():
    """SC-SR1: R-OBJ target-max → optimal, acetate flux>0, growth ≥ floor(0.5·μc*)."""
    eng = MicomEngine()
    comm = eng.build_community(build_taxonomy(), cmig_solver="gurobi")
    r = target_max_solve(comm, _spec(), growth_fraction=0.5, solver="gurobi")
    assert r.status == "optimal"
    assert r.target_flux > 1.0
    mu_star = eng.cooperative_tradeoff(comm, 1.0, cmig_solver="gurobi").objective
    assert r.community_growth >= 0.5 * mu_star - 1e-3       # growth-floor 충족


def test_target_max_missing_exchange():
    """SC-SR2: 부재 target → status=missing + capability_missing diagnostic(정직)."""
    eng = MicomEngine()
    comm = eng.build_community(build_taxonomy(), cmig_solver="gurobi")
    r = target_max_solve(comm, TargetSpec(metabolite="nonexistent_xyz"), solver="gurobi")
    assert r.status == "missing" and r.diagnostic is not None


def test_score_target_result():
    """SC-SR3: MAX_SECRETION 점수 = weight·target_flux. infeasible → -inf."""
    from cmig.core.search import TargetMaxResult
    spec = _spec()
    ok = TargetMaxResult("EX_ac_m", "max_secretion", 10.0, 0.2, "optimal")
    assert score_target_result(ok, spec) == 10.0
    bad = TargetMaxResult("EX_ac_m", "max_secretion", 0.0, 0.0, "infeasible")
    assert score_target_result(bad, spec) == float("-inf")


def test_score_target_result_respects_minimize_directions():
    """최소화 direction 도 rank score 는 클수록 우수해야 한다."""
    from cmig.core.search import TargetMaxResult

    high_flux = TargetMaxResult("EX_ac_m", "min_secretion", 10.0, 0.2, "optimal")
    low_flux = TargetMaxResult("EX_ac_m", "min_secretion", 2.0, 0.2, "optimal")
    assert score_target_result(low_flux, TargetSpec("ac", Direction.MIN_SECRETION)) > (
        score_target_result(high_flux, TargetSpec("ac", Direction.MIN_SECRETION))
    )

    high_uptake = TargetMaxResult("EX_ac_m", "min_uptake", -10.0, 0.2, "optimal")
    low_uptake = TargetMaxResult("EX_ac_m", "min_uptake", -2.0, 0.2, "optimal")
    assert score_target_result(low_uptake, TargetSpec("ac", Direction.MIN_UPTAKE)) > (
        score_target_result(high_uptake, TargetSpec("ac", Direction.MIN_UPTAKE))
    )


def test_rank_consortia_exhaustive():
    """SC-SR4: 2-member 부분집합 랭킹(exhaustive), score 내림차순."""
    eng = MicomEngine()
    tax = build_taxonomy()
    ranked = rank_consortia(eng, tax, _spec(), sizes=(2,), n_max=20)
    assert len(ranked) == 3                               # C(3,2)
    assert all(rc.status == "optimal" for rc in ranked)
    scores = [rc.score for rc in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_consortia_nmax_guard():
    """SC-SR5: 후보 > n_max → ValueError(silent 절단 금지, honesty)."""
    eng = MicomEngine()
    with pytest.raises(ValueError, match="n_max"):
        rank_consortia(eng, build_taxonomy(), _spec(), sizes=(1, 2, 3), n_max=2)
