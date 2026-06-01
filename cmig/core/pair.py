"""AN-PAIR — monoculture vs co-culture 분석 (Roadmap Phase 1.2).

Design Ref: §10 AN-PAIR / cmig-an-pair.design. Plan SC: SC-AP1~AP4.

2-member: 각 멤버 monoculture growth(single_model FBA) vs co-culture growth(micom community
member_growth) → 상호작용 유형(metrics.interaction_type)·MRO·MIP. 모든 지표는 기존 단일 진입점
(metrics·single_model·sign) 위임 — 재구현 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from cmig.core.metrics import (
    interaction_type,
    mip_pair,
    mro_pair,
    secretion_sets,
    uptake_sets,
)


@dataclass(frozen=True)
class PairResult:
    """AN-PAIR 산출. mono/co growth + 상호작용 + MRO/MIP."""

    member_a: str
    member_b: str
    mono_growth: dict[str, float]
    co_growth: dict[str, float]
    interaction: str                                  # InteractionType.value
    mro_score: float                                  # NB: 'mro' 는 type.mro 와 충돌 → mro_score
    mip: int
    co_member_exchange: dict[str, dict[str, float]]
    status: str = "ok"
    diagnostic: str | None = None


def analyze_pair(
    taxonomy: Any, *, solver: str = "gurobi", tradeoff_f: float = 0.5, engine: Any = None,
) -> PairResult:
    """2-member taxonomy → mono-vs-co + 상호작용 typing.

    co: micom community cooperative_tradeoff → member_growth.
    mono: 각 멤버 GEM 단독 FBA(single_model). 상호작용=metrics.interaction_type.
    """
    import cobra

    from cmig.core.engine import MicomEngine
    from cmig.core.single_model import solve_single_model

    ids = [str(x) for x in taxonomy["id"]]
    if len(ids) != 2:
        raise ValueError(f"AN-PAIR 은 정확히 2 멤버 (받음: {len(ids)})")
    a, b = ids
    eng = engine if engine is not None else MicomEngine()

    # co-culture
    community = eng.build_community(taxonomy, cmig_solver=solver)
    co = eng.cooperative_tradeoff(community, tradeoff_f, cmig_solver=solver)
    co_growth = {m: float(co.member_growth.get(m, 0.0) or 0.0) for m in ids}
    if co.status != "optimal" or any(not math.isfinite(v) for v in co_growth.values()):
        return PairResult(
            member_a=a, member_b=b, mono_growth={}, co_growth=co_growth,
            interaction="failed", mro_score=0.0, mip=0, co_member_exchange={},
            status="failed", diagnostic=co.diagnostic or f"co-culture status={co.status}",
        )

    # monoculture — 각 멤버 GEM 단독 FBA
    mono_growth: dict[str, float] = {}
    for m, f in zip(ids, list(taxonomy["file"]), strict=True):
        model = cobra.io.read_sbml_model(str(f))
        mono = solve_single_model(model, method="FBA", solver=solver)
        mono_growth[m] = mono.objective
        if mono.status != "optimal" or not math.isfinite(mono.objective):
            return PairResult(
                member_a=a, member_b=b, mono_growth=mono_growth, co_growth=co_growth,
                interaction="failed", mro_score=0.0, mip=0, co_member_exchange={},
                status="failed",
                diagnostic=mono.diagnostic or f"monoculture {m} status={mono.status}",
            )

    itype = interaction_type(mono_growth[a], mono_growth[b], co_growth[a], co_growth[b])

    upt = uptake_sets(co.member_exchange)
    sec = secretion_sets(co.member_exchange)
    mro = mro_pair(upt.get(a, set()), upt.get(b, set()))
    mip = (mip_pair(sec.get(a, set()), upt.get(b, set()))
           + mip_pair(sec.get(b, set()), upt.get(a, set())))

    return PairResult(
        member_a=a, member_b=b, mono_growth=mono_growth, co_growth=co_growth,
        interaction=itype.value, mro_score=mro, mip=mip,
        co_member_exchange={k: dict(v) for k, v in co.member_exchange.items()},
    )


def pair_matrix_rows(result: PairResult, *, medium_id: str = "default") -> list[dict[str, Any]]:
    """PairResult → matrix long-format 행 (medium×member×metric). build_matrix 입력."""
    rows: list[dict[str, Any]] = []
    for m in (result.member_a, result.member_b):
        mono = result.mono_growth[m]
        co = result.co_growth[m]
        rows.append({"medium_id": medium_id, "member_id": m, "metric": "mono_growth",
                     "value": mono, "label": None})
        rows.append({"medium_id": medium_id, "member_id": m, "metric": "co_growth",
                     "value": co, "label": None})
        rows.append({"medium_id": medium_id, "member_id": m, "metric": "growth_delta",
                     "value": co - mono, "label": None})
    rows.append({"medium_id": medium_id, "member_id": "__pair__", "metric": "mro",
                 "value": result.mro_score, "label": None})
    rows.append({"medium_id": medium_id, "member_id": "__pair__", "metric": "mip",
                 "value": float(result.mip), "label": None})
    rows.append({"medium_id": medium_id, "member_id": "__pair__", "metric": "interaction",
                 "value": None, "label": result.interaction})
    return rows
