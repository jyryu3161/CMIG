"""C8 — Target metabolite readout (SCFA 등). Design Ref(foundations): §5. Plan SC: SC-F5.

관심 대사체(예: SCFA)만 profile/delta 에서 추려 요약한다. profile 은 이미 sign 정규화
(label·ui_flux 보유, §4.3 단일 진입점 경유)되어 있으므로 본 모듈은 **재분류 없이 필터만** 한다
(sign 단일진입 준수). 순수 로직 — 엔진 비의존.
"""

from __future__ import annotations

import re
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

# 결정적 preset 순서 (CLI --target-preset → --targets 확장에 사용; set 순회 비결정성 차단).
def preset_targets(name: str) -> list[str]:
    """preset 이름 → 정렬된 metabolite id 목록. 미등록 이름은 ValueError."""
    preset = TARGET_PRESETS.get(name)
    if preset is None:
        raise ValueError(
            f"unknown target preset: {name!r} (available: {sorted(TARGET_PRESETS)})"
        )
    return sorted(preset.metabolites)


_FORMULA_ELEMENT = re.compile(r"([A-Z][a-z]?)(\d*)")


def parse_carbon_number(formula: str | None) -> int | None:
    """화학식 → 탄소 원자 수. 판독 불가/탄소 없음은 None (0 과 구별한다).

    'C2H3O2' → 2, 'C4H7O2' → 4, 'CH4' → 1. SCFA 총량을 mmol 단순합으로 더하는 것은
    화학적으로 의미가 없으므로(아세트산 C2 vs 부티르산 C4) carbon-equivalent 가중에 쓰인다.
    formula 가 비었거나 탄소를 포함하지 않으면 None — 호출자가 "모른다"를 조용히 0 으로
    바꾸지 않도록 한다.
    """
    if not formula:
        return None
    text = str(formula).strip()
    if not text:
        return None
    position = 0
    carbon: int | None = None
    for match in _FORMULA_ELEMENT.finditer(text):
        if match.start() != position:      # 판독하지 못한 구간 → 신뢰할 수 없는 식
            return None
        position = match.end()
        element, count = match.group(1), match.group(2)
        if element == "C":
            carbon = (carbon or 0) + (int(count) if count else 1)
    if position != len(text):
        return None
    return carbon


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
