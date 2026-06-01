"""Consortium Search 고급 — 정규화·Pareto·전략·robustness·explain (Roadmap Phase 3.5/3.6, §14).

Design Ref: §14 / cmig-search-advanced.design. Plan SC: SC-SA1~SA7.

search-core(target_max_solve·rank_consortia) 위에 부가가치: weighted 다중표적 정규화, 2-표적
Pareto frontier, 전략 dispatch(exhaustive/MRO-MIP greedy/GA), robustness(FVA), 자연어 explain.

[honesty] 정규화 normalizer 명시 강제(literature_max 우선·observed_range 폴백+경고). GA(>100)는
core.search_ga 의 결정적 근사 탐색으로 분리 구현되어 있으며, non-exhaustive 전략은 근사 경고를
동반한다.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from cmig.core.search import RankedConsortium, TargetSpec


class Normalizer(enum.Enum):
    LITERATURE_MAX = "literature_max"     # 문헌 최대치 기준(데이터셋 간 비교 가능)
    OBSERVED_RANGE = "observed_range"     # 관측 범위 min-max(폴백, 데이터셋 종속 — 경고)


@dataclass(frozen=True)
class NormResult:
    value: float
    normalizer: str
    warning: str | None = None


def normalize_score(
    raw: float, *, literature_max: float | None = None,
    observed_min: float | None = None, observed_max: float | None = None,
) -> NormResult:
    """raw → [0,1]. literature_max 우선; observed_range 폴백(+경고); 둘 다 없으면 ValueError."""
    if literature_max is not None:
        if literature_max <= 0:
            raise ValueError("literature_max 는 > 0")
        return NormResult(max(0.0, min(raw / literature_max, 1.0)), Normalizer.LITERATURE_MAX.value)
    if observed_min is not None and observed_max is not None:
        if observed_max <= observed_min:
            return NormResult(0.0, Normalizer.OBSERVED_RANGE.value, "observed_range 폭 0")
        v = (raw - observed_min) / (observed_max - observed_min)
        return NormResult(
            max(0.0, min(v, 1.0)), Normalizer.OBSERVED_RANGE.value,
            "observed_range 폴백 — 데이터셋 간 비교 불가(literature_max 권고)")
    raise ValueError("normalizer 미지정: literature_max 또는 observed_range(min,max) 필요")


def weighted_multi_target(
    normalized: dict[str, float], specs: list[TargetSpec],
) -> float:
    """다중 표적 weighted 합(정규화된 [0,1] 값 × weight). 정규화 전 raw 혼합 금지."""
    by_met = {s.metabolite: s for s in specs}
    return sum(by_met[m].weight * v for m, v in normalized.items() if m in by_met)


def pareto_frontier(points: list[tuple[float, float]]) -> list[int]:
    """2-표적 비지배(non-dominated) 점 인덱스 (둘 다 최대화 가정). Pareto frontier(≤2 표적)."""
    keep: list[int] = []
    for i, (ai, bi) in enumerate(points):
        dominated = any(
            (aj >= ai and bj >= bi) and (aj > ai or bj > bi)
            for j, (aj, bj) in enumerate(points) if j != i
        )
        if not dominated:
            keep.append(i)
    return keep


class Strategy(enum.Enum):
    EXHAUSTIVE = "exhaustive"             # ≤ 20: 전수
    MRO_MIP_GREEDY = "mro_mip_greedy"     # 20–100: MRO/MIP pre-screen greedy
    GA = "ga"                             # > 100: 유전 알고리즘(근사)


def select_strategy(
    n_candidates: int, *, exhaustive_max: int = 20, greedy_max: int = 100,
) -> Strategy:
    """후보 수 → 전략 dispatch. >greedy_max 는 GA 근사 탐색."""
    if n_candidates <= exhaustive_max:
        return Strategy.EXHAUSTIVE
    if n_candidates <= greedy_max:
        return Strategy.MRO_MIP_GREEDY
    return Strategy.GA


@dataclass(frozen=True)
class PrescreenResult:
    members: tuple[str, ...]
    mip_score: int
    mro_score: float
    warning: str | None = None


def mro_mip_prescreen(
    member_exchange: dict[str, dict[str, float]],
    candidates: list[tuple[str, ...]], *, top_k: int = 10,
) -> list[PrescreenResult]:
    """MRO/MIP pre-screen greedy (20–100 후보). cross-feeding 잠재(MIP) 높고 경쟁(MRO) 낮은 순.

    [honesty] 근사(최적성 미보장) — 결과에 non-exhaustive 경고 동반.
    """
    from cmig.core.metrics import mip_pair, mro_pair, secretion_sets, uptake_sets

    upt = uptake_sets(member_exchange)
    sec = secretion_sets(member_exchange)
    scored: list[PrescreenResult] = []
    warn = "MRO/MIP greedy pre-screen — 근사(전수 아님), 상위 후보만 정밀 평가 권고"
    for members in candidates:
        if len(members) != 2:
            continue
        a, b = members
        mip = (mip_pair(sec.get(a, set()), upt.get(b, set()))
               + mip_pair(sec.get(b, set()), upt.get(a, set())))
        mro = mro_pair(upt.get(a, set()), upt.get(b, set()))
        scored.append(PrescreenResult(members, mip, mro, warn))
    # MIP 내림차순, 동률이면 MRO 오름차순(경쟁 적은 쪽 우선)
    scored.sort(key=lambda p: (-p.mip_score, p.mro_score))
    return scored[:top_k]


@dataclass(frozen=True)
class RobustnessResult:
    target: str
    fva_lo: float
    fva_hi: float
    range_width: float
    status: str
    diagnostic: str | None = None


def robustness_fva(
    community: Any, spec: TargetSpec, *, growth_fraction: float = 0.5, solver: str = "gurobi",
) -> RobustnessResult:
    """robustness = target exchange 의 FVA 범위(growth ≥ f·μ_c* 하). 좁을수록 robust.

    community FVA(core.fva) 위임. infeasible/부재 → status 노출(silent 금지).
    """
    from cmig.core.fva import FVAInfeasibleError, FVAUnavailableError, community_fva
    ex_id = spec.exchange_id()
    if ex_id not in {r.id for r in community.reactions}:
        return RobustnessResult(ex_id, 0.0, 0.0, 0.0, "missing", f"target 부재: {ex_id}")
    try:
        ranges = community_fva(
            community, reactions=[ex_id], fraction_of_optimum=growth_fraction, solver=solver)
    except (FVAUnavailableError, FVAInfeasibleError) as e:
        return RobustnessResult(ex_id, 0.0, 0.0, 0.0, "failed", str(e))
    rng = ranges[ex_id]
    return RobustnessResult(ex_id, rng.lo, rng.hi, rng.hi - rng.lo, "ok")


def explain_consortium(ranked: RankedConsortium, spec: TargetSpec) -> str:
    """랭킹된 consortium 자연어 설명(보고/GUI용)."""
    if ranked.status != "optimal":
        return f"멤버셋 {ranked.members}: solve {ranked.status} — 평가 불가"
    direction = "분비" if "secretion" in spec.direction.value else "흡수"
    return (
        f"멤버셋 {ranked.members} 는 {spec.metabolite} {direction}를 "
        f"{ranked.target_flux:.3g} (mmol/gDW/h) 까지 달성하며, 이때 군집 성장률은 "
        f"{ranked.community_growth:.3g} 이다(점수 {ranked.score:.3g})."
    )
