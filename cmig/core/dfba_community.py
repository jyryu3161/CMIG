"""Well-mixed dynamic FBA for a MICOM community.

The dynamic state is deliberately small: one biomass concentration per member and one
concentration per tracked metabolite in a shared extracellular pool.  MICOM is built once.  At
each time step its abundances and member-to-pool uptake bounds are rebound, the community is
solved, and the resulting per-member growth and exchange rates are integrated with explicit
Euler updates.

MICOM member exchange orientation depends on the source reaction. The shared-pool amount
coordinate is derived from its actual pool coefficient and member abundance. Consequently
``dS_m/dt = sum_i(q_i,m * X_i)``. Death and washout are intentionally out of scope for this
prototype; negative member growth is rejected rather than silently interpreted as death.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from cmig.core.engine import FLUX_REPORT_LABEL, MicomEngine, SolveResult

COMMUNITY_DFBA_LIMITATIONS = (
    "death and washout are out of scope; member biomass changes only through solved growth",
)
_FLUX_TOLERANCE = 1e-9


@dataclass(frozen=True)
class CommunityDfbaConfig:
    """Configuration for a future thin ``dfba-community`` CLI wrapper.

    Concentration keys are MICOM environmental exchanges (for example ``EX_glc__D_m``).
    ``member_vmax`` optionally overrides the maximum uptake rate for a member and tracked
    exchange.  Missing overrides use the community's initial environmental import limit when it
    is positive, otherwise the member pool-exchange limit.
    """

    t_end: float
    initial_concentrations: dict[str, float]
    initial_biomasses: dict[str, float]
    dt: float = 0.1
    km: float = 0.01
    member_vmax: dict[str, dict[str, float]] | None = None
    min_dt: float = 1e-4
    growth_floor: float = 1e-6
    tradeoff_fraction: float = 1.0
    close_untracked_uptake: bool = False

    def __post_init__(self) -> None:
        numeric = {
            "t_end": self.t_end,
            "dt": self.dt,
            "km": self.km,
            "min_dt": self.min_dt,
            "growth_floor": self.growth_floor,
            "tradeoff_fraction": self.tradeoff_fraction,
        }
        if any(
            isinstance(value, bool) or not math.isfinite(float(value))
            for value in numeric.values()
        ):
            raise ValueError("community dFBA numeric configuration must contain finite numbers")
        if self.t_end <= 0.0 or self.dt <= 0.0 or self.min_dt <= 0.0:
            raise ValueError("community dFBA t_end, dt, and min_dt must be > 0")
        if self.min_dt > self.dt:
            raise ValueError("community dFBA min_dt cannot exceed dt")
        if self.km < 0.0 or self.growth_floor < 0.0:
            raise ValueError("community dFBA km and growth_floor must be >= 0")
        if not 0.0 < self.tradeoff_fraction <= 1.0:
            raise ValueError("community dFBA tradeoff_fraction must satisfy 0 < fraction <= 1")
        if not self.initial_concentrations:
            raise ValueError("community dFBA requires at least one tracked concentration")
        if not self.initial_biomasses:
            raise ValueError("community dFBA requires at least one member biomass")
        self._validate_nonnegative_mapping(
            self.initial_concentrations, "initial concentration", positive=False
        )
        self._validate_nonnegative_mapping(
            self.initial_biomasses, "initial biomass", positive=True
        )
        for member, values in (self.member_vmax or {}).items():
            if not str(member).strip() or not values:
                raise ValueError(f"invalid community dFBA member_vmax member: {member!r}")
            self._validate_nonnegative_mapping(
                values, f"member_vmax for {member}", positive=False
            )

    @staticmethod
    def _validate_nonnegative_mapping(
        values: dict[str, float], label: str, *, positive: bool
    ) -> None:
        for key, value in values.items():
            invalid_value = (
                isinstance(value, bool)
                or not math.isfinite(float(value))
                or value < 0.0
                or (positive and value == 0.0)
            )
            if not str(key).strip() or invalid_value:
                comparison = "> 0" if positive else ">= 0"
                raise ValueError(
                    f"invalid community dFBA {label}: {key}={value}; values must be {comparison}"
                )


@dataclass(frozen=True)
class CommunityDfbaEvent:
    t: float
    kind: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommunityDfbaTimepoint:
    t: float
    member_biomasses: dict[str, float]
    member_growth_rates: dict[str, float]
    concentrations: dict[str, float]
    step_dt: float = 0.0
    member_exchange_fluxes: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class CommunityDfbaAcceptance:
    status_accepted: bool
    no_untracked_uptake: bool
    full_flux_at_every_step: bool
    concentrations_nonnegative: bool
    interpretable: bool
    not_interpretable_because: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommunityDfbaResult:
    timecourse: list[CommunityDfbaTimepoint]
    status: str
    acceptance: CommunityDfbaAcceptance
    diagnostic: str | None = None
    members: list[str] = field(default_factory=list)
    managed_exchanges: list[str] = field(default_factory=list)
    untracked_uptake: dict[str, float] = field(default_factory=dict)
    untracked_uptake_basis: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    events: list[CommunityDfbaEvent] = field(default_factory=list)
    community_build_seconds: float = 0.0
    step_solve_seconds: list[float] = field(default_factory=list)
    flux_report_statuses: list[str] = field(default_factory=list)
    limitations: tuple[str, ...] = COMMUNITY_DFBA_LIMITATIONS

    @property
    def mean_step_solve_seconds(self) -> float:
        if not self.step_solve_seconds:
            return 0.0
        return sum(self.step_solve_seconds) / len(self.step_solve_seconds)


def _exchange_metabolite(exchange_id: str, suffix: str = "_m") -> str:
    name = exchange_id[3:] if exchange_id.startswith("EX_") else exchange_id
    return name[: -len(suffix)] if name.endswith(suffix) else name


def _member_exchange_map(
    community: Any, tracked: list[str], members: list[str]
) -> dict[str, dict[str, list[Any]]]:
    """Map each tracked environmental exchange to its connected member reactions."""
    mapped: dict[str, dict[str, list[Any]]] = {}
    for exchange_id in tracked:
        try:
            external = community.reactions.get_by_id(exchange_id)
        except KeyError as error:
            raise ValueError(
                f"tracked community exchange does not exist: {exchange_id}"
            ) from error
        if external not in community.exchanges:
            raise ValueError(
                f"tracked reaction is not a MICOM environmental exchange: {exchange_id}"
            )
        if len(external.metabolites) != 1:
            raise ValueError(
                f"tracked MICOM exchange must contain one pool metabolite: {exchange_id}"
            )
        pool_metabolite = next(iter(external.metabolites))
        by_member: dict[str, list[Any]] = {}
        for reaction in pool_metabolite.reactions:
            member = getattr(reaction, "community_id", None)
            if not reaction.boundary and member in members:
                by_member.setdefault(str(member), []).append(reaction)
        mapped[exchange_id] = by_member
    return mapped


def _default_member_vmax(
    community: Any,
    exchange_id: str,
    member_reactions: list[Any],
    initial_medium: dict[str, float],
) -> float:
    from cmig.core.exchange import exchange_identity

    environmental_limit = float(initial_medium.get(exchange_id, 0.0))
    if environmental_limit > 0.0:
        external = exchange_identity(community.reactions.get_by_id(exchange_id))
        return environmental_limit * abs(external.coefficient)
    member = str(member_reactions[0].community_id)
    abundance = float(community.abundances[member])
    return sum(
        max(0.0, -coefficient * bound / abundance)
        for reaction in member_reactions
        for coefficient, bound in [_member_pool_supply_bound(reaction)]
    )


def _member_pool_supply_bound(reaction: Any) -> tuple[float, float]:
    """Pool coefficient and the raw bound in the pool-consuming direction."""
    pool = [
        float(coefficient)
        for met, coefficient in reaction.metabolites.items()
        if str(getattr(met, "compartment", "")) == "m"
    ]
    if (
        len(pool) != 1 or len(reaction.metabolites) != 2
        or not math.isfinite(pool[0]) or not pool[0]
    ):
        raise ValueError(f"unsupported MICOM member-pool exchange topology: {reaction.id}")
    coefficient = pool[0]
    bound = reaction.lower_bound if coefficient > 0 else reaction.upper_bound
    return coefficient, float(bound)


def _member_kinetic_constraints(
    community: Any,
    by_member: dict[str, list[Any]],
    abundances: dict[str, float],
    budgets: dict[str, float],
    *,
    index: int,
    nutrient_index: int,
) -> list[Any]:
    """One physical uptake budget across all channels, with secretion unconstrained."""
    added: list[Any] = []
    for member_index, (member, reactions) in enumerate(sorted(by_member.items())):
        auxiliaries: list[Any] = []
        for channel_index, reaction in enumerate(reactions):
            coefficient, _ = _member_pool_supply_bound(reaction)
            name = f"cmig_kin_{index}_{nutrient_index}_{member_index}_{channel_index}"
            uptake = community.problem.Variable(name, lb=0)
            # u >= -q, q=(c_pool/abundance)*v. Positive q is secretion.
            bound = community.problem.Constraint(
                uptake + coefficient / abundances[member] * reaction.flux_expression,
                lb=0,
                name=f"{name}_channel",
            )
            auxiliaries.append(uptake)
            added.extend((uptake, bound))
        if auxiliaries:
            added.append(
                community.problem.Constraint(
                    sum(auxiliaries), ub=budgets[member],
                    name=f"cmig_kin_{index}_{nutrient_index}_{member_index}_total",
                )
            )
    community.add_cons_vars(added)
    return added


def _validate_vmax_surface(
    config: CommunityDfbaConfig, members: list[str], tracked: list[str]
) -> None:
    member_extras = set(config.member_vmax or {}) - set(members)
    if member_extras:
        raise ValueError(
            f"community dFBA member_vmax has unknown members: {sorted(member_extras)}"
        )
    exchange_extras = {
        exchange
        for values in (config.member_vmax or {}).values()
        for exchange in values
        if exchange not in tracked
    }
    if exchange_extras:
        raise ValueError(
            "community dFBA member_vmax keys are not tracked exchanges: "
            f"{sorted(exchange_extras)}"
        )


def _acceptance(
    *,
    status: str,
    timecourse: list[CommunityDfbaTimepoint],
    untracked_uptake: dict[str, float],
    flux_report_statuses: set[str],
) -> CommunityDfbaAcceptance:
    status_accepted = status in {"completed", "stalled"}
    nonnegative = all(
        concentration >= -_FLUX_TOLERANCE
        for point in timecourse
        for concentration in point.concentrations.values()
    )
    full_flux = bool(flux_report_statuses) and flux_report_statuses == {"full"}
    reasons: list[str] = []
    if not status_accepted:
        reasons.append(f"community solve ended with status={status}")
    elif status == "stalled" and len(timecourse) == 1:
        reasons.append("the community stalled before producing any dynamics")
    if untracked_uptake:
        reasons.append(
            "growth used untracked, never-depleted environmental substrates; close or track "
            "those exchanges"
        )
    if not full_flux:
        labels = [FLUX_REPORT_LABEL.get(item, item) for item in sorted(flux_report_statuses)]
        reasons.append(f"not every integrated step had a full pFBA flux vector: {labels}")
    if not nonnegative:
        reasons.append("a tracked concentration became negative")
    return CommunityDfbaAcceptance(
        status_accepted=status_accepted,
        no_untracked_uptake=not untracked_uptake,
        full_flux_at_every_step=full_flux,
        concentrations_nonnegative=nonnegative,
        interpretable=not reasons,
        not_interpretable_because=reasons,
    )


def _untracked_warning(untracked_uptake: dict[str, float], tracked: list[str]) -> str:
    ranked = sorted(untracked_uptake.items(), key=lambda item: (-item[1], item[0]))[:8]
    details = ", ".join(f"{exchange} (max {rate:.3g})" for exchange, rate in ranked)
    return (
        f"growth used {len(untracked_uptake)} UNTRACKED environmental substrates outside "
        f"{sorted(tracked)}: {details}. These pools have no concentration and are never "
        "depleted, so the community dFBA trajectory is NOT interpretable. Re-run with "
        "close_untracked_uptake=True or track those exchanges."
    )


def _finish_result(
    *,
    timecourse: list[CommunityDfbaTimepoint],
    status: str,
    diagnostic: str | None,
    members: list[str],
    tracked: list[str],
    untracked_uptake: dict[str, float],
    warnings: list[str],
    events: list[CommunityDfbaEvent],
    build_seconds: float,
    solve_seconds: list[float],
    flux_report_statuses: set[str],
) -> CommunityDfbaResult:
    if untracked_uptake:
        warnings.append(_untracked_warning(untracked_uptake, tracked))
    acceptance = _acceptance(
        status=status,
        timecourse=timecourse,
        untracked_uptake=untracked_uptake,
        flux_report_statuses=flux_report_statuses,
    )
    return CommunityDfbaResult(
        timecourse=timecourse,
        status=status,
        acceptance=acceptance,
        diagnostic=diagnostic,
        members=members,
        managed_exchanges=tracked,
        untracked_uptake=untracked_uptake,
        untracked_uptake_basis={
            key: "member_biomass" if key.startswith("member:") else "community_biomass"
            for key in untracked_uptake
        },
        warnings=list(dict.fromkeys(warnings)),
        events=events,
        community_build_seconds=build_seconds,
        step_solve_seconds=solve_seconds,
        flux_report_statuses=sorted(flux_report_statuses),
    )


def _member_flux_keys(
    tracked_members: dict[str, dict[str, Any]]
) -> dict[str, dict[str, str]]:
    """tracked env exchange -> member -> key under which the engine reports that member's flux.

    ``SolveResult.member_exchange`` is keyed by ``_met_from_exchange(<member reaction id>, "_e")``
    (engine.py), i.e. by the *member's* exchange id, not by the environmental exchange id. The
    first cut guessed the key from the environmental id (``EX_glc__D_m`` -> ``glc__D``) and
    defaulted to 0.0 when the guess missed, so any member whose exchange is not literally
    ``EX_<met>_e`` grew on a pool that never depleted while ``member_exchange_fluxes`` said 0.
    """
    return {
        exchange_id: {
            # Engine normalizes the actual shared pool identity, independent of global_id.
            member: next(
                str(met.id)[:-2] for met in reactions[0].metabolites
                if str(getattr(met, "compartment", "")) == "m" and str(met.id).endswith("_m")
            )
            for member, reactions in by_member.items()
        }
        for exchange_id, by_member in tracked_members.items()
    }


def _solve_member_state(
    solution: SolveResult,
    members: list[str],
    tracked_members: dict[str, dict[str, list[Any]]],
    tracked_metabolites: dict[str, dict[str, str]],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    growth: dict[str, float] = {}
    member_fluxes: dict[str, dict[str, float]] = {member: {} for member in members}
    for member in members:
        value = solution.member_growth.get(member)
        if value is None or not math.isfinite(float(value)):
            raise ValueError(f"MICOM solution omitted finite growth for member {member}")
        if value < -_FLUX_TOLERANCE:
            raise ValueError(
                f"MICOM returned negative growth for {member}; death is not modeled"
            )
        growth[member] = max(0.0, float(value))
        reported = solution.member_exchange.get(member, {})
        for exchange_id, by_member in tracked_members.items():
            if member not in by_member:
                # This member has no reaction on the tracked pool metabolite: its flux is 0
                # by construction, not by a missing report.
                member_fluxes[member][exchange_id] = 0.0
                continue
            key = tracked_metabolites[exchange_id][member]
            if key not in reported:
                raise ValueError(
                    f"MICOM solution did not report {exchange_id} for member {member} "
                    f"(expected member exchange key {key!r})"
                )
            value = reported[key]
            if not math.isfinite(float(value)):
                raise ValueError(
                    f"MICOM solution omitted finite {exchange_id} flux for member {member}"
                )
            member_fluxes[member][exchange_id] = float(value)
    return growth, member_fluxes


def run_community_dfba(
    taxonomy: Any,
    config: CommunityDfbaConfig,
    *,
    solver: str = "gurobi",
) -> CommunityDfbaResult:
    """Run deterministic, well-mixed community dFBA using MICOM's public solve surface.

    The MICOM community is constructed exactly once.  ``community_build_seconds`` and every
    per-step solve duration are returned as operational measurements; wall-clock timings never
    affect the scientific trajectory.
    """
    if solver != "gurobi":
        raise ValueError(
            "community dFBA currently requires gurobi because concentration integration needs "
            "a full member-level pFBA flux vector"
        )

    engine = MicomEngine()
    build_started = perf_counter()
    community: Any = engine.build_community(taxonomy, cmig_solver=solver)
    build_seconds = perf_counter() - build_started

    members = sorted(str(member) for member in community.taxa)
    configured_members = set(config.initial_biomasses)
    if configured_members != set(members):
        raise ValueError(
            "community dFBA initial_biomasses must match taxonomy members exactly; "
            f"missing={sorted(set(members) - configured_members)}, "
            f"unknown={sorted(configured_members - set(members))}"
        )
    tracked = list(config.initial_concentrations)
    _validate_vmax_surface(config, members, tracked)
    initial_total = sum(config.initial_biomasses.values())
    community.set_abundance({
        member: config.initial_biomasses[member] / initial_total for member in members
    })
    tracked_members = _member_exchange_map(community, tracked, members)
    tracked_metabolites = _member_flux_keys(tracked_members)
    initial_medium = {
        str(exchange): float(value) for exchange, value in community.medium.items()
    }

    vmax: dict[str, dict[str, float]] = {member: {} for member in members}
    for exchange_id, by_member in tracked_members.items():
        for member, reactions in by_member.items():
            override = (config.member_vmax or {}).get(member, {}).get(exchange_id)
            vmax[member][exchange_id] = (
                float(override)
                if override is not None
                else _default_member_vmax(
                    community, exchange_id, reactions, initial_medium
                )
            )

    from cmig.core.boundary import close_boundary_supply

    environmental_ids = {str(reaction.id) for reaction in community.exchanges}
    closed_untracked: list[str] = []
    if config.close_untracked_uptake:
        closure = close_boundary_supply(community, keep=tracked)
        if closure.forced_supply:
            raise ValueError(
                "community boundary isolation cannot close forced undeclared suppliers: "
                f"{closure.forced_supply}"
            )
        closed_untracked = list(closure.closed)

    concentrations = dict(config.initial_concentrations)
    biomasses = dict(config.initial_biomasses)
    timecourse = [
        CommunityDfbaTimepoint(
            t=0.0,
            member_biomasses=dict(biomasses),
            member_growth_rates={member: 0.0 for member in members},
            concentrations=dict(concentrations),
        )
    ]
    warnings: list[str] = []
    if closed_untracked:
        warnings.append(
            f"closed {len(closed_untracked)} untracked environmental uptake exchanges before "
            "integrating"
        )
    events: list[CommunityDfbaEvent] = []
    untracked_uptake: dict[str, float] = {}
    solve_seconds: list[float] = []
    flux_report_statuses: set[str] = set()
    t = 0.0
    step_index = 0
    kinetic_constraints: list[Any] = []

    while t < config.t_end - 1e-12:
        if kinetic_constraints:
            community.remove_cons_vars(kinetic_constraints)
            kinetic_constraints = []
        total_biomass = sum(biomasses.values())
        abundances = {member: biomasses[member] / total_biomass for member in members}
        community.set_abundance(abundances)

        for nutrient_index, (exchange_id, by_member) in enumerate(tracked_members.items()):
            concentration = max(concentrations[exchange_id], 0.0)
            weighted_capacity = 0.0
            budgets: dict[str, float] = {}
            for member in by_member:
                maximum = vmax[member][exchange_id]
                uptake = (
                    maximum * concentration / (config.km + concentration)
                    if concentration > 0.0
                    else 0.0
                )
                budgets[member] = uptake
                weighted_capacity += abundances[member] * uptake
            kinetic_constraints.extend(_member_kinetic_constraints(
                community, by_member, abundances, budgets,
                index=step_index, nutrient_index=nutrient_index,
            ))
            from cmig.core.exchange import exchange_identity

            external = community.reactions.get_by_id(exchange_id)
            exchange_identity(external).set_physical_uptake_limit(
                external, weighted_capacity
            )
        step_index += 1

        solve_started = perf_counter()
        solution = engine.cooperative_tradeoff(
            community, config.tradeoff_fraction, cmig_solver=solver
        )
        solve_seconds.append(perf_counter() - solve_started)
        flux_report_statuses.add(solution.flux_report_status)
        warnings.extend(solution.warnings)
        if solution.status != "optimal":
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="solver_failure",
                    message=f"MICOM status={solution.status}; integration stopped",
                    details={"status": solution.status},
                )
            )
            return _finish_result(
                timecourse=timecourse,
                status=solution.status,
                diagnostic=solution.diagnostic or f"MICOM status={solution.status} at t={t:.6g}",
                members=members,
                tracked=tracked,
                untracked_uptake=untracked_uptake,
                warnings=warnings,
                events=events,
                build_seconds=build_seconds,
                solve_seconds=solve_seconds,
                flux_report_statuses=flux_report_statuses,
            )

        try:
            growth_rates, member_fluxes = _solve_member_state(
                solution, members, tracked_members, tracked_metabolites
            )
        except ValueError as error:
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="solution_readout_failure",
                    message=str(error),
                )
            )
            return _finish_result(
                timecourse=timecourse,
                status="solver_failed",
                diagnostic=str(error),
                members=members,
                tracked=tracked,
                untracked_uptake=untracked_uptake,
                warnings=warnings,
                events=events,
                build_seconds=build_seconds,
                solve_seconds=solve_seconds,
                flux_report_statuses=flux_report_statuses,
            )

        new_untracked: dict[str, float] = {}
        if not solution.boundary_supply_complete:
            return _finish_result(
                timecourse=timecourse, status="solver_failed",
                diagnostic="MICOM solution lacks a complete boundary-supply readout",
                members=members, tracked=tracked, untracked_uptake=untracked_uptake,
                warnings=warnings, events=events, build_seconds=build_seconds,
                solve_seconds=solve_seconds, flux_report_statuses=flux_report_statuses,
            )
        for reaction_id, uptake in solution.boundary_supply.items():
            if reaction_id in tracked:
                continue
            # Preserve the reaction identity and biomass basis. Member sinks and environment
            # exchanges are never summed as if they shared a biomass denominator.
            key = reaction_id if reaction_id in environmental_ids else "member:" + reaction_id
            if uptake > untracked_uptake.get(key, 0.0):
                untracked_uptake[key] = uptake
                new_untracked[key] = uptake
        if new_untracked:
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="untracked_uptake",
                    message="untracked environmental uptake makes the trajectory uninterpretable",
                    details={"uptake": new_untracked},
                )
            )

        if max(growth_rates.values(), default=0.0) <= config.growth_floor:
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="stalled",
                    message="all member growth rates were at or below growth_floor",
                    details={"growth_rates": growth_rates},
                )
            )
            return _finish_result(
                timecourse=timecourse,
                status="stalled",
                diagnostic=None,
                members=members,
                tracked=tracked,
                untracked_uptake=untracked_uptake,
                warnings=warnings,
                events=events,
                build_seconds=build_seconds,
                solve_seconds=solve_seconds,
                flux_report_statuses=flux_report_statuses,
            )

        concentration_rates = {
            exchange_id: sum(
                member_fluxes[member][exchange_id] * biomasses[member]
                for member in members
            )
            for exchange_id in tracked
        }
        requested_dt = min(config.dt, config.t_end - t)
        step_dt = requested_dt
        growth_scale = 1.0
        proposed = {
            exchange_id: concentrations[exchange_id]
            + concentration_rates[exchange_id] * step_dt
            for exchange_id in tracked
        }
        while (
            any(value < -_FLUX_TOLERANCE for value in proposed.values())
            and step_dt / 2.0 >= min(config.min_dt, config.t_end - t)
        ):
            step_dt /= 2.0
            proposed = {
                exchange_id: concentrations[exchange_id]
                + concentration_rates[exchange_id] * step_dt
                for exchange_id in tracked
            }
        if any(value < -_FLUX_TOLERANCE for value in proposed.values()):
            step_dt = min(config.min_dt, config.t_end - t)
            fractions = []
            for exchange_id, rate in concentration_rates.items():
                # Only genuine consumption limits the step. A depleted pool sits at a bound of
                # -0.0 where a basic variable can legally read -1e-12 (solver feasibility
                # tolerance); counting that as "required" mass gave 0/1e-15 = 0 and froze the
                # whole community on numerical noise.
                if rate >= -_FLUX_TOLERANCE:
                    continue
                required = -rate * step_dt
                if required > 0.0:
                    fractions.append(
                        max(0.0, min(1.0, concentrations[exchange_id] / required))
                    )
            growth_scale = min(fractions) if fractions else 1.0
            proposed = {
                exchange_id: max(
                    0.0,
                    concentrations[exchange_id]
                    + concentration_rates[exchange_id] * step_dt * growth_scale,
                )
                for exchange_id in tracked
            }
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="nonnegativity_clamp",
                    message="scaled growth and exchange fluxes to available shared-pool mass",
                    details={"step_dt": step_dt, "scale": growth_scale},
                )
            )
        if step_dt < requested_dt and growth_scale == 1.0:
            limiting = [
                exchange_id
                for exchange_id, rate in concentration_rates.items()
                if concentrations[exchange_id] + rate * requested_dt < -_FLUX_TOLERANCE
            ]
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="adaptive_dt",
                    message="halved the integration step to preserve shared-pool non-negativity",
                    details={
                        "requested_dt": requested_dt,
                        "accepted_dt": step_dt,
                        "limiting_exchanges": limiting,
                    },
                )
            )

        effective_growth = {
            member: growth_rates[member] * growth_scale for member in members
        }
        effective_fluxes = {
            member: {
                exchange_id: flux * growth_scale
                for exchange_id, flux in member_fluxes[member].items()
            }
            for member in members
        }
        roundoff_clamps = {
            exchange_id: value for exchange_id, value in proposed.items() if value < 0.0
        }
        if roundoff_clamps:
            events.append(
                CommunityDfbaEvent(
                    t=t,
                    kind="roundoff_nonnegativity_clamp",
                    message="clamped tolerance-scale negative concentrations to zero",
                    details={"pre_clamp_concentrations": roundoff_clamps},
                )
            )
        concentrations = {
            exchange_id: max(0.0, value) for exchange_id, value in proposed.items()
        }
        biomasses = {
            member: biomasses[member]
            + effective_growth[member] * biomasses[member] * step_dt
            for member in members
        }
        t += step_dt
        timecourse.append(
            CommunityDfbaTimepoint(
                t=t,
                member_biomasses=dict(biomasses),
                member_growth_rates=effective_growth,
                concentrations=dict(concentrations),
                step_dt=step_dt,
                member_exchange_fluxes=effective_fluxes,
            )
        )

    return _finish_result(
        timecourse=timecourse,
        status="completed",
        diagnostic=None,
        members=members,
        tracked=tracked,
        untracked_uptake=untracked_uptake,
        warnings=warnings,
        events=events,
        build_seconds=build_seconds,
        solve_seconds=solve_seconds,
        flux_report_statuses=flux_report_statuses,
    )
