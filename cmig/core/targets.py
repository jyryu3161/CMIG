"""C8 — Target metabolite readout (SCFA 등). Design Ref(foundations): §5. Plan SC: SC-F5.

관심 대사체(예: SCFA)만 profile/delta 에서 추려 요약한다. profile 은 이미 sign 정규화
(label·ui_flux 보유, §4.3 단일 진입점 경유)되어 있으므로 본 모듈은 **재분류 없이 필터만** 한다
(sign 단일진입 준수). 순수 로직 — 엔진 비의존.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TargetMetaboliteSet:
    """관심 대사체 집합 (metabolite id 기준)."""

    name: str
    metabolites: frozenset[str]

    def matches(self, metabolite: str) -> bool:
        return metabolite in self.metabolites


# Short-chain fatty acids — 문서화된 5종(plan FR-F6·design §5.1): acetate·propionate·
# butyrate·lactate(L/D)·succinate. id 는 BiGG 계열 (profile metabolite 와 매칭).
# AF-4: 문서 set 초과(formate 'for') 제거 — 계약과 정확히 일치.
SCFA = TargetMetaboliteSet(
    name="SCFA",
    metabolites=frozenset({"ac", "ppa", "but", "lac__L", "lac__D", "succ"}),
)

# 이름 → preset (CLI/GUI 선택용)
TARGET_PRESETS: dict[str, TargetMetaboliteSet] = {"scfa": SCFA}


def target_summary(
    profile_rows: Sequence[Mapping[str, Any]], target_set: TargetMetaboliteSet
) -> list[dict[str, Any]]:
    """profile rows 중 target 대사체만 추출 (이미 sign 정규화된 값 그대로).

    각 행: metabolite·net_flux·ui_flux·label (재분류 없음). metabolite 정렬.
    """
    rows = [
        {
            "metabolite": r["metabolite"],
            "net_flux": r.get("net_flux"),
            "ui_flux": r.get("ui_flux"),
            "label": r.get("label"),
        }
        for r in profile_rows
        if target_set.matches(r["metabolite"])
    ]
    return sorted(rows, key=lambda r: r["metabolite"])


def target_delta_summary(
    delta: Any, target_set: TargetMetaboliteSet
) -> list[dict[str, Any]]:
    """DeltaResult.profile 중 target 대사체만 (baseline·modified·delta). metabolite 정렬."""
    rows = [
        {
            "metabolite": d.metabolite,
            "baseline": d.baseline,
            "modified": d.modified,
            "delta": d.delta,
        }
        for d in delta.profile
        if target_set.matches(d.metabolite)
    ]
    return sorted(rows, key=lambda r: r["metabolite"])
