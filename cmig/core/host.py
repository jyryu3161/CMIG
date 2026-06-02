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
    """host solve(config B) 산출. viable = ATP maintenance 충족 + feasible."""

    viable: bool
    status: str
    biomass: float
    interface_fluxes: list[InterfaceFlux] = field(default_factory=list)
    lumen_uptake: dict[str, float] = field(default_factory=dict)   # 미생물→host 흡수(met→flux)
    diagnostic: str | None = None


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
    matched_exchanges: dict[str, str]
    unmatched_metabolites: list[str]
    host_result: HostSolveResult
    impact: Any
    warnings: list[str]


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


def summarize_host_model(host: Any, *, exchange_examples: int = 10) -> HostModelSummary:
    """Summarize a cobra-compatible host model without assuming CMIG lumen/blood IDs."""
    from cobra.util.solver import linear_reaction_coefficients

    exchanges = [r for r in host.reactions if str(r.id).startswith("EX_")]
    objective = [str(r.id) for r in linear_reaction_coefficients(host)]
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


def solve_bigg_host(
    host: Any,
    microbial_availability: dict[str, float],
    *,
    host_medium: dict[str, float] | None = None,
    exchange_suffix: str = "_e",
    exclude_metabolites: set[str] | frozenset[str] | None = DEFAULT_BIGG_COUPLING_EXCLUDE,
    close_unlisted_uptake: bool = True,
    solver: str = "gurobi",
) -> HostSolveResult:
    """Solve a BiGG-style host GEM coupled to microbial secretions.

    Microbial secretion metabolite ids are assumed to be BiGG ids and are mapped directly to
    host exchange ids (`met` -> `EX_<met>_e`). `host_medium` is optional background host
    availability for non-microbial nutrients, with keys accepted as either exchange ids or
    metabolite ids.
    """
    from cobra.util.solver import linear_reaction_coefficients

    from cmig.core.single_model import _require_lp, set_model_solver

    _require_lp(solver)
    host_medium = host_medium or {}
    with host:
        set_model_solver(host, solver)
        exchange_ids = {str(r.id) for r in host.reactions if str(r.id).startswith("EX_")}
        if close_unlisted_uptake:
            for reaction in host.reactions:
                if str(reaction.id).startswith("EX_") and reaction.lower_bound < 0:
                    reaction.lower_bound = 0.0

        exchange_availability: dict[str, float] = {}
        microbial_caps: dict[str, float] = {}

        def add_availability(key: str, value: float, *, label: str) -> tuple[str | None, float]:
            rid = key if key.startswith("EX_") else _bigg_exchange_id(key, suffix=exchange_suffix)
            flux = _availability_flux(value, label=label)
            if rid in exchange_ids:
                exchange_availability[rid] = (
                    exchange_availability.get(rid, 0.0) + flux
                )
                return rid, flux
            return None, flux

        for key, value in host_medium.items():
            add_availability(str(key), value, label=f"host_medium[{key!r}]")
        excluded = set(exclude_metabolites or set())
        matched: set[str] = set()
        for met, value in microbial_availability.items():
            if met in excluded:
                continue
            rid, flux = add_availability(
                met,
                value,
                label=f"microbial_availability[{met!r}]",
            )
            if rid is not None:
                microbial_caps[met] = microbial_caps.get(met, 0.0) + flux
                matched.add(met)
        for rid, availability in exchange_availability.items():
            host.reactions.get_by_id(rid).lower_bound = -availability

        sol = host.optimize()
        status = str(sol.status)
        if status != "optimal":
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diag = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"BiGG host LP non-optimal under microbial coupling (status={status})",
            )])
            return HostSolveResult(False, status, 0.0, [], {}, diag)

        fluxes = {str(rid): float(v) for rid, v in sol.fluxes.items()}
        coeffs = linear_reaction_coefficients(host)
        objective_value = sum(float(c) * fluxes.get(r.id, 0.0) for r, c in coeffs.items())
        interface_fluxes: list[InterfaceFlux] = []
        lumen_uptake: dict[str, float] = {}
        for rid in sorted(exchange_ids):
            flux = fluxes.get(rid, 0.0)
            signed = convert(flux, Scope.ENVIRONMENT)
            if signed.label is None:
                continue
            met = _met_from_bigg_exchange(rid, suffix=exchange_suffix)
            interface_fluxes.append(InterfaceFlux(
                exchange_id=rid,
                interface="bigg_external",
                metabolite=met,
                flux=flux,
                label=signed.label.value,
            ))
            if met in matched and signed.label is Label.UPTAKE:
                microbial_cap = microbial_caps.get(met, 0.0)
                transfer = min(-flux, microbial_cap)
                if transfer > 1e-6:
                    lumen_uptake[met] = transfer
        return HostSolveResult(
            viable=status == "optimal" and objective_value > 1e-9,
            status=status,
            biomass=objective_value,
            interface_fluxes=interface_fluxes,
            lumen_uptake=lumen_uptake,
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

    host 는 **군집 성장 목적 미포함** — host 자체 목적(biomass)로 풀되 maintenance 충족이 viability.
    lumen_availability: {metabolite: 가용 flux}(미생물 community 분비량). 미생물 SCFA → host 흡수.
    """
    from cmig.core.single_model import _require_lp
    _require_lp(solver)
    with host:
        from cmig.core.single_model import set_model_solver
        set_model_solver(host, solver)
        ex_ids = {r.id for r in host.reactions}
        # [정직성] lumen interface 는 **기본 폐쇄**(uptake=0) — 미생물이 실제 분비한 것만 흡수 가능.
        # availability 미포함 대사체를 phantom 흡수하지 않도록 모든 EX_*_lumen lower_bound=0 먼저.
        for r in host.reactions:
            if r.id.startswith("EX_") and _interface_of(r.id) is HostInterface.LUMEN:
                r.lower_bound = 0.0
        # lumen uptake 한계: 가용 대사체만 EX_<met>_lumen lower_bound = -available 개방.
        for met, avail in lumen_availability.items():
            ex = f"EX_{met}_lumen"
            flux = _availability_flux(avail, label=f"lumen_availability[{met!r}]")
            if ex in ex_ids:
                host.reactions.get_by_id(ex).lower_bound = -flux
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
        viable = status == "optimal"
        if not viable:
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts
            diag = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"host 비viable — maintenance({maintenance_flux}) 충족 불가 (status={status})")])
            return HostSolveResult(False, status, 0.0, [], {}, diag)

        fluxes = {str(rid): float(v) for rid, v in sol.fluxes.items()}
        interface = classify_host_exchanges(fluxes)
        # 미생물→host 흡수 = lumen interface 에서 uptake(label=uptake)
        lumen_uptake = {
            f.metabolite: -f.flux for f in interface
            if f.interface == HostInterface.LUMEN.value and f.label == Label.UPTAKE.value
        }
        from cobra.util.solver import linear_reaction_coefficients
        coeffs = linear_reaction_coefficients(host)
        biomass = sum(float(c) * fluxes.get(r.id, 0.0) for r, c in coeffs.items())
        return HostSolveResult(
            biomass > 1e-9,
            status,
            biomass,
            interface,
            lumen_uptake,
        )


def run_host_microbe(
    taxonomy: Any, host: Any, *, solver: str = "gurobi", tradeoff_f: float = 0.5,
    maintenance_flux: float = 1.0, engine: Any = None,
) -> tuple[HostSolveResult, Any]:
    """end-to-end config B: 미생물 community solve → lumen 분비 → host solve + impact (실 wiring).

    community external_exchange(분비>0) → lumen_availability → solve_host → host_impact.
    orphan 아님 — 실 micom 분비가 host 입력. (HostSolveResult, HostImpact) 반환.
    """
    from cmig.core.engine import MicomEngine
    from cmig.core.host_impact import host_impact

    eng = engine if engine is not None else MicomEngine()
    community = eng.build_community(taxonomy, cmig_solver=solver)
    result = eng.cooperative_tradeoff(community, tradeoff_f, cmig_solver=solver)
    if result.status != "optimal":
        diag = result.diagnostic
        host_res = HostSolveResult(False, result.status, 0.0, [], {}, diag)
        return host_res, host_impact({}, host_res)
    secretion = {m: v for m, v in result.external_exchange.items() if v > 1e-6}  # lumen 가용
    host_res = solve_host(host, secretion, maintenance_flux=maintenance_flux, solver=solver)
    return host_res, host_impact(secretion, host_res)


def run_bigg_host_microbe(
    taxonomy: Any,
    host: Any,
    *,
    solver: str = "gurobi",
    tradeoff_f: float = 0.5,
    microbe_medium: Any | None = None,
    host_medium: dict[str, float] | None = None,
    exchange_suffix: str = "_e",
    exclude_metabolites: set[str] | frozenset[str] | None = DEFAULT_BIGG_COUPLING_EXCLUDE,
    close_unlisted_host_uptake: bool = True,
    engine: Any = None,
) -> BiggHostMicrobeResult:
    """BiGG direct coupling: microbe community secretion -> host `EX_<met>_e` uptake."""
    from cmig.core.engine import MicomEngine
    from cmig.core.host_impact import host_impact

    eng = engine if engine is not None else MicomEngine()
    community = eng.build_community(taxonomy, cmig_solver=solver)
    if microbe_medium is not None:
        from cmig.core.medium_spec import apply_medium_checked

        apply_medium_checked(community, microbe_medium, strict=True)
    community_result = eng.cooperative_tradeoff(community, tradeoff_f, cmig_solver=solver)
    if community_result.status != "optimal":
        host_res = HostSolveResult(
            False, community_result.status, 0.0, [], {}, community_result.diagnostic
        )
        return BiggHostMicrobeResult(
            community_status=community_result.status,
            community_growth=community_result.objective,
            microbial_secretion={},
            matched_exchanges={},
            unmatched_metabolites=[],
            host_result=host_res,
            impact=host_impact({}, host_res),
            warnings=["microbial community solve was not optimal"],
        )
    secretion = {
        metabolite: flux
        for metabolite, flux in community_result.external_exchange.items()
        if flux > 1e-6
    }
    excluded = set(exclude_metabolites or set())
    host_exchange_ids = {str(r.id) for r in host.reactions if str(r.id).startswith("EX_")}
    matched = {
        met: _bigg_exchange_id(met, suffix=exchange_suffix)
        for met in secretion
        if met not in excluded
        if _bigg_exchange_id(met, suffix=exchange_suffix) in host_exchange_ids
    }
    unmatched = sorted(set(secretion) - set(matched) - excluded)
    host_res = solve_bigg_host(
        host,
        secretion,
        host_medium=host_medium,
        exchange_suffix=exchange_suffix,
        exclude_metabolites=exclude_metabolites,
        close_unlisted_uptake=close_unlisted_host_uptake,
        solver=solver,
    )
    warnings: list[str] = []
    excluded_present = sorted(set(secretion) & excluded)
    if excluded_present:
        warnings.append(f"excluded currency microbial secretions: {excluded_present}")
    if unmatched:
        warnings.append(f"unmatched microbial secretions: {unmatched}")
    if not matched:
        warnings.append("no microbial secretions matched host BiGG exchange ids")
    return BiggHostMicrobeResult(
        community_status=community_result.status,
        community_growth=community_result.objective,
        microbial_secretion=secretion,
        matched_exchanges=matched,
        unmatched_metabolites=unmatched,
        host_result=host_res,
        impact=host_impact(secretion, host_res),
        warnings=warnings,
    )
