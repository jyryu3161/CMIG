"""Host-Microbe core — HostModel · 2-interface sign · viability 제약 (Roadmap Phase 3.1, §12).

Design Ref: §12 (Host-Microbe) / cmig-host.design. Plan SC: SC-HM1~HM6.

[config B 확정] micom 0.39.0 Community 는 host 파라미터 없음(probe) → MICOM-native host 불가 →
**CMIG 2-compartment post-process**: 미생물 community solve → lumen 가용 대사체 → host(cobra) 를
lumen uptake 한계로 풀되 **viability 제약(ATP maintenance ≥ 임계, host 는 군집 성장 목적 미포함)**.

2-interface: lumen(장관, 미생물 공유) vs blood(전신). reviewed map, compartment,
annotation/metadata and the historical id suffix are evidence; sign.convert is the one direction
entry point. cobra 위임(자체 LP 미구현).
"""

from __future__ import annotations

import time
import tracemalloc
from typing import Any

from cmig.core.host_types import (
    BIOMASS_BASIS_KINDS,
    DEFAULT_BIGG_COUPLING_EXCLUDE,
    BiggHostMicrobeResult,
    CouplingScale,
    HostBenchmarkResult,
    HostInterface,
    HostModelSummary,
    HostSolveResult,
    InterfaceFlux,
    _availability_flux,
    _bigg_exchange_id,
    _coupling_scale,
    _identified_points,
    _interface_of_suffix,
    _met_from_bigg_exchange,
    _met_from_host_exchange,
    _uptake_fva_ranges,
    classify_host_exchanges,
    classify_host_interfaces,
)
from cmig.core.sign import Label

__all__ = [
    "BIOMASS_BASIS_KINDS",
    "DEFAULT_BIGG_COUPLING_EXCLUDE",
    "BiggHostMicrobeResult",
    "CouplingScale",
    "HostBenchmarkResult",
    "HostInterface",
    "HostModelSummary",
    "HostSolveResult",
    "InterfaceFlux",
    "_availability_flux",
    "_bigg_exchange_id",
    "_coupling_scale",
    "_identified_points",
    "_met_from_bigg_exchange",
    "_met_from_host_exchange",
    "_uptake_fva_ranges",
    "benchmark_generic_host",
    "classify_host_exchanges",
    "classify_host_interfaces",
    "nonexchange_boundary_uptake",
    "run_bigg_host_microbe",
    "run_host_microbe",
    "solve_bigg_host",
    "solve_generic_host",
    "solve_host",
    "summarize_host_model",
]



def nonexchange_boundary_uptake(host: Any) -> list[str]:
    """Boundary reactions outside ``model.exchanges`` that can still supply mass to the host.

    cobra splits boundary reactions into ``exchanges``, ``sinks`` and ``demands``. Only the first
    set is what CMIG's host coupling used to close, so on a real human GEM the host stayed
    connected to free mass through the other two: Recon3D has 246 non-exchange boundary reactions
    and 95 of them sit at ``lower_bound = -1000``, enough to build biomass with no microbes and no
    declared medium at all. Measured, that made the coupled host objective indistinguishable
    (368.0102475464… to 15 significant figures) with and without any microbial availability.

    Round-6 integration: this is answered by :mod:`cmig.core.boundary`, the shared primitive, rather
    than by a second local enumeration. The difference is not cosmetic — the original test here was
    ``lower_bound < 0``, which cannot see a boundary reaction written ``--> met`` (a demand that
    supplies at *positive* flux). ``supply_capacity`` reads the direction off the stoichiometry, so
    the count is the same 95 on Recon3D and correct on a model where the two disagree.
    """
    from cmig.core.boundary import exposes_boundary, mass_supplying_boundary

    if not exposes_boundary(host):
        # Not a cobra model (a test double, or a model built without the boundary accessor). The
        # honest answer for something whose boundary cannot be enumerated is "none known", not a
        # guess from id prefixes — an id-prefix guess is the enumeration mistake this fixes.
        return []
    return sorted(
        supply.reaction_id
        for supply in mass_supplying_boundary(host).values()
        if not supply.is_exchange
    )


def summarize_host_model(host: Any, *, exchange_examples: int = 10) -> HostModelSummary:
    """Summarize a cobra-compatible host model without assuming CMIG lumen/blood IDs."""
    from cobra.util.solver import linear_reaction_coefficients

    from cmig.core.boundary import boundary_reactions, exposes_boundary
    from cmig.io.model_import import objective_structure_warning

    exchanges = list(host.exchanges)
    objective_coefficient_reactions = sorted(
        linear_reaction_coefficients(host), key=lambda reaction: str(reaction.id)
    )
    objective = [str(r.id) for r in objective_coefficient_reactions]
    classification = classify_host_interfaces(host)
    raw_compartments = getattr(host, "compartments", {})
    compartments = {str(k): str(v) for k, v in dict(raw_compartments).items()}
    return HostModelSummary(
        model_id=str(getattr(host, "id", "")),
        n_reactions=len(host.reactions),
        n_metabolites=len(host.metabolites),
        n_genes=len(host.genes),
        n_exchanges=classification.n_exchanges,
        compartments=compartments,
        objective_reactions=objective,
        exchange_examples=[str(r.id) for r in exchanges[:exchange_examples]],
        has_lumen_blood_interfaces=classification.has_lumen_blood_interfaces,
        objective_warning=objective_structure_warning(
            len(objective), objective_coefficient_reactions
        ),
        n_boundary_reactions=(
            len(boundary_reactions(host)) if exposes_boundary(host)
            else len([r for r in host.reactions if bool(getattr(r, "boundary", False))])
        ),
        n_nonexchange_boundary_uptake=len(nonexchange_boundary_uptake(host)),
        interface_classification=classification.as_dict(),
    )


def solve_generic_host(host: Any, *, solver: str = "gurobi") -> HostSolveResult:
    """Solve a generic cobra host GEM as-is.

    This is the explicit path for Recon3D/Human-GEM style models that have extracellular exchanges
    but do not expose CMIG's lumen/blood interface convention. It performs a real LP solve and
    reports the model objective value; interface fluxes are populated only if the model already uses
    `_lumen`/`_blood` exchange IDs.
    """
    from cobra.util.solver import linear_reaction_coefficients

    from cmig.core.single_model import _require_lp, set_model_solver

    _require_lp(solver)
    with host:
        set_model_solver(host, solver)
        sol = host.optimize()
        status = str(sol.status)
        if status != "optimal":
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"generic host LP non-optimal (status={status})",
            )])
            return HostSolveResult(False, status, 0.0, [], {}, diag)

        fluxes = {str(rid): float(v) for rid, v in sol.fluxes.items()}
        coeffs = linear_reaction_coefficients(host)
        objective_value = sum(float(c) * fluxes.get(r.id, 0.0) for r, c in coeffs.items())
        interface = classify_host_exchanges(fluxes, host=host)
        return HostSolveResult(
            viable=objective_value > 1e-9,
            status=status,
            biomass=objective_value,
            interface_fluxes=interface,
            lumen_uptake={
                f.metabolite: -f.flux for f in interface
                if f.interface == HostInterface.LUMEN.value and f.label == Label.UPTAKE.value
            },
            # One LP vertex, no objective-fixed FVA: the default label would over-claim.
            attribution_method="single_fba_point",
        )


def benchmark_generic_host(host: Any, *, solver: str = "gurobi") -> HostBenchmarkResult:
    """Generic Human-GEM/Recon3D scale benchmark: model size + LP solve time/memory.

    ``quantitative_coupling_ready`` requires evidence for both sides *and* a side for every
    exchange. A partial real-GEM classification is exposed for review but is not promoted to a
    complete quantitative contract.
    """
    summary = summarize_host_model(host)
    tracemalloc.start()
    start = time.perf_counter()
    try:
        result = solve_generic_host(host, solver=solver)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    elapsed = time.perf_counter() - start
    warnings: list[str] = []
    classification = summary.interface_classification
    if not summary.has_lumen_blood_interfaces:
        warnings.append(
            "host model has no evidence-backed lumen/blood pair; quantitative coupling requires "
            "reviewed interface-side mapping before microbe-host flux constraints"
        )
    elif not classification.get("complete", False):
        warnings.append(
            "host model has evidence for both lumen and blood, but interface classification is "
            f"partial ({classification.get('n_unclassified', 0)} unclassified, "
            f"{classification.get('n_conflicted', 0)} conflicted); quantitative coupling "
            "requires reviewed assignments for the remainder"
        )
    # R6-H: the objective structure verdict has to reach the benchmark payload. Without it this
    # command reported Recon3D's maintenance optimum of 755.003 with an empty warnings list.
    if summary.objective_warning:
        warnings.append(summary.objective_warning)
    if summary.n_nonexchange_boundary_uptake:
        warnings.append(
            f"{summary.n_nonexchange_boundary_uptake} boundary reactions outside "
            "model.exchanges (cobra sinks/demands) can supply mass to this host; an objective "
            "value from this model is not attributable to a declared medium alone"
        )
    if result.status != "optimal":
        warnings.append(f"host LP solve status is {result.status}")
    return HostBenchmarkResult(
        summary=summary,
        solve=result,
        solve_seconds=elapsed,
        peak_memory_mb=peak / (1024 * 1024),
        quantitative_coupling_ready=bool(classification.get("complete", False)),
        warnings=warnings,
    )


def solve_host(
    host: Any, lumen_availability: dict[str, float], *,
    maintenance_reaction: str = "ATPM", maintenance_flux: float = 1.0,
    solver: str = "gurobi",
) -> HostSolveResult:
    """config B host solve: lumen 가용 대사체 → host uptake 한계 + viability(ATPM≥임계) 제약.

    host 는 **군집 성장 목적 미포함** — host 자체 목적(biomass)로 풀되, viability =
    feasible(status optimal) AND biomass>0 (제로-biomass host 는 non-viable 계약).
    lumen_availability: {metabolite: 가용 flux}(미생물 community 분비량). 미생물 SCFA → host 흡수.
    """
    from cmig.core.boundary import (
        boundary_reactions,
        close_boundary_supply,
        set_supply_limit,
        supply_capacity,
    )
    from cmig.core.single_model import _require_lp
    _require_lp(solver)
    with host:
        from cmig.core.single_model import set_model_solver
        set_model_solver(host, solver)
        ex_ids = {r.id for r in host.reactions}
        # Round 6 (track B, P2): this function implements CMIG's 2-interface contract — the lumen
        # is closed by default and only what the microbes secreted may enter, while the blood
        # interface stays open. A model with no `_lumen` ids cannot express that contract, so the
        # loop below closed NOTHING and the LP ran with the model's entire boundary open. Recon3D
        # has `ATPM`, so it passed the maintenance check and returned `viable=True` with a
        # phantom-fed objective — a wrong number, not an error. Reachable from no CLI path today,
        # but the next person to wire one would have inherited it silently.
        host_boundary = boundary_reactions(host)
        interface_classification = classify_host_interfaces(host)
        interface_by_exchange = interface_classification.by_exchange()

        def boundary_interface(reaction: Any) -> HostInterface:
            assignment = interface_by_exchange.get(str(reaction.id))
            if assignment is not None:
                return HostInterface(assignment.interface)
            return _interface_of_suffix(str(reaction.id))

        lumen_boundary = [
            str(r.id) for r in host_boundary
            if boundary_interface(r) is HostInterface.LUMEN
        ]
        # The trap, stated precisely: an `EX_*` reaction CMIG cannot classify as lumen or blood is
        # an exchange interface this contract does not model, and if it can supply mass it feeds
        # the LP invisibly. Recon3D has 1560 of them, all open, so `solve_host` closed nothing,
        # passed the ATPM check (Recon3D has `ATPM`) and returned `viable=True` off a background it
        # never declared. Refusing is the only honest answer: the right entry point for a generic
        # GEM is `solve_generic_host` or `solve_bigg_host`, both of which say what they assume.
        exchange_boundary_ids = {
            str(reaction.id) for reaction in host_boundary
            if str(reaction.id).startswith("EX_")
            or str(reaction.id) in interface_by_exchange
        }
        unclassified = sorted(
            str(r.id) for r in host_boundary
            if str(r.id) in exchange_boundary_ids
            and boundary_interface(r) is HostInterface.UNKNOWN
            and supply_capacity(r) > 0.0
        )
        if unclassified:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.HOST_INTERFACE_ABSENT,
                f"{len(unclassified)} host exchange reactions can supply mass but belong to "
                "neither the _lumen nor the _blood interface, e.g. "
                f"{unclassified[:5]}; the 2-interface contract cannot classify them, so this "
                "solve would be fed by an undeclared background. Use solve_generic_host (reports "
                "the model as-is) or the BiGG coupling path (solve_bigg_host, which isolates the "
                "whole boundary) for a generic GEM.",
            )])
            return HostSolveResult(False, "infeasible", 0.0, [], {}, diag)
        # [정직성] lumen interface 는 **기본 폐쇄**(uptake=0) — 미생물이 실제 분비한 것만 흡수 가능.
        # Closed against `model.boundary` restricted to the lumen, so a `SK_*_lumen` sink is closed
        # too; the old `EX_`-prefixed loop over `host.reactions` could not see one.
        close_boundary_supply(host, only=lumen_boundary)
        # lumen uptake 한계: 가용 대사체만 EX_<met>_lumen lower_bound = -available 개방.
        for met, avail in lumen_availability.items():
            ex = f"EX_{met}_lumen"
            flux = _availability_flux(avail, label=f"lumen_availability[{met!r}]")
            if ex in ex_ids:
                set_supply_limit(host.reactions.get_by_id(ex), flux)
        # viability: ATP maintenance ≥ 임계 (명시 강제). upper < 임계면 동반 상향(bound 역전 방지).
        if maintenance_reaction in ex_ids:
            mr = host.reactions.get_by_id(maintenance_reaction)
            mr.bounds = (
                max(mr.lower_bound, maintenance_flux),
                max(mr.upper_bound, maintenance_flux),
            )
        else:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.HOST_MAINTENANCE_ABSENT,
                f"host maintenance reaction absent: {maintenance_reaction}",
            )])
            return HostSolveResult(False, "infeasible", 0.0, [], {}, diag)

        sol = host.optimize()
        status = str(sol.status)
        feasible = status == "optimal"          # maintenance 충족 가능성 (viability 필요조건)
        if not feasible:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts
            diag = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"host 비viable — maintenance({maintenance_flux}) 충족 불가 (status={status})")])
            return HostSolveResult(False, status, 0.0, [], {}, diag)

        fluxes = {str(rid): float(v) for rid, v in sol.fluxes.items()}
        interface = classify_host_exchanges(fluxes, host=host)
        lumen_exchange_by_metabolite = {
            met: f"EX_{met}_lumen"
            for met in sorted(lumen_availability)
            if f"EX_{met}_lumen" in ex_ids
        }
        exchange_ranges = _uptake_fva_ranges(
            host, list(lumen_exchange_by_metabolite.values())
        )
        lumen_uptake_ranges = {
            met: exchange_ranges[exchange]
            for met, exchange in lumen_exchange_by_metabolite.items()
        }
        lumen_uptake = _identified_points(lumen_uptake_ranges)
        from cobra.util.solver import linear_reaction_coefficients
        coeffs = linear_reaction_coefficients(host)
        biomass = sum(float(c) * fluxes.get(r.id, 0.0) for r, c in coeffs.items())
        return HostSolveResult(
            biomass > 1e-9,        # viability = feasible AND 양의 biomass (계약; 216·331 동일)
            status,
            biomass,
            interface,
            lumen_uptake,
            lumen_uptake_ranges=lumen_uptake_ranges,
        )


def run_host_microbe(
    taxonomy: Any, host: Any, *,
    microbial_biomass_gdw: float,
    host_biomass_gdw: float,
    biomass_basis_kind: str,
    biomass_basis_source: str,
    solver: str = "gurobi", tradeoff_f: float = 0.5,
    maintenance_flux: float = 1.0, engine: Any = None,
) -> tuple[HostSolveResult, Any]:
    """end-to-end config B: 미생물 community solve → lumen 분비 → host solve + impact (실 wiring).

    community external_exchange(분비>0) → lumen_availability → solve_host → host_impact.
    orphan 아님 — 실 micom 분비가 host 입력. (HostSolveResult, HostImpact) 반환.
    """
    from cmig.core.engine import MicomEngine
    from cmig.core.host_impact import host_impact

    eng = engine if engine is not None else MicomEngine()
    scale = _coupling_scale(
        microbial_biomass_gdw,
        host_biomass_gdw,
        basis_kind=biomass_basis_kind,
        basis_source=biomass_basis_source,
    )
    community = eng.build_community(taxonomy, cmig_solver=solver)
    result = eng.cooperative_tradeoff(community, tradeoff_f, cmig_solver=solver)
    if result.status != "optimal":
        diag = result.diagnostic
        host_res = HostSolveResult(False, result.status, 0.0, [], {}, diag)
        return host_res, host_impact({}, host_res)
    secretion = {
        metabolite: flux * scale.microbe_to_host_ratio
        for metabolite, flux in result.external_exchange.items()
        if flux > 1e-6
    }
    host_res = solve_host(host, secretion, maintenance_flux=maintenance_flux, solver=solver)
    return host_res, host_impact(secretion, host_res)


# Public compatibility surface, now a static import. ``host_coupling`` imports only the shared
# leaf module :mod:`cmig.core.host_types`, so this cannot re-enter a partially initialised host
# module and mypy sees both names as real callables.
from cmig.core.host_coupling import run_bigg_host_microbe, solve_bigg_host  # noqa: E402
