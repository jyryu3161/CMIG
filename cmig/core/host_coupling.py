"""BiGG/explicit-map host coupling implementation.

The generic host inspection and lumen/blood host contract stay in :mod:`cmig.core.host`; this
module isolates the larger microbial-availability mapping and end-to-end MICOM orchestration.
"""

from __future__ import annotations

from typing import Any

from cmig.core.host import (
    BiggHostMicrobeResult,
    HostSolveResult,
    InterfaceFlux,
    _availability_flux,
    _bigg_exchange_id,
    _coupling_scale,
    _identified_points,
    _met_from_bigg_exchange,
    _uptake_fva_ranges,
)
from cmig.core.sign import Scope, convert

DEFAULT_BIGG_COUPLING_EXCLUDE = frozenset({"h", "h2o", "co2"})


def solve_bigg_host(
    host: Any,
    microbial_availability: dict[str, float],
    *,
    host_medium: dict[str, float] | None = None,
    interface_map: dict[str, str] | None = None,
    exchange_suffix: str = "_e",
    exclude_metabolites: set[str] | frozenset[str] | None = DEFAULT_BIGG_COUPLING_EXCLUDE,
    close_unlisted_uptake: bool = True,
    solver: str = "gurobi",
) -> HostSolveResult:
    """Solve a host GEM using microbial availability and an optional reviewed interface map."""
    from cobra.util.solver import linear_reaction_coefficients

    from cmig.core.namespace import _normalize_metabolite_id
    from cmig.core.single_model import _require_lp, set_model_solver

    _require_lp(solver)
    host_medium = host_medium or {}
    with host:
        set_model_solver(host, solver)
        exchange_reactions = list(host.exchanges)
        exchange_ids = {str(reaction.id) for reaction in exchange_reactions}
        normalized_interface: dict[str, str] = {}
        for raw_metabolite, raw_exchange in (interface_map or {}).items():
            key = _normalize_metabolite_id(str(raw_metabolite))
            exchange_id = str(raw_exchange)
            if exchange_id not in exchange_ids:
                raise ValueError(
                    f"interface map host exchange not found: {raw_metabolite} -> {exchange_id}"
                )
            prior = normalized_interface.setdefault(key, exchange_id)
            if prior != exchange_id:
                raise ValueError(
                    f"conflicting interface map for {raw_metabolite}: {prior}, {exchange_id}"
                )

        def exchange_for(key: str) -> str:
            if key in exchange_ids:
                return key
            normalized = _normalize_metabolite_id(key)
            return normalized_interface.get(
                normalized, _bigg_exchange_id(normalized, suffix=exchange_suffix)
            )

        host_exchange_to_metabolite = {
            exchange_id: metabolite
            for metabolite, exchange_id in normalized_interface.items()
        }
        if close_unlisted_uptake:
            for reaction in exchange_reactions:
                if reaction.lower_bound < 0:
                    reaction.lower_bound = 0.0

        exchange_availability: dict[str, float] = {}
        microbial_caps: dict[str, float] = {}
        background_caps: dict[str, float] = {}

        def add_availability(key: str, value: float, *, label: str) -> tuple[str | None, float]:
            reaction_id = exchange_for(key)
            flux = _availability_flux(value, label=label)
            if reaction_id in exchange_ids:
                exchange_availability[reaction_id] = (
                    exchange_availability.get(reaction_id, 0.0) + flux
                )
                return reaction_id, flux
            return None, flux

        for key, value in host_medium.items():
            reaction_id, flux = add_availability(
                str(key), value, label=f"host_medium[{key!r}]"
            )
            if reaction_id is not None:
                metabolite = _normalize_metabolite_id(str(key))
                background_caps[metabolite] = background_caps.get(metabolite, 0.0) + flux
        excluded = set(exclude_metabolites or set())
        matched: set[str] = set()
        for raw_metabolite, value in microbial_availability.items():
            metabolite = _normalize_metabolite_id(str(raw_metabolite))
            if metabolite in excluded:
                continue
            reaction_id, flux = add_availability(
                raw_metabolite,
                value,
                label=f"microbial_availability[{raw_metabolite!r}]",
            )
            if reaction_id is not None:
                microbial_caps[metabolite] = microbial_caps.get(metabolite, 0.0) + flux
                matched.add(metabolite)
        for reaction_id, availability in exchange_availability.items():
            host.reactions.get_by_id(reaction_id).lower_bound = -availability

        solution = host.optimize()
        status = "no_solution" if solution is None else str(solution.status)
        if status != "optimal":
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diagnostic = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"host LP non-optimal under microbial coupling (status={status})",
            )])
            return HostSolveResult(False, status, 0.0, [], {}, diagnostic)

        fluxes = {str(reaction_id): float(value) for reaction_id, value in solution.fluxes.items()}
        coefficients = linear_reaction_coefficients(host)
        objective_value = sum(
            float(coefficient) * fluxes.get(reaction.id, 0.0)
            for reaction, coefficient in coefficients.items()
        )
        total_ranges = _uptake_fva_ranges(
            host, [exchange_for(metabolite) for metabolite in sorted(matched)]
        )
        microbial_ranges: dict[str, tuple[float, float]] = {}
        for metabolite in sorted(matched):
            reaction_id = exchange_for(metabolite)
            total_lower, total_upper = total_ranges.get(reaction_id, (0.0, 0.0))
            microbial_cap = microbial_caps.get(metabolite, 0.0)
            lower = min(
                microbial_cap,
                max(0.0, total_lower - background_caps.get(metabolite, 0.0)),
            )
            upper = min(microbial_cap, total_upper)
            microbial_ranges[metabolite] = (lower, max(lower, upper))
        lumen_uptake = _identified_points(microbial_ranges)
        interface_fluxes: list[InterfaceFlux] = []
        for reaction_id in sorted(exchange_ids):
            flux = fluxes.get(reaction_id, 0.0)
            signed = convert(flux, Scope.ENVIRONMENT)
            if signed.label is None:
                continue
            metabolite = host_exchange_to_metabolite.get(
                reaction_id,
                _met_from_bigg_exchange(reaction_id, suffix=exchange_suffix),
            )
            interface_fluxes.append(
                InterfaceFlux(
                    exchange_id=reaction_id,
                    interface="bigg_external",
                    metabolite=metabolite,
                    flux=flux,
                    label=signed.label.value,
                )
            )
        return HostSolveResult(
            viable=objective_value > 1e-9,
            status=status,
            biomass=objective_value,
            interface_fluxes=interface_fluxes,
            lumen_uptake=lumen_uptake,
            lumen_uptake_ranges=microbial_ranges,
        )


def run_bigg_host_microbe(
    taxonomy: Any,
    host: Any,
    *,
    microbial_biomass_gdw: float,
    host_biomass_gdw: float,
    biomass_basis_kind: str,
    biomass_basis_source: str,
    solver: str = "gurobi",
    tradeoff_f: float = 0.5,
    microbe_medium: Any | None = None,
    host_medium: dict[str, float] | None = None,
    interface_map: dict[str, str] | None = None,
    exchange_suffix: str = "_e",
    exclude_metabolites: set[str] | frozenset[str] | None = DEFAULT_BIGG_COUPLING_EXCLUDE,
    close_unlisted_host_uptake: bool = True,
    engine: Any = None,
) -> BiggHostMicrobeResult:
    """MICOM community secretion to reviewed-map/BiGG host coupling."""
    from cmig.core.engine import MicomEngine
    from cmig.core.host_impact import host_impact
    from cmig.core.namespace import _normalize_metabolite_id

    community_engine = engine if engine is not None else MicomEngine()
    scale = _coupling_scale(
        microbial_biomass_gdw,
        host_biomass_gdw,
        basis_kind=biomass_basis_kind,
        basis_source=biomass_basis_source,
    )
    community = community_engine.build_community(taxonomy, cmig_solver=solver)
    if microbe_medium is not None:
        from cmig.core.medium_spec import apply_medium_checked

        apply_medium_checked(community, microbe_medium, strict=True)
    community_result = community_engine.cooperative_tradeoff(
        community, tradeoff_f, cmig_solver=solver
    )
    if community_result.status != "optimal":
        host_result = HostSolveResult(
            False, community_result.status, 0.0, [], {}, community_result.diagnostic
        )
        return BiggHostMicrobeResult(
            community_status=community_result.status,
            community_growth=community_result.objective,
            microbial_secretion={},
            member_secretion={},
            matched_exchanges={},
            unmatched_metabolites=[],
            host_result=host_result,
            impact=host_impact({}, host_result),
            warnings=(
                ["biomass basis is validation-only; result is not publication-ready"]
                if scale.basis_kind == "validation" else []
            ) + [
                f"microbial community solve was not optimal (status={community_result.status})"
            ] + list(getattr(community_result, "warnings", []) or []),
            coupling_scale=scale,
        )
    community_secretion = {
        metabolite: flux
        for metabolite, flux in community_result.external_exchange.items()
        if flux > 1e-6
    }
    secretion = {
        metabolite: flux * scale.microbe_to_host_ratio
        for metabolite, flux in community_secretion.items()
    }
    missing_abundances = [
        member
        for member in community_result.member_exchange
        if community_result.abundances.get(member) is None
    ]
    if missing_abundances:
        raise ValueError(
            f"member abundance missing; cannot scale host attribution: {missing_abundances}"
        )
    abundances = {
        member: float(abundance)
        for member, abundance in community_result.abundances.items()
        if abundance is not None
    }
    member_secretion = {
        member: {
            metabolite: flux * abundances[member] * scale.microbe_to_host_ratio
            for metabolite, flux in exchange.items()
            if flux > 1e-6
        }
        for member, exchange in community_result.member_exchange.items()
    }
    excluded = set(exclude_metabolites or set())
    exchange_ids = {str(reaction.id) for reaction in host.exchanges}
    normalized_interface = {
        _normalize_metabolite_id(metabolite): str(exchange)
        for metabolite, exchange in (interface_map or {}).items()
    }

    def host_exchange_for(metabolite: str) -> str:
        return normalized_interface.get(
            _normalize_metabolite_id(metabolite),
            _bigg_exchange_id(metabolite, suffix=exchange_suffix),
        )

    matched = {
        metabolite: host_exchange_for(metabolite)
        for metabolite in secretion
        if metabolite not in excluded and host_exchange_for(metabolite) in exchange_ids
    }
    unmatched = sorted(set(secretion) - set(matched) - excluded)
    host_result = solve_bigg_host(
        host,
        secretion,
        host_medium=host_medium,
        interface_map=interface_map,
        exchange_suffix=exchange_suffix,
        exclude_metabolites=exclude_metabolites,
        close_unlisted_uptake=close_unlisted_host_uptake,
        solver=solver,
    )
    warnings: list[str] = []
    if scale.basis_kind == "validation":
        warnings.append(
            "biomass basis is validation-only; result is not publication-ready"
        )
    # B6: host LP 실패는 최상위 요약에서 조용히 사라져서는 안 된다(status 파생 + warning 양쪽).
    if host_result.status != "optimal":
        warnings.append(
            f"host solve was not optimal (status={host_result.status}); "
            "the reported host objective is not a result"
        )
    # engine seam 은 duck-typed (engine: Any) — warnings 를 갖지 않는 double 도 허용한다.
    warnings.extend(getattr(community_result, "warnings", []) or [])
    excluded_present = sorted(set(secretion) & excluded)
    if excluded_present:
        warnings.append(f"excluded currency microbial secretions: {excluded_present}")
    if unmatched:
        warnings.append(f"unmatched microbial secretions: {unmatched}")
    if not matched:
        warnings.append("no microbial secretions matched host exchange ids")
    impact = host_impact(secretion, host_result)
    if impact.ambiguous_metabolites:
        warnings.append(
            "host transfer is not point-identifiable at the optimal objective for: "
            f"{impact.ambiguous_metabolites}; report FVA intervals"
        )
    if any(member_secretion.values()):
        warnings.append(
            "member contribution uses an abundance-weighted proportional allocation; "
            "it is not causal or uniquely identifiable"
        )
    return BiggHostMicrobeResult(
        community_status=community_result.status,
        community_growth=community_result.objective,
        microbial_secretion=secretion,
        member_secretion=member_secretion,
        matched_exchanges=matched,
        unmatched_metabolites=unmatched,
        host_result=host_result,
        impact=impact,
        warnings=warnings,
        community_secretion=community_secretion,
        coupling_scale=scale,
    )
