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
import math
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


@dataclass(frozen=True)
class MultiTargetSolveResult:
    """One jointly feasible multi-target LP solution.

    ``target_fluxes`` are read from one flux vector. ``signed_values`` converts every configured
    direction to a larger-is-better axis but never combines optima from different solves.
    """

    target_fluxes: dict[str, float]
    signed_values: dict[str, float]
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


def target_flux_domain(direction: Direction) -> tuple[float | None, float | None]:
    """Physical sign domain for a direction-specific target objective.

    Secretion objectives operate only on ``v >= 0`` and uptake objectives only on ``v <= 0``.
    Without this constraint, ``min_secretion`` degenerates into ``max_uptake`` and
    ``min_uptake`` degenerates into ``max_secretion``.
    """
    if direction in (Direction.MAX_SECRETION, Direction.MIN_SECRETION):
        return 0.0, None
    return None, 0.0


def signed_target_flux(flux: float, direction: Direction) -> float:
    """Direction-adjust raw flux so a larger value always means a better objective."""
    if direction in (Direction.MAX_SECRETION, Direction.MIN_UPTAKE):
        return float(flux)
    return -float(flux)


def _community_growth_star(community: Any) -> float:
    """μ_c* = 최대 community growth. target-max growth floor 의 기준값."""
    sol = community.cooperative_tradeoff(fraction=1.0, fluxes=False)
    if sol is None:
        raise ValueError("community maximum-growth solve returned no solution")
    gr = sol.growth_rate
    value = float(gr.iloc[0]) if hasattr(gr, "iloc") else float(gr)
    if not math.isfinite(value):
        raise ValueError(f"community maximum growth is non-finite: {value}")
    if value < 0.0:
        raise ValueError(f"community maximum growth is negative: {value}")
    return value


def _validate_growth_floor(growth_fraction: float, mu_community: float | None) -> None:
    if not math.isfinite(growth_fraction) or not (0.0 < growth_fraction <= 1.0):
        raise ValueError("growth_fraction must be finite and satisfy 0 < f <= 1")
    if mu_community is not None and (not math.isfinite(mu_community) or mu_community < 0.0):
        raise ValueError("mu_community must be finite and non-negative")


def _target_domain_constraint(model: Any, reaction: Any, direction: Direction, name: str) -> Any:
    lower, upper = target_flux_domain(direction)
    return model.problem.Constraint(reaction.flux_expression, lb=lower, ub=upper, name=name)


def target_max_solve(
    community: Any, spec: TargetSpec, *, growth_fraction: float = 0.5,
    mu_community: float | None = None, solver: str = "gurobi",
) -> TargetMaxResult:
    """target-max: max(target exchange) s.t. community growth ≥ growth_fraction·μ_c* (R-OBJ).

    mu_community 는 μ_c* 값이다. None 이면 cooperative_tradeoff(fraction=1.0) 로 μ_c*를 먼저
    산출한다. gurobi(LP) 전제.
    """
    from cmig.core.single_model import _require_lp, set_model_solver
    _validate_growth_floor(growth_fraction, mu_community)
    if not math.isfinite(spec.weight) or spec.weight < 0.0:
        raise ValueError("target weight must be finite and non-negative")
    _require_lp(solver)
    ex_id = spec.exchange_id()
    with community as m:
        set_model_solver(m, solver)
        if mu_community is None:
            try:
                mu_community = _community_growth_star(m)
            except ValueError as e:
                from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

                diag = diagnostic_from_parts([(DiagnosticCode.INFEASIBLE, str(e))])
                return TargetMaxResult(
                    ex_id, spec.direction.value, 0.0, 0.0, "baseline_failed", diag
                )
        if ex_id not in {r.id for r in m.reactions}:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.CAPABILITY_MISSING, f"target exchange 부재: {ex_id}")])
            return TargetMaxResult(ex_id, spec.direction.value, 0.0, 0.0, "missing", diag)
        growth_expr = m.objective.expression                      # community growth 식
        floor = m.problem.Constraint(
            growth_expr, lb=growth_fraction * mu_community, name="cmig_growth_floor")
        rxn = m.reactions.get_by_id(ex_id)
        domain = _target_domain_constraint(m, rxn, spec.direction, "cmig_target_sign_domain")
        m.add_cons_vars([floor, domain])
        m.solver.update()
        m.objective = rxn
        m.objective.direction = target_objective_direction(spec.direction)
        sol = m.optimize()
        if sol is None:
            solver_status = getattr(m.solver, "status", None)
            status = str(solver_status) if solver_status else "solver_no_solution"
            return TargetMaxResult(
                ex_id,
                spec.direction.value,
                0.0,
                0.0,
                status,
                f"target LP returned no solution object (solver_status={status})",
            )
        status = str(sol.status)
        flux = float(rxn.flux) if status == "optimal" else 0.0
        # community growth at target-max 해 = growth_floor 제약의 primal(LHS 값)
        growth = float(floor.primal) if status == "optimal" else 0.0
    diagnostic = None if status == "optimal" else f"target LP status={status}"
    return TargetMaxResult(ex_id, spec.direction.value, flux, growth, status, diagnostic)


def joint_target_solve(
    community: Any,
    specs: list[TargetSpec],
    *,
    normalization_scales: dict[str, float],
    growth_fraction: float = 0.5,
    mu_community: float | None = None,
    solver: str = "gurobi",
) -> MultiTargetSolveResult:
    """Optimize all targets in one LP and return fluxes from the same feasible solution.

    The objective is ``sum(weight * signed_flux / scale)``. Observed-range offsets are constants
    and therefore do not affect the optimizer; callers apply them when reporting normalized
    scores. Every direction receives an explicit secretion/uptake sign-domain constraint.
    """
    from cmig.core.single_model import _require_lp, set_model_solver

    _validate_growth_floor(growth_fraction, mu_community)
    if len(specs) < 2:
        raise ValueError("joint_target_solve requires at least two targets")
    metabolites = [spec.metabolite for spec in specs]
    if len(set(metabolites)) != len(metabolites):
        raise ValueError("multi-target metabolites must be unique")
    if any(not math.isfinite(spec.weight) or spec.weight < 0.0 for spec in specs):
        raise ValueError("multi-target weights must be finite and non-negative")
    if not any(spec.weight > 0.0 for spec in specs):
        raise ValueError("at least one multi-target weight must be positive")
    for spec in specs:
        scale = normalization_scales.get(spec.metabolite)
        if scale is None or not math.isfinite(scale) or scale <= 0.0:
            raise ValueError(f"normalization scale for {spec.metabolite!r} must be finite and > 0")

    _require_lp(solver)
    with community as model:
        set_model_solver(model, solver)
        if mu_community is None:
            try:
                mu_community = _community_growth_star(model)
            except ValueError as e:
                return MultiTargetSolveResult({}, {}, 0.0, "baseline_failed", str(e))
        missing = [
            spec.exchange_id() for spec in specs
            if spec.exchange_id() not in model.reactions
        ]
        if missing:
            return MultiTargetSolveResult(
                {}, {}, 0.0, "missing", f"target exchanges absent: {sorted(missing)}"
            )

        growth_expr = model.objective.expression
        floor = model.problem.Constraint(
            growth_expr,
            lb=growth_fraction * mu_community,
            name="cmig_multi_growth_floor",
        )
        constraints = [floor]
        objective = 0
        reactions: dict[str, Any] = {}
        for index, spec in enumerate(specs):
            reaction = model.reactions.get_by_id(spec.exchange_id())
            reactions[spec.metabolite] = reaction
            constraints.append(
                _target_domain_constraint(
                    model, reaction, spec.direction, f"cmig_multi_target_domain_{index}"
                )
            )
            sign = 1.0 if spec.direction in (
                Direction.MAX_SECRETION, Direction.MIN_UPTAKE
            ) else -1.0
            objective += (
                spec.weight / normalization_scales[spec.metabolite]
            ) * sign * reaction.flux_expression
        model.add_cons_vars(constraints)
        model.objective = model.problem.Objective(objective, direction="max")
        model.solver.update()
        solution = model.optimize()
        if solution is None:
            solver_status = getattr(model.solver, "status", None)
            status = str(solver_status) if solver_status else "solver_no_solution"
            return MultiTargetSolveResult(
                {}, {}, 0.0, status,
                f"joint target LP returned no solution object (solver_status={status})",
            )
        status = str(solution.status)
        if status != "optimal":
            return MultiTargetSolveResult({}, {}, 0.0, status, f"joint target LP status={status}")
        fluxes = {
            spec.metabolite: float(reactions[spec.metabolite].flux) for spec in specs
        }
        signed = {
            spec.metabolite: signed_target_flux(fluxes[spec.metabolite], spec.direction)
            for spec in specs
        }
        growth = float(floor.primal)
    return MultiTargetSolveResult(fluxes, signed, growth, "optimal")


def score_target_result(result: TargetMaxResult, spec: TargetSpec) -> float:
    """가중 점수(정규화 전 raw·weight). 모든 direction 에서 클수록 우수."""
    if result.status != "optimal":
        return float("-inf")
    return spec.weight * signed_target_flux(result.target_flux, spec.direction)


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
