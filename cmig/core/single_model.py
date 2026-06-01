"""AN-SINGLE — 단일 GEM 분석 (Roadmap Phase 1.1).

Design Ref: §10 AN-SINGLE / cmig-an-single.design. Plan SC: SC-AS1~AS6.

cobra 위임 단일모델 연산: FBA/pFBA(LP)·FVA(reuse core.fva)·single 반응/유전자 knockout·
exchange 요약(sign 단일 진입점)·growth feasibility·bound 편집. MICOM/cobra 위임 철학 일관 —
자체 LP 미구현. LP capability 부재 → 정직한 capability_missing (강제 success 금지).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts
from cmig.core.sign import Label, classify


class SingleModelUnavailableError(RuntimeError):
    """LP solver capability 부재 → AN-SINGLE 비활성 (§2 capability degrade)."""


@dataclass(frozen=True)
class SingleModelResult:
    """단일 GEM solve 산출. fluxes 는 reaction_id → flux."""

    objective: float
    status: str                         # optimal | infeasible | ...
    method: str                         # FBA | pFBA
    solver: str
    fluxes: dict[str, float] = field(default_factory=dict)
    diagnostic: str | None = None


def _require_lp(solver: str) -> None:
    """LP capability 단일 진입점(solver seam) — 부재 시 fail-fast (fva.py 와 일관)."""
    from cmig.core.solver import capability_matrix
    cap = capability_matrix().get(solver)
    if cap is None or not cap.supports("LP"):
        avail = [n for n, c in capability_matrix().items() if c.supports("LP")]
        raise SingleModelUnavailableError(
            f"solver '{solver}' LP capability 부재/미가용 (§2). 가용 LP: {avail}"
        )


def solve_single_model(
    model: Any, *, method: str = "FBA", solver: str = "gurobi",
) -> SingleModelResult:
    """AN-SINGLE FBA/pFBA. method ∈ {FBA, pFBA}. LP 부재 → SingleModelUnavailableError."""
    if method not in ("FBA", "pFBA"):
        raise ValueError(f"미지원 method: {method} (FBA|pFBA)")
    _require_lp(solver)
    model.solver = solver
    if method == "pFBA":
        from cobra.flux_analysis import pfba
        sol = pfba(model)            # pFBA objective_value = 총 flux(절약), growth 아님
    else:
        sol = model.optimize()
    fluxes = {str(rid): float(v) for rid, v in sol.fluxes.items()}
    # objective = **growth rate**(원 objective 식)로 일관 — FBA/pFBA 모두 동일 의미.
    # pFBA 는 sol.objective_value 가 총 flux 이므로 원 목적계수로 재계산(biomass flux).
    from cobra.util.solver import linear_reaction_coefficients
    coeffs = linear_reaction_coefficients(model)
    growth = sum(float(c) * fluxes.get(rxn.id, 0.0) for rxn, c in coeffs.items())
    return SingleModelResult(
        objective=growth, status=str(sol.status), method=method, solver=solver, fluxes=fluxes,
    )


def single_reaction_knockout(
    model: Any, reaction_id: str, *, method: str = "FBA", solver: str = "gurobi",
) -> SingleModelResult:
    """단일 반응 knockout 후 재solve (with model: 컨텍스트로 bound 자동 복원)."""
    with model:
        model.reactions.get_by_id(reaction_id).knock_out()
        return solve_single_model(model, method=method, solver=solver)


def single_gene_knockout(
    model: Any, gene_id: str, *, method: str = "FBA", solver: str = "gurobi",
) -> SingleModelResult:
    """단일 유전자 knockout 후 재solve (GPR 반영, bound 자동 복원)."""
    with model:
        model.genes.get_by_id(gene_id).knock_out()
        return solve_single_model(model, method=method, solver=solver)


def single_model_fva(
    model: Any, *, fraction_of_optimum: float = 1.0, solver: str = "gurobi",
) -> dict[str, Any]:
    """AN-SINGLE FVA — core.fva.flux_variability 위임(재구현 금지)."""
    from cmig.core.fva import flux_variability
    return flux_variability(model, fraction_of_optimum=fraction_of_optimum, solver=solver)


def exchange_summary(model: Any, *, solver: str = "gurobi") -> list[dict[str, Any]]:
    """exchange reaction별 flux + 방향(sign 단일 진입점 classify). FBA 1회 후 추출.

    cobra exchange flux 부호 = CMIG 규약(+분비/−흡수). label=None(무흐름)은 inactive.
    """
    res = solve_single_model(model, method="FBA", solver=solver)
    rows: list[dict[str, Any]] = []
    for rxn in model.exchanges:
        flux = res.fluxes.get(rxn.id, 0.0)
        label: Label | None = classify(flux)
        rows.append({
            "reaction_id": rxn.id,
            "flux": flux,
            "direction": label.value if label is not None else "inactive",
        })
    return rows


def growth_feasible(
    model: Any, *, threshold: float = 1e-6, solver: str = "gurobi",
) -> bool:
    """성장 가능 여부 — FBA status=optimal ∧ objective > threshold."""
    res = solve_single_model(model, method="FBA", solver=solver)
    return res.status == "optimal" and res.objective > threshold


def capability_missing_result(solver: str) -> SingleModelResult:
    """LP 부재 시 정직한 capability_missing 산출(강제 success 금지)."""
    diag = diagnostic_from_parts([(
        DiagnosticCode.CAPABILITY_MISSING,
        f"AN-SINGLE LP capability 부재 (solver={solver})",
    )])
    return SingleModelResult(
        objective=0.0, status="capability_missing", method="FBA", solver=solver,
        fluxes={}, diagnostic=diag,
    )
