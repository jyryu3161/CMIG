"""CMIG-MRO / CMIG-MIP / interaction typing (CMIG-defined 지표).

Design Ref: §4.5 (CMIG-MIP/MRO) · §10 AN-PAIR (interaction typing) / FR-2.4.
순수 로직 — 멤버 exchange/growth 로부터 산출(엔진 비의존, 테스트 가능).

- **MRO** (Metabolic Resource Overlap, 영양 중복): 멤버들이 공통으로 흡수하는 자원 비율.
- **MIP** (Metabolic Interaction Potential, cross-feeding 잠재): 한 멤버가 분비하고 다른
  멤버가 흡수 가능한 대사체 수(잠재 cross-feeding donation).
- **interaction typing**: monoculture vs co-culture growth 변화로 상호작용 유형 분류.
"""

from __future__ import annotations

import enum
import itertools
from collections.abc import Mapping

from cmig.core.sign import NOISE_FLOOR, Label, classify

# member_id → 흡수(uptake)/분비(secretion) 대사체 집합
MetaboliteSets = Mapping[str, set[str]]


def _pairs(members: list[str]) -> list[tuple[str, str]]:
    return list(itertools.combinations(sorted(members), 2))


def uptake_sets(
    member_exchange: Mapping[str, Mapping[str, float]], eps: float = NOISE_FLOOR
) -> dict[str, set[str]]:
    """member_exchange(raw) → 멤버별 흡수 대사체 집합 (TC-16: sign.classify 단일진입 경유)."""
    return {
        m: {x for x, v in ex.items() if classify(v, eps) is Label.UPTAKE}
        for m, ex in member_exchange.items()
    }


def secretion_sets(
    member_exchange: Mapping[str, Mapping[str, float]], eps: float = NOISE_FLOOR
) -> dict[str, set[str]]:
    """member_exchange(raw) → 멤버별 분비 대사체 집합 (TC-16: sign.classify 단일진입 경유)."""
    return {
        m: {x for x, v in ex.items() if classify(v, eps) is Label.SECRETION}
        for m, ex in member_exchange.items()
    }


def mro_pair(a_uptake: set[str], b_uptake: set[str]) -> float:
    """MRO(쌍) = Jaccard(흡수 집합) = |A∩B| / |A∪B|. 영양 경쟁/중복 정도."""
    union = a_uptake | b_uptake
    if not union:
        return 0.0
    return len(a_uptake & b_uptake) / len(union)


def mro_community(uptakes: MetaboliteSets) -> float:
    """MRO(community) = 평균 쌍별 MRO. 멤버 1개 이하면 0."""
    members = list(uptakes)
    pairs = _pairs(members)
    if not pairs:
        return 0.0
    return sum(mro_pair(uptakes[a], uptakes[b]) for a, b in pairs) / len(pairs)


def mip_pair(donor_secretion: set[str], recipient_uptake: set[str]) -> int:
    """MIP(donor→recipient) = donor 분비 ∩ recipient 흡수 수 (잠재 cross-feeding)."""
    return len(donor_secretion & recipient_uptake)


def mip_community(secretions: MetaboliteSets, uptakes: MetaboliteSets) -> int:
    """MIP(community) = 모든 순서쌍의 잠재 donation 합 (방향성)."""
    members = list(set(secretions) | set(uptakes))
    total = 0
    for d in members:
        for r in members:
            if d == r:
                continue
            total += mip_pair(secretions.get(d, set()), uptakes.get(r, set()))
    return total


class InteractionType(enum.Enum):
    """AN-PAIR 상호작용 유형 (co vs mono growth 부호 쌍)."""

    MUTUALISM = "mutualism"          # (+,+) 협력
    COMPETITION = "competition"      # (−,−)
    COMMENSALISM = "commensalism"    # (+,0)
    AMENSalism = "amensalism"        # (−,0)
    PARASITISM = "parasitism"        # (+,−) / (−,+)
    NEUTRALISM = "neutralism"        # (0,0)


def _sign(delta: float, eps: float) -> int:
    if delta > eps:
        return 1
    if delta < -eps:
        return -1
    return 0


def interaction_type(
    mono_a: float, mono_b: float, co_a: float, co_b: float, eps: float = 1e-6
) -> InteractionType:
    """monoculture vs co-culture growth 변화 → 상호작용 유형 (§10 AN-PAIR)."""
    sa, sb = _sign(co_a - mono_a, eps), _sign(co_b - mono_b, eps)
    signs = {sa, sb}
    if signs == {1}:
        return InteractionType.MUTUALISM
    if signs == {-1}:
        return InteractionType.COMPETITION
    if signs == {0}:
        return InteractionType.NEUTRALISM
    if signs == {1, 0}:
        return InteractionType.COMMENSALISM
    if signs == {-1, 0}:
        return InteractionType.AMENSalism
    return InteractionType.PARASITISM   # {1, -1}
