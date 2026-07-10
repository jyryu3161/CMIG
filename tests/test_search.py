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
    joint_target_solve,
    rank_consortia,
    score_target_result,
    target_flux_domain,
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
    assert target_flux_domain(Direction.MAX_SECRETION) == (0.0, None)
    assert target_flux_domain(Direction.MIN_SECRETION) == (0.0, None)
    assert target_flux_domain(Direction.MAX_UPTAKE) == (None, 0.0)
    assert target_flux_domain(Direction.MIN_UPTAKE) == (None, 0.0)


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


@pytest.mark.parametrize(
    ("direction", "lower", "upper"),
    [
        (Direction.MIN_SECRETION, -1e-8, float("inf")),
        (Direction.MIN_UPTAKE, float("-inf"), 1e-8),
    ],
)
def test_target_solve_enforces_direction_sign_domain(direction, lower, upper):
    eng = MicomEngine()
    comm = eng.build_community(build_taxonomy(), cmig_solver="gurobi")
    result = target_max_solve(comm, TargetSpec("ac", direction), solver="gurobi")
    assert result.status == "optimal"
    assert lower <= result.target_flux <= upper


def test_target_solve_rejects_invalid_growth_fraction():
    eng = MicomEngine()
    comm = eng.build_community(build_taxonomy(), cmig_solver="gurobi")
    with pytest.raises(ValueError, match="growth_fraction"):
        target_max_solve(comm, _spec(), growth_fraction=0.0)


def test_target_solve_handles_solver_returning_no_solution(monkeypatch):
    from cobra import Metabolite, Model, Reaction

    metabolite = Metabolite("ac_m", compartment="m")
    model = Model("no_solution")
    target = Reaction("EX_ac_m")
    target.add_metabolites({metabolite: -1.0})
    target.bounds = (-1000.0, 1000.0)
    model.add_reactions([target])
    model.objective = target
    monkeypatch.setattr(model, "optimize", lambda: None)

    result = target_max_solve(
        model, _spec(), growth_fraction=0.5, mu_community=1.0, solver="gurobi"
    )

    assert result.status == "solver_no_solution"
    assert result.diagnostic is not None


def test_joint_multi_target_uses_one_flux_vector_not_combined_individual_optima():
    """A shared precursor permits only five total target units after the growth floor.

    Independent target optima would report a=5 and b=5 together. The joint LP must return one
    feasible vector with a+b<=5.
    """
    from cobra import Metabolite, Model, Reaction

    precursor = Metabolite("p_c", compartment="c")
    model = Model("joint_target_tradeoff")
    source = Reaction("SOURCE")
    source.add_metabolites({precursor: 1.0})
    source.bounds = (0.0, 10.0)
    growth = Reaction("GROWTH")
    growth.add_metabolites({precursor: -1.0})
    growth.bounds = (0.0, 1000.0)
    target_a = Reaction("EX_a_m")
    target_a.add_metabolites({precursor: -1.0})
    target_a.bounds = (-1000.0, 1000.0)
    target_b = Reaction("EX_b_m")
    target_b.add_metabolites({precursor: -1.0})
    target_b.bounds = (-1000.0, 1000.0)
    model.add_reactions([source, growth, target_a, target_b])
    model.objective = growth

    result = joint_target_solve(
        model,
        [TargetSpec("a"), TargetSpec("b")],
        normalization_scales={"a": 1.0, "b": 1.0},
        growth_fraction=0.5,
        mu_community=10.0,
        solver="gurobi",
    )
    assert result.status == "optimal"
    assert result.community_growth >= 5.0 - 1e-7
    assert result.target_fluxes["a"] >= -1e-8
    assert result.target_fluxes["b"] >= -1e-8
    assert sum(result.target_fluxes.values()) <= 5.0 + 1e-7


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
