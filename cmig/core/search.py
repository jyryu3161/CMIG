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
from dataclasses import dataclass, field
from typing import Any

from cmig.core.search_constraints import GrowthPolicy, apply_member_growth, member_measurements
from cmig.core.search_profile import timed


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
    member_growth: dict[str, float] = field(default_factory=dict)
    abundances: dict[str, float] = field(default_factory=dict)


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
    # B3: community 에 exchange 가 없는 target — flux 0 으로 기여하고 여기에 기록된다
    # (하나가 없다고 consortium 전체를 랭킹에서 탈락시키지 않는다).
    missing_targets: tuple[str, ...] = ()
    member_growth: dict[str, float] = field(default_factory=dict)
    abundances: dict[str, float] = field(default_factory=dict)


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


#: μ_c* at or below this is numerically no growth (same floor as ``sign.NOISE_FLOOR``). A
#: consortium at zero growth still has a feasible fermentation vertex, so the target LP returns
#: `optimal` with a positive flux and a growth floor of ``growth_fraction * 0 == 0`` — a ranking
#: built on that says "best producer" about a community that does not grow. Observed on a real
#: AGORA2 pool held on a defined diet that lacked the strains' required lipids and quinones:
#: every candidate reported non-zero butyrate at exactly zero growth.
NON_VIABLE_GROWTH = 1e-6


@timed("target_lp")
def _optimize_target(community: Any) -> Any:
    return community.optimize()


@timed("baseline")
def _community_growth_star(community: Any) -> float:
    """μ_c* = 최대 community growth. target-max growth floor 의 기준값."""
    sol = community.optimize()
    if sol is None:
        raise ValueError("community maximum-growth solve returned no solution")
    if str(sol.status) != "optimal":
        raise ValueError(f"community maximum-growth solve status={sol.status}")
    gr = getattr(sol, "growth_rate", None)
    if gr is None:
        gr = sol.objective_value
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
    growth_policy: GrowthPolicy | None = None,
) -> TargetMaxResult:
    """target-max: max(target exchange) s.t. community growth ≥ growth_fraction·μ_c* (R-OBJ).

    mu_community 는 μ_c* 값이다. None 이면 growth-only LP 로 μ_c*를 먼저
    산출한다. gurobi(LP) 전제.
    """
    from cmig.core.single_model import _require_lp, set_model_solver
    _validate_growth_floor(growth_fraction, mu_community)
    policy = growth_policy or GrowthPolicy()
    policy.validate()
    if not math.isfinite(spec.weight) or spec.weight < 0.0:
        raise ValueError("target weight must be finite and non-negative")
    _require_lp(solver)
    ex_id = spec.exchange_id()
    with community as m:
        set_model_solver(m, solver)
        apply_member_growth(m, policy)
        if mu_community is None:
            try:
                mu_community = _community_growth_star(m)
            except ValueError as e:
                from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

                diag = diagnostic_from_parts([(DiagnosticCode.INFEASIBLE, str(e))])
                return TargetMaxResult(
                    ex_id, spec.direction.value, 0.0, 0.0, "baseline_failed", diag
                )
        if mu_community <= NON_VIABLE_GROWTH:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"community maximum growth is {mu_community:.3g} (<= {NON_VIABLE_GROWTH:g}): the "
                "consortium cannot grow on this medium, so the growth floor is vacuous and any "
                "target flux is a no-growth fermentation vertex, not production. Check the "
                "medium with `cmig medium-gap`",
            )])
            return TargetMaxResult(
                ex_id, spec.direction.value, 0.0, mu_community, "non_viable", diag
            )
        if ex_id not in {r.id for r in m.reactions}:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.CAPABILITY_MISSING,
                f"target exchange absent from the community: {ex_id}")])
            return TargetMaxResult(ex_id, spec.direction.value, 0.0, 0.0, "missing", diag)
        growth_expr = m.objective.expression                      # community growth 식
        floor = m.problem.Constraint(
            growth_expr, lb=max(growth_fraction * mu_community, policy.min_community_growth),
            name="cmig_growth_floor")
        rxn = m.reactions.get_by_id(ex_id)
        domain = _target_domain_constraint(m, rxn, spec.direction, "cmig_target_sign_domain")
        m.add_cons_vars([floor, domain])
        m.solver.update()
        m.objective = rxn
        m.objective.direction = target_objective_direction(spec.direction)
        sol = _optimize_target(m)
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
        member_growth, abundances = member_measurements(m) if status == "optimal" else ({}, {})
    diagnostic = None if status == "optimal" else f"target LP status={status}"
    return TargetMaxResult(
        ex_id, spec.direction.value, flux, growth, status, diagnostic, member_growth, abundances,
    )


def epsilon_constrained_solve(
    community: Any,
    specs: list[TargetSpec],
    floors: dict[str, float],
    *,
    normalization_scales: dict[str, float],
    growth_fraction: float = 0.5,
    mu_community: float | None = None,
    solver: str = "gurobi",
    growth_policy: GrowthPolicy | None = None,
) -> MultiTargetSolveResult:
    """Joint solve with epsilon lower bounds on direction-adjusted (larger-is-better) values.

    Secretion/uptake domains are enforced independently of utility. A negative
    epsilon for a minimisation target bounds its physical magnitude from above;
    an omitted epsilon adds no utility constraint. Sweeps sample achievable
    trade-offs, but a finite grid does not certify the complete Pareto front.
    """
    from cmig.core.single_model import _require_lp, set_model_solver

    _validate_growth_floor(growth_fraction, mu_community)
    _validate_multi_targets(specs, normalization_scales)
    if set(floors) - {spec.metabolite for spec in specs}:
        raise ValueError("epsilon bounds contain an unknown target")
    if any(not math.isfinite(value) for value in floors.values()):
        raise ValueError("epsilon bounds must be finite signed target values")
    policy = growth_policy or GrowthPolicy()
    policy.validate()
    _require_lp(solver)
    with community as model:
        set_model_solver(model, solver)
        apply_member_growth(model, policy)
        if mu_community is None:
            try:
                mu_community = _community_growth_star(model)
            except ValueError as e:
                return MultiTargetSolveResult({}, {}, 0.0, "baseline_failed", str(e))
        if mu_community <= NON_VIABLE_GROWTH:
            return _non_viable_multi(mu_community)
        present_specs = [spec for spec in specs if spec.exchange_id() in model.reactions]
        missing_metabolites = tuple(
            spec.metabolite for spec in specs if spec.exchange_id() not in model.reactions
        )
        if any(floors.get(metabolite, 0.0) > 0 for metabolite in missing_metabolites):
            return MultiTargetSolveResult(
                {}, {}, 0.0, "infeasible", "positive epsilon for a missing exchange",
                missing_metabolites,
            )
        if not present_specs:
            return MultiTargetSolveResult(
                {spec.metabolite: 0.0 for spec in specs},
                {spec.metabolite: 0.0 for spec in specs},
                0.0, "missing", "no target exchange present", missing_metabolites,
            )
        growth_expr = model.objective.expression
        constraints = [model.problem.Constraint(
            growth_expr, lb=max(growth_fraction * mu_community, policy.min_community_growth),
            name="cmig_eps_growth_floor"
        )]
        objective = 0
        reactions: dict[str, Any] = {}
        for index, spec in enumerate(present_specs):
            reaction = model.reactions.get_by_id(spec.exchange_id())
            reactions[spec.metabolite] = reaction
            sign = 1.0 if spec.direction in (
                Direction.MAX_SECRETION, Direction.MIN_UPTAKE
            ) else -1.0
            constraints.append(_target_domain_constraint(
                model, reaction, spec.direction, f"cmig_eps_domain_{index}",
            ))
            # Bounds are on the larger-is-better axis. For a minimisation target,
            # a negative bound -u means physical magnitude <= u. An omitted bound
            # imposes only the physical sign domain, not an implicit zero ceiling.
            if spec.metabolite in floors:
                constraints.append(model.problem.Constraint(
                    sign * reaction.flux_expression,
                    lb=float(floors[spec.metabolite]),
                    name=f"cmig_eps_floor_{index}",
                ))
            scale = normalization_scales[spec.metabolite]
            objective += (spec.weight / scale) * sign * reaction.flux_expression
        model.add_cons_vars(constraints)
        model.objective = model.problem.Objective(objective, direction="max")
        model.solver.update()
        solution = _optimize_target(model)
        status = "solver_no_solution" if solution is None else str(solution.status)
        if status != "optimal":
            return MultiTargetSolveResult(
                {}, {}, 0.0, status,
                f"epsilon-constrained LP status={status}", missing_metabolites,
            )
        fluxes = {
            spec.metabolite: (
                float(reactions[spec.metabolite].flux) if spec.metabolite in reactions else 0.0
            )
            for spec in specs
        }
        signed = {
            spec.metabolite: signed_target_flux(fluxes[spec.metabolite], spec.direction)
            for spec in specs
        }
        growth = float(constraints[0].primal)
        member_growth, abundances = member_measurements(model)
    return MultiTargetSolveResult(
        fluxes, signed, growth, "optimal", None, missing_metabolites, member_growth, abundances,
    )


def _non_viable_multi(mu_community: float) -> MultiTargetSolveResult:
    return MultiTargetSolveResult(
        {}, {}, mu_community, "non_viable",
        f"community maximum growth is {mu_community:.3g} (<= {NON_VIABLE_GROWTH:g}); "
        "check the medium with `cmig medium-gap`",
    )


def _validate_multi_targets(specs: list[TargetSpec], scales: dict[str, float]) -> None:
    if len(specs) < 2:
        raise ValueError("multi-target solve requires at least two targets")
    if len({spec.metabolite for spec in specs}) != len(specs):
        raise ValueError("multi-target metabolites must be unique")
    if any(not math.isfinite(spec.weight) or spec.weight < 0 for spec in specs):
        raise ValueError("multi-target weights must be finite and non-negative")
    if not any(spec.weight > 0 for spec in specs):
        raise ValueError("at least one multi-target weight must be positive")
    for spec in specs:
        value = scales.get(spec.metabolite)
        if value is None or not math.isfinite(value) or value <= 0:
            raise ValueError(f"normalization scale for {spec.metabolite!r} must be finite and > 0")


def joint_target_solve(
    community: Any,
    specs: list[TargetSpec],
    *,
    normalization_scales: dict[str, float],
    growth_fraction: float = 0.5,
    mu_community: float | None = None,
    solver: str = "gurobi",
    growth_policy: GrowthPolicy | None = None,
) -> MultiTargetSolveResult:
    """Optimize all targets in one LP and return fluxes from the same feasible solution.

    The objective is ``sum(weight * signed_flux / scale)``. Observed-range offsets are constants
    and therefore do not affect the optimizer; callers apply them when reporting normalized
    scores. Every direction receives an explicit secretion/uptake sign-domain constraint.
    """
    from cmig.core.single_model import _require_lp, set_model_solver

    _validate_growth_floor(growth_fraction, mu_community)
    policy = growth_policy or GrowthPolicy()
    policy.validate()
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
        apply_member_growth(model, policy)
        if mu_community is None:
            try:
                mu_community = _community_growth_star(model)
            except ValueError as e:
                return MultiTargetSolveResult({}, {}, 0.0, "baseline_failed", str(e))
        if mu_community <= NON_VIABLE_GROWTH:
            return _non_viable_multi(mu_community)
        # B3: 개별 target 의 exchange 부재는 "그 대사체를 만들 수 없다"(flux 0)는 정보이지
        # consortium 을 평가 불가로 만드는 사유가 아니다. 존재하는 target 만 목적식에 넣고,
        # 부재 target 은 0 으로 보고한다. 전부 부재일 때만 평가할 것이 없어 status="missing".
        present_specs = [spec for spec in specs if spec.exchange_id() in model.reactions]
        missing_metabolites = tuple(
            spec.metabolite for spec in specs if spec.exchange_id() not in model.reactions
        )
        if not present_specs:
            return MultiTargetSolveResult(
                {spec.metabolite: 0.0 for spec in specs},
                {spec.metabolite: 0.0 for spec in specs},
                0.0,
                "missing",
                "target exchanges absent: "
                f"{sorted(spec.exchange_id() for spec in specs)}",
                missing_metabolites,
            )

        growth_expr = model.objective.expression
        floor = model.problem.Constraint(
            growth_expr,
            lb=max(growth_fraction * mu_community, policy.min_community_growth),
            name="cmig_multi_growth_floor",
        )
        constraints = [floor]
        objective = 0
        reactions: dict[str, Any] = {}
        for index, spec in enumerate(present_specs):
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
        solution = _optimize_target(model)
        if solution is None:
            solver_status = getattr(model.solver, "status", None)
            status = str(solver_status) if solver_status else "solver_no_solution"
            return MultiTargetSolveResult(
                {}, {}, 0.0, status,
                f"joint target LP returned no solution object (solver_status={status})",
                missing_metabolites,
            )
        status = str(solution.status)
        if status != "optimal":
            return MultiTargetSolveResult(
                {}, {}, 0.0, status, f"joint target LP status={status}", missing_metabolites
            )
        # 부재 target 은 0.0 — 실제 flux vector 와 같은 해석(만들 수 없음)을 갖는다.
        fluxes = {
            spec.metabolite: (
                float(reactions[spec.metabolite].flux) if spec.metabolite in reactions else 0.0
            )
            for spec in specs
        }
        signed = {
            spec.metabolite: signed_target_flux(fluxes[spec.metabolite], spec.direction)
            for spec in specs
        }
        growth = float(floor.primal)
        member_growth, abundances = member_measurements(model)
    return MultiTargetSolveResult(
        fluxes, signed, growth, "optimal", None, missing_metabolites, member_growth, abundances,
    )


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
