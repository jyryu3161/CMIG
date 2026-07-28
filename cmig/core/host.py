"""Host-Microbe core — HostModel · 2-interface sign · viability 제약 (Roadmap Phase 3.1, §12).

Design Ref: §12 (Host-Microbe) / cmig-host.design. Plan SC: SC-HM1~HM6.

[config B 확정] micom 0.39.0 Community 는 host 파라미터 없음(probe) → MICOM-native host 불가 →
**CMIG 2-compartment post-process**: 미생물 community solve → lumen 가용 대사체 → host(cobra) 를
lumen uptake 한계로 풀되 **viability 제약(ATP maintenance ≥ 임계, host 는 군집 성장 목적 미포함)**.

2-interface: lumen(장관, 미생물 공유) vs blood(전신). exchange id 접미사(_lumen/_blood)로 분류,
sign 단일 진입점(sign.convert)으로 방향 라벨. cobra 위임(자체 LP 미구현).
"""

from __future__ import annotations

import enum
import math
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any

from cmig.core.sign import Label, Scope, convert

DEFAULT_BIGG_COUPLING_EXCLUDE = frozenset({"h", "h2o", "co2"})
BIOMASS_BASIS_KINDS = frozenset({"measured", "literature", "validation"})


class HostInterface(enum.Enum):
    LUMEN = "lumen"      # 장관(미생물 공유) — 미생물 SCFA 유입
    BLOOD = "blood"      # 전신 순환
    UNKNOWN = "unknown"


def _interface_of(exchange_id: str) -> HostInterface:
    if exchange_id.endswith("_lumen"):
        return HostInterface.LUMEN
    if exchange_id.endswith("_blood"):
        return HostInterface.BLOOD
    return HostInterface.UNKNOWN


@dataclass(frozen=True)
class InterfaceFlux:
    """host exchange 한 건의 2-interface sign 분류."""

    exchange_id: str
    interface: str
    metabolite: str
    flux: float
    label: str | None      # secretion | uptake | None(무흐름) — sign 단일 진입점


@dataclass(frozen=True)
class HostSolveResult:
    """host solve(config B) 산출.

    viable = feasible(status optimal, ATP maintenance 충족 가능) **그리고** 양(+)의 biomass(>1e-9).
    maintenance 만 충족하고 biomass 최적이 0 인 host 는 **non-viable**(정성 의존성 계약 —
    test_host_feasible_zero_objective_is_not_viable). 세 solve 경로(solve_host/solve_bigg_host/
    solve_generic_host)가 이 계약을 동일하게 적용한다.
    """

    viable: bool
    status: str
    biomass: float
    interface_fluxes: list[InterfaceFlux] = field(default_factory=list)
    lumen_uptake: dict[str, float] = field(default_factory=dict)   # 미생물→host 흡수(met→flux)
    diagnostic: str | None = None
    lumen_uptake_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    attribution_method: str = "objective_fixed_fva"
    flux_unit: str = "mmol gDW_host^-1 h^-1"
    # Round 6 (track B): what the solve actually closed on the host's boundary, measured rather
    # than intended. `None` on paths that do not isolate (`solve_host`, `solve_generic_host`).
    # A solve that left mass sources open must be able to say so; see `run_bigg_host_microbe`,
    # which turns this into a warning, and the manifest provenance that records it.
    boundary_isolation: dict[str, Any] | None = None
    # R6-H: the same facts in prose, for a caller that reads `HostSolveResult` directly rather
    # than the manifest — e.g. that the host was left connected to non-exchange boundary
    # suppliers, so the objective is not attributable to the microbial availability. Derived from
    # `boundary_isolation` by the solver so the two can never disagree; `diagnostic` stays
    # reserved for failures.
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CouplingScale:
    """미생물 community-specific flux를 host-specific flux로 변환하는 biomass 기준."""

    microbial_biomass_gdw: float
    host_biomass_gdw: float
    microbe_to_host_ratio: float
    basis_kind: str
    basis_source: str
    source_flux_unit: str = "mmol gDW_microbiome^-1 h^-1"
    target_flux_unit: str = "mmol gDW_host^-1 h^-1"


@dataclass(frozen=True)
class HostModelSummary:
    """generic host GEM inspection summary.

    Recon3D/Human-GEM 같은 외부 human GEM은 CMIG toy host의 `_lumen`/`_blood` exchange
    convention을 따르지 않을 수 있으므로, coupling 전에 모델 구조와 LP objective를 먼저 기록한다.
    """

    model_id: str
    n_reactions: int
    n_metabolites: int
    n_genes: int
    n_exchanges: int
    compartments: dict[str, str]
    objective_reactions: list[str]
    exchange_examples: list[str]
    has_lumen_blood_interfaces: bool
    # R6-H: recording the objective *id* is not enough. Recon3D ships `BIOMASS_maintenance` and
    # optimizes to 755.003 — a maintenance rate — while RECON1 ships the transport reaction
    # `S6T14g`. Both were summarized here with no statement that the optimum is not growth, so
    # the structure verdict travels with the summary.
    objective_warning: str | None = None
    n_boundary_reactions: int = 0
    # Boundary reactions cobra does NOT classify as exchanges (its `sinks`/`demands`) that can
    # still inject mass. On Recon3D there are 95 such `SK_*` reactions at lower_bound = -1000.
    n_nonexchange_boundary_uptake: int = 0


@dataclass(frozen=True)
class HostBenchmarkResult:
    """Human-GEM/Recon3D scale host benchmark record."""

    summary: HostModelSummary
    solve: HostSolveResult
    solve_seconds: float
    peak_memory_mb: float
    quantitative_coupling_ready: bool
    warnings: list[str]


@dataclass(frozen=True)
class BiggHostMicrobeResult:
    """BiGG-ID direct host-microbe coupling product result."""

    community_status: str
    community_growth: float
    microbial_secretion: dict[str, float]
    member_secretion: dict[str, dict[str, float]]
    matched_exchanges: dict[str, str]
    unmatched_metabolites: list[str]
    host_result: HostSolveResult
    impact: Any
    warnings: list[str]
    community_secretion: dict[str, float] = field(default_factory=dict)
    coupling_scale: CouplingScale | None = None
    # Round 6 [P1]: round 5's objective-structure guard reached `strain-growth` and `model-quality`
    # and none of the three host-coupling commands, so `--host-objective` stayed optional and a
    # transport or demand reaction could be published as `host_objective` with no caveat anywhere
    # (RECON1 ships `S6T14g`, a Golgi sulfotransferase, as its default objective). All three
    # commands go through `run_bigg_host_microbe`, so the guard is called once, here.
    objective_warning: str | None = None
    objective_reactions: list[str] = field(default_factory=list)
    # Round 7: which requested medium exchanges the community/host could not honour and were
    # therefore dropped under `--allow-unknown-medium`. Empty under the strict default, because
    # strict refuses instead of dropping. It exists so the *commands* can derive `degraded`
    # from a measurement rather than from parsing their own warning strings.
    unapplied_medium_exchanges: tuple[str, ...] = ()


def _met_from_host_exchange(exchange_id: str) -> str:
    """EX_ac_lumen → ac · EX_glc_blood → glc."""
    s = exchange_id
    if s.startswith("EX_"):
        s = s[3:]
    for suf in ("_lumen", "_blood"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def _bigg_exchange_id(metabolite: str, *, suffix: str = "_e") -> str:
    """BiGG metabolite id -> exchange id, e.g. but -> EX_but_e."""
    return f"EX_{metabolite}{suffix}"


def _met_from_bigg_exchange(exchange_id: str, *, suffix: str = "_e") -> str:
    """EX_but_e -> but."""
    s = exchange_id[3:] if exchange_id.startswith("EX_") else exchange_id
    if s.endswith(suffix):
        return s[: -len(suffix)]
    return s


def _availability_flux(value: float, *, label: str) -> float:
    """Validate a non-negative finite uptake availability value."""
    if isinstance(value, bool):
        raise ValueError(f"{label} availability must be numeric, not bool")
    flux = float(value)
    if not math.isfinite(flux) or flux < 0.0:
        raise ValueError(f"{label} availability must be finite and non-negative")
    return flux


def _coupling_scale(
    microbial_biomass_gdw: float,
    host_biomass_gdw: float,
    *,
    basis_kind: str,
    basis_source: str,
) -> CouplingScale:
    """Validate numeric scaling and retain how the gDW bases were obtained."""
    microbial = _availability_flux(
        microbial_biomass_gdw, label="microbial_biomass_gdw"
    )
    host = _availability_flux(host_biomass_gdw, label="host_biomass_gdw")
    if microbial <= 0.0 or host <= 0.0:
        raise ValueError("microbial_biomass_gdw and host_biomass_gdw must be > 0")
    kind = str(basis_kind).strip().lower()
    if kind not in BIOMASS_BASIS_KINDS:
        raise ValueError(
            "biomass_basis_kind must be one of: " + ", ".join(sorted(BIOMASS_BASIS_KINDS))
        )
    source = str(basis_source).strip()
    if not source:
        raise ValueError(
            "biomass_basis_source is required (measurement method or literature citation)"
        )
    return CouplingScale(microbial, host, microbial / host, kind, source)


def _uptake_fva_ranges(
    model: Any, exchange_ids: list[str]
) -> dict[str, tuple[float, float]]:
    """최적 host objective를 고정한 exchange uptake 가능 범위."""
    if not exchange_ids:
        return {}
    from cobra.flux_analysis import flux_variability_analysis

    table = flux_variability_analysis(
        model,
        reaction_list=sorted(exchange_ids),
        fraction_of_optimum=1.0,
    )
    ranges: dict[str, tuple[float, float]] = {}
    for reaction_id in sorted(exchange_ids):
        minimum = float(table.loc[reaction_id, "minimum"])
        maximum = float(table.loc[reaction_id, "maximum"])
        ranges[reaction_id] = (max(0.0, -maximum), max(0.0, -minimum))
    return ranges


def _identified_points(
    ranges: dict[str, tuple[float, float]], *, tolerance: float = 1e-6
) -> dict[str, float]:
    """범위 폭이 tolerance 이내인 flux만 식별된 점 추정치로 노출한다."""
    return {
        metabolite: (lower + upper) / 2.0
        for metabolite, (lower, upper) in ranges.items()
        if upper > tolerance and upper - lower <= tolerance
    }


def classify_host_exchanges(fluxes: dict[str, float]) -> list[InterfaceFlux]:
    """host exchange flux → 2-interface sign 분류(sign.convert 단일 진입점)."""
    out: list[InterfaceFlux] = []
    for ex_id, flux in sorted(fluxes.items()):
        if not ex_id.startswith("EX_"):
            continue
        iface = _interface_of(ex_id)
        if iface is HostInterface.UNKNOWN:
            continue
        signed = convert(flux, Scope.ENVIRONMENT)
        out.append(InterfaceFlux(
            exchange_id=ex_id, interface=iface.value,
            metabolite=_met_from_host_exchange(ex_id), flux=flux,
            label=signed.label.value if signed.label is not None else None))
    return out


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

    exchanges = [r for r in host.reactions if str(r.id).startswith("EX_")]
    objective_coefficient_reactions = sorted(
        linear_reaction_coefficients(host), key=lambda reaction: str(reaction.id)
    )
    objective = [str(r.id) for r in objective_coefficient_reactions]
    has_interfaces = any(
        _interface_of(str(r.id)) is not HostInterface.UNKNOWN for r in exchanges
    )
    raw_compartments = getattr(host, "compartments", {})
    compartments = {str(k): str(v) for k, v in dict(raw_compartments).items()}
    return HostModelSummary(
        model_id=str(getattr(host, "id", "")),
        n_reactions=len(host.reactions),
        n_metabolites=len(host.metabolites),
        n_genes=len(host.genes),
        n_exchanges=len(exchanges),
        compartments=compartments,
        objective_reactions=objective,
        exchange_examples=[str(r.id) for r in exchanges[:exchange_examples]],
        has_lumen_blood_interfaces=has_interfaces,
        objective_warning=objective_structure_warning(
            len(objective), objective_coefficient_reactions
        ),
        n_boundary_reactions=(
            len(boundary_reactions(host)) if exposes_boundary(host)
            else len([r for r in host.reactions if bool(getattr(r, "boundary", False))])
        ),
        n_nonexchange_boundary_uptake=len(nonexchange_boundary_uptake(host)),
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
        interface = classify_host_exchanges(fluxes)
        return HostSolveResult(
            viable=objective_value > 1e-9,
            status=status,
            biomass=objective_value,
            interface_fluxes=interface,
            lumen_uptake={
                f.metabolite: -f.flux for f in interface
                if f.interface == HostInterface.LUMEN.value and f.label == Label.UPTAKE.value
            },
        )


def benchmark_generic_host(host: Any, *, solver: str = "gurobi") -> HostBenchmarkResult:
    """Generic Human-GEM/Recon3D scale benchmark: model size + LP solve time/memory.

    This does not pretend CMIG lumen/blood coupling exists. `quantitative_coupling_ready`
    is true only if the host already exposes CMIG-style `_lumen`/`_blood` exchange IDs.
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
    if not summary.has_lumen_blood_interfaces:
        warnings.append(
            "host model has no CMIG lumen/blood exchange convention; quantitative coupling "
            "requires mapping before microbe-host flux constraints"
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
        quantitative_coupling_ready=summary.has_lumen_blood_interfaces,
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
        lumen_boundary = [
            str(r.id) for r in host_boundary
            if _interface_of(str(r.id)) is HostInterface.LUMEN
        ]
        # The trap, stated precisely: an `EX_*` reaction CMIG cannot classify as lumen or blood is
        # an exchange interface this contract does not model, and if it can supply mass it feeds
        # the LP invisibly. Recon3D has 1560 of them, all open, so `solve_host` closed nothing,
        # passed the ATPM check (Recon3D has `ATPM`) and returned `viable=True` off a background it
        # never declared. Refusing is the only honest answer: the right entry point for a generic
        # GEM is `solve_generic_host` or `solve_bigg_host`, both of which say what they assume.
        unclassified = sorted(
            str(r.id) for r in host_boundary
            if str(r.id).startswith("EX_")
            and _interface_of(str(r.id)) is HostInterface.UNKNOWN
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
        interface = classify_host_exchanges(fluxes)
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


_HOST_COUPLING_REEXPORTS = ("run_bigg_host_microbe", "solve_bigg_host")


def __getattr__(name: str) -> object:
    """Lazy re-export of the BiGG host-coupling entry points.

    ``cmig.core.host_coupling`` imports from this module at import time, so a module-level
    re-export here made ``import cmig.core.host_coupling`` (as the *first* import) raise
    ``ImportError: cannot import name 'run_bigg_host_microbe' from partially initialized module``.
    Resolving on attribute access breaks the cycle without changing the public surface.
    """
    if name in _HOST_COUPLING_REEXPORTS:
        from cmig.core import host_coupling

        return getattr(host_coupling, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
