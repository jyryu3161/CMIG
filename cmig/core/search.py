"""Consortium Search — target-max solve + 멤버셋 랭킹 (Roadmap Phase 3.4, §14 G3).

Design Ref: §14 / cmig-search.design. Plan SC: SC-SR1~SR5.

R-OBJ(검증됨): micom Community 는 cobra Model 서브클래스 → community growth 식에 하한 제약
(growth ≥ f·μ_c*)을 optlang public API 로 추가하고 objective 를 target exchange 로 오버라이드해
target-max 재solve 가능(spike 결과 status=optimal). gurobi 전제(LP).

[honesty] target-max 는 정규화 전 raw flux. 멤버셋 랭킹은 exhaustive(소규모 ≤ N_MAX)만 —
대규모 heuristic/Pareto/GUI 는 후속 feature(stub 으로 '완료' 위장 금지).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any


class Direction(enum.Enum):
    MAX_SECRETION = "max_secretion"      # target 분비 최대화 (objective = +EX_target)
    MIN_SECRETION = "min_secretion"
    MAX_UPTAKE = "max_uptake"            # target 흡수 최대화 (objective = −EX_target)
    MIN_UPTAKE = "min_uptake"


@dataclass(frozen=True)
class TargetSpec:
    """탐색 표적. metabolite=환경 exchange 의 대사체(예: 'ac' → EX_ac_m)."""

    metabolite: str
    direction: Direction = Direction.MAX_SECRETION
    weight: float = 1.0

    def exchange_id(self) -> str:
        return f"EX_{self.metabolite}_m"


@dataclass(frozen=True)
class TargetMaxResult:
    target: str
    direction: str
    target_flux: float
    community_growth: float
    status: str
    diagnostic: str | None = None


def target_objective_direction(direction: Direction) -> str:
    """CMIG semantic direction → cobra objective direction.

    exchange 부호는 +분비/-흡수이므로 흡수 최대화는 exchange flux 최소화다.
    """
    if direction in (Direction.MAX_SECRETION, Direction.MIN_UPTAKE):
        return "max"
    return "min"


def _community_growth_star(community: Any) -> float:
    """μ_c* = 최대 community growth. target-max growth floor 의 기준값."""
    sol = community.cooperative_tradeoff(fraction=1.0, fluxes=False)
    gr = sol.growth_rate
    return float(gr.iloc[0]) if hasattr(gr, "iloc") else float(gr)


def target_max_solve(
    community: Any, spec: TargetSpec, *, growth_fraction: float = 0.5,
    mu_community: float | None = None, solver: str = "gurobi",
) -> TargetMaxResult:
    """target-max: max(target exchange) s.t. community growth ≥ growth_fraction·μ_c* (R-OBJ).

    mu_community 는 μ_c* 값이다. None 이면 cooperative_tradeoff(fraction=1.0) 로 μ_c*를 먼저
    산출한다. gurobi(LP) 전제.
    """
    from cmig.core.single_model import _require_lp
    _require_lp(solver)
    community.solver = solver
    if mu_community is None:
        mu_community = _community_growth_star(community)

    ex_id = spec.exchange_id()
    if ex_id not in {r.id for r in community.reactions}:
        from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts
        diag = diagnostic_from_parts([(
            DiagnosticCode.CAPABILITY_MISSING, f"target exchange 부재: {ex_id}")])
        return TargetMaxResult(ex_id, spec.direction.value, 0.0, 0.0, "missing", diag)

    with community as m:
        growth_expr = m.objective.expression                      # community growth 식
        floor = m.problem.Constraint(
            growth_expr, lb=growth_fraction * mu_community, name="cmig_growth_floor")
        m.add_cons_vars([floor])
        m.solver.update()
        rxn = m.reactions.get_by_id(ex_id)
        m.objective = rxn
        m.objective.direction = target_objective_direction(spec.direction)
        sol = m.optimize()
        status = sol.status
        flux = float(rxn.flux) if status == "optimal" else 0.0
        # community growth at target-max 해 = growth_floor 제약의 primal(LHS 값)
        growth = float(floor.primal) if status == "optimal" else 0.0
    return TargetMaxResult(ex_id, spec.direction.value, flux, growth, status)


def score_target_result(result: TargetMaxResult, spec: TargetSpec) -> float:
    """가중 점수(정규화 전 raw·weight). 모든 direction 에서 클수록 우수."""
    if result.status != "optimal":
        return float("-inf")
    match spec.direction:
        case Direction.MAX_SECRETION:
            signed = result.target_flux
        case Direction.MIN_SECRETION:
            signed = -result.target_flux
        case Direction.MAX_UPTAKE:
            signed = -result.target_flux
        case Direction.MIN_UPTAKE:
            signed = result.target_flux
    return spec.weight * signed


@dataclass(frozen=True)
class RankedConsortium:
    members: tuple[str, ...]
    score: float
    target_flux: float
    community_growth: float
    status: str


def rank_consortia(
    engine: Any, taxonomy: Any, spec: TargetSpec, *,
    sizes: tuple[int, ...] = (2,), growth_fraction: float = 0.5,
    solver: str = "gurobi", n_max: int = 20,
) -> list[RankedConsortium]:
    """후보 멤버셋(taxonomy 부분집합)을 target-max 로 평가·랭킹 (exhaustive, ≤ n_max).

    [honesty] exhaustive 만 — 후보 수 > n_max 면 ValueError(silent 절단 금지).
    """
    import itertools

    ids = [str(x) for x in taxonomy["id"]]
    candidates: list[tuple[str, ...]] = []
    for k in sizes:
        candidates.extend(tuple(c) for c in itertools.combinations(ids, k))
    if len(candidates) > n_max:
        raise ValueError(
            f"후보 {len(candidates)} > n_max={n_max} — exhaustive 한계 초과. "
            f"heuristic/Pareto 전략은 후속 feature(silent 절단 금지)")

    ranked: list[RankedConsortium] = []
    for members in candidates:
        sub = taxonomy[taxonomy["id"].isin(members)].copy()
        community = engine.build_community(sub, cmig_solver=solver)
        res = target_max_solve(community, spec, growth_fraction=growth_fraction, solver=solver)
        ranked.append(RankedConsortium(
            members=members, score=score_target_result(res, spec),
            target_flux=res.target_flux, community_growth=res.community_growth,
            status=res.status))
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked
