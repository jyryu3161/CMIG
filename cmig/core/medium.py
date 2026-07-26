"""Minimal medium (cardinality MILP) + limiting nutrient.

Design Ref: §4.5 (minimal medium·cardinality MILP) / §10 / FR-2.3.
Plan SC: SC-9 (산출 계약) — MILP capability(Gurobi/HiGHS/CPLEX) 필요(§2 capability matrix).

cobra.medium.minimal_medium(minimize_components=True) 로 **최소 cardinality 의 exchange 집합**
(= 성장 유지에 필요한 최소 영양)을 구한다. MILP solver 부재 시 비활성화(§2).
cobra 는 lazy import — 엔진 stack 없는 환경에서도 cmig 패키지 import 가능.
"""

from __future__ import annotations

import math
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
    """Validated minimal-medium result.

    ``components`` is one cardinality-minimal support selected by the MILP. It is not itself an
    essentiality claim. ``essential_components`` contains exchanges whose removal from the full
    candidate medium makes ``min_growth`` unattainable (leave-one-out verification).
    """

    components: list[str]            # exchange reaction id (결정적 정렬)
    n_components: int                # cardinality
    min_growth: float                # 충족 성장 하한
    uptake_bounds: dict[str, float]  # exchange id → uptake 허용량
    achieved_growth: float           # returned medium을 재solve한 검증 성장률
    essential_components: list[str]  # full candidate medium leave-one-out verified
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
    """구조적 blocked(bound (0,0)) — exchange 가 flux 를 못 싣는 경우. (full FVA-blocked 아님)

    R5-P3 (codex F4): 예전에는 **모든** 예외를 "이 영양소는 못 쓴다"로 해석했다. cobra 의
    `DictList.get_by_id` 는 없는 id 에 대해 KeyError 만 낸다(측정 확인). 따라서 그 외의
    예외(backend 오류·API drift 등)를 함께 삼키면, 무관한 오류가 조용히 minimal medium 에서
    물 같은 필수 영양소를 빼버리고 **과학적으로 다른 배지**를 만들어낸다. 실제로 없을 때만
    제외하고, 나머지는 올라가게 둔다.
    """
    try:
        rxn = model.reactions.get_by_id(ex_id)
    except KeyError:
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
    # U 기본집합 항상 포함 (모델에 존재 + 미blocked + 실제 흡수 용량이 있는 것만).
    for ex in u_base:
        if ex in out:
            continue
        if _is_blocked(model, ex):
            continue
        rxn = model.reactions.get_by_id(ex)
        uptake_cap = abs(float(rxn.lower_bound))    # 허용 uptake 량
        # 흡수 용량 0(lower_bound==0, ub>0 인 secretion-only exchange)은 영양원으로 무의미하다.
        # 강제 추가하면 limiting_nutrients 가 이를 essential 로 오라벨하므로 제외한다.
        if uptake_cap == 0.0:
            continue
        out[ex] = uptake_cap
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
    invariant: U 기본집합 항상 포함(흡수 용량 0 은 제외)·oxygen_mode(O₂)·blocked 제외.
    결정성: 출력은 exchange id 로 정렬한다. 동일 cardinality 대안 최적(alternate optima) 간의
    **선택**은 solver 결정성에 의존한다(같은 solver·머신이면 재현적). cross-solver 선택 차이는
    예상된 동작이다(cobra minimal_medium API 한계로 lexicographic tie-break 미적용).
    """
    if oxygen_mode not in OXYGEN_MODES:
        raise ValueError(f"oxygen_mode ∈ {OXYGEN_MODES} (받음: {oxygen_mode}) [§4.5]")
    if not math.isfinite(min_objective_value) or min_objective_value <= 0.0:
        raise ValueError("min_objective_value must be finite and > 0")
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
    with model as working:
        working.solver = solver           # context가 solver/bounds/medium을 원본에 남기지 않음
        candidate_medium = dict(working.medium)
        if oxygen_mode == "anaerobic":
            # Oxygen is a solve constraint, not a label applied after an aerobic MILP.
            candidate_medium.pop(O2_EXCHANGE, None)
        working.medium = candidate_medium

        series = minimal_medium(
            working, min_objective_value=min_objective_value, minimize_components=True
        )
        if series is None:                # capability 있음 → None 은 infeasible (TC-8)
            raise MILPInfeasibleError(
                f"minimal medium MILP infeasible (min_growth={min_objective_value}, "
                f"solver={solver}, oxygen_mode={oxygen_mode})"
            )
        bounds = {str(k): float(v) for k, v in series.items()}
        bounds = _apply_min_medium_invariants(
            working,
            bounds,
            oxygen_mode=oxygen_mode,
            u_base=u_base,
            exclude_blocked=exclude_blocked,
        )

        # Re-solve the exact medium that will be returned. A post-processed support that does not
        # achieve the declared growth threshold is never published as a successful result.
        working.medium = bounds
        achieved_raw = working.slim_optimize(error_value=float("nan"))
        achieved = float(achieved_raw)
        tolerance = 1e-7 * max(1.0, abs(min_objective_value))
        if not math.isfinite(achieved) or achieved + tolerance < min_objective_value:
            raise MILPInfeasibleError(
                "minimal medium validation failed: "
                f"achieved={achieved}, required={min_objective_value}, "
                f"oxygen_mode={oxygen_mode}"
            )

        # Global-within-input-medium essentiality: restore the full candidate medium, remove one
        # selected component, and re-optimize. Alternatives remain available, so alternate carbon
        # or electron sources prevent false 'limiting' labels.
        essential: list[str] = []
        for exchange_id in sorted(bounds):
            leave_one_out = dict(candidate_medium)
            leave_one_out.pop(exchange_id, None)
            working.medium = leave_one_out
            value = float(working.slim_optimize(error_value=float("nan")))
            if not math.isfinite(value) or value + tolerance < min_objective_value:
                essential.append(exchange_id)

    return MinimalMediumResult(
        # Deterministic presentation; the selected MILP support may still be solver-specific.
        components=sorted(bounds),
        n_components=len(bounds),
        min_growth=min_objective_value,
        uptake_bounds=bounds,
        achieved_growth=achieved,
        essential_components=essential,
        oxygen_mode=oxygen_mode,
    )


def limiting_nutrients(result: MinimalMediumResult) -> list[str]:
    """Return leave-one-out verified essential nutrients, not all selected components."""
    return list(result.essential_components)
