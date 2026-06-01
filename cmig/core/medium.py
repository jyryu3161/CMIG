"""Minimal medium (cardinality MILP) + limiting nutrient.

Design Ref: §4.5 (minimal medium·cardinality MILP) / §10 / FR-2.3.
Plan SC: SC-9 (산출 계약) — MILP capability(Gurobi/HiGHS/CPLEX) 필요(§2 capability matrix).

cobra.medium.minimal_medium(minimize_components=True) 로 **최소 cardinality 의 exchange 집합**
(= 성장 유지에 필요한 최소 영양)을 구한다. MILP solver 부재 시 비활성화(§2).
cobra 는 lazy import — 엔진 stack 없는 환경에서도 cmig 패키지 import 가능.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MILPUnavailableError(RuntimeError):
    """MILP solver/cobra 부재 → minimal medium 비활성화 (§2 capability degrade).

    TC-8: 이것은 **capability 부재**(solver/cobra 없음)를 의미한다.
    실제 모델이 infeasible 한 경우는 MILPInfeasibleError 로 구분한다(§4.4 ≠ §2).
    """


class MILPInfeasibleError(RuntimeError):
    """minimal medium MILP 가 infeasible — 모델/성장 하한이 만족 불가 (§4.4 수치 거동).

    TC-8: capability 는 있으나 해가 없음. capability 부재(MILPUnavailableError)와 별개 개념.
    """


# [MIN-MEDIUM-U] (§4.5): U 기본 집합 — 항상 available(BiGG 기준), O₂ 는 oxygen_mode 로 결정.
DEFAULT_U_BASE = ("EX_h2o_e", "EX_h_e", "EX_pi_e")
O2_EXCHANGE = "EX_o2_e"
OXYGEN_MODES = ("aerobic", "anaerobic")


@dataclass(frozen=True)
class MinimalMediumResult:
    """minimal medium 산출 — 최소 exchange 집합 ([MIN-MEDIUM-U] invariant 적용)."""

    components: list[str]            # exchange reaction id (결정적 정렬)
    n_components: int                # cardinality
    min_growth: float                # 충족 성장 하한
    uptake_bounds: dict[str, float]  # exchange id → uptake 허용량
    oxygen_mode: str = "aerobic"     # {aerobic, anaerobic} — O₂ 포함/제외


def _load_cobra() -> Any:
    try:
        import cobra
    except ImportError as e:  # pragma: no cover - 2a 환경
        raise MILPUnavailableError(
            "cobra 미설치 — minimal medium 비활성화 (`uv sync --extra engine`)."
        ) from e
    return cobra


def _is_blocked(model: Any, ex_id: str) -> bool:
    """구조적 blocked(bound (0,0)) — exchange 가 flux 를 못 싣는 경우. (full FVA-blocked 아님)"""
    try:
        rxn = model.reactions.get_by_id(ex_id)
    except Exception:  # noqa: BLE001 - cobra get_by_id 다양한 예외
        return True               # 모델에 없으면 사용 불가 = 제외
    return bool(rxn.lower_bound == 0 and rxn.upper_bound == 0)


def _apply_min_medium_invariants(
    model: Any, bounds: dict[str, float], *, oxygen_mode: str,
    u_base: tuple[str, ...], exclude_blocked: bool,
) -> dict[str, float]:
    """[MIN-MEDIUM-U] (§4.5): U 기본집합 항상 포함·O₂ oxygen_mode·blocked 제외·결정적.

    U 기본 {H₂O,H⁺,Pi} 는 항상 available → 모델에 존재하면 medium 에 포함(없으면 무시).
    anaerobic → O₂ exchange 제외. blocked(구조적 (0,0)) exchange 제외.
    """
    out = dict(bounds)
    # U 기본집합 항상 포함 (모델에 존재 + 미blocked 인 것만).
    for ex in u_base:
        if ex in out:
            continue
        if not _is_blocked(model, ex):
            rxn = model.reactions.get_by_id(ex)
            out[ex] = abs(float(rxn.lower_bound)) or 1000.0   # 허용 uptake 량
    # oxygen_mode: anaerobic → O₂ 제외.
    if oxygen_mode == "anaerobic":
        out.pop(O2_EXCHANGE, None)
    # blocked exchange 제외 (구조적).
    if exclude_blocked:
        out = {ex: v for ex, v in out.items() if not _is_blocked(model, ex)}
    return out


def minimal_medium_cardinality(
    model: Any, min_objective_value: float, *, solver: str = "gurobi",
    oxygen_mode: str = "aerobic", u_base: tuple[str, ...] = DEFAULT_U_BASE,
    exclude_blocked: bool = True,
) -> MinimalMediumResult:
    """cardinality MILP 최소 배지 (§4.5) + [MIN-MEDIUM-U] invariant (TC-10).

    model: cobra Model. min_objective_value: 유지할 성장 하한(절대).
    minimize_components=True → 최소 **개수**의 exchange (MILP, Gurobi/HiGHS/CPLEX).
    capability 부재 → MILPUnavailableError; 실제 infeasible → MILPInfeasibleError (TC-8).
    invariant: U 기본집합 항상 포함·oxygen_mode(O₂)·blocked 제외·결정적 tie-break(sorted).
    """
    if oxygen_mode not in OXYGEN_MODES:
        raise ValueError(f"oxygen_mode ∈ {OXYGEN_MODES} (받음: {oxygen_mode}) [§4.5]")
    _load_cobra()                       # cobra 가용성 보장
    from cobra.medium import minimal_medium

    # TC-9: solver capability 단일 진입점(solver seam) 경유 — MILP 미지원/부재 시 fail-fast.
    from cmig.core.solver import capability_matrix
    cap = capability_matrix().get(solver)
    if cap is None or not cap.supports("MILP"):
        raise MILPUnavailableError(
            f"solver '{solver}' MILP capability 부재/미가용 (§2 capability matrix). "
            f"가용 MILP solver: {[n for n, c in capability_matrix().items() if c.supports('MILP')]}"
        )
    model.solver = solver               # capability 확인 후 설정 (실패는 더 이상 silent 아님)
    series = minimal_medium(
        model, min_objective_value=min_objective_value, minimize_components=True
    )
    if series is None:                  # capability 있음 → None 은 infeasible (TC-8)
        raise MILPInfeasibleError(
            f"minimal medium MILP infeasible (min_growth={min_objective_value}, solver={solver})"
        )
    bounds = {str(k): float(v) for k, v in series.items()}
    bounds = _apply_min_medium_invariants(
        model, bounds, oxygen_mode=oxygen_mode, u_base=u_base, exclude_blocked=exclude_blocked,
    )
    return MinimalMediumResult(
        components=sorted(bounds),       # 결정적 tie-break
        n_components=len(bounds),
        min_growth=min_objective_value,
        uptake_bounds=bounds,
        oxygen_mode=oxygen_mode,
    )


def limiting_nutrients(result: MinimalMediumResult) -> list[str]:
    """제한 영양 = 최소 배지 구성요소 (이 중 하나라도 빠지면 성장 하한 미달).

    cardinality 최소이므로 모든 구성요소가 essential(=limiting) 후보다 (§10 limiting nutrient).
    """
    return list(result.components)
