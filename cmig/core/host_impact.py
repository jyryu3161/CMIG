"""Host Impact — 미생물→host flux decomposition (Roadmap Phase 3.1, §12).

Design Ref: §12 (host impact) / cmig-host.design. Plan SC: SC-HI1~HI3.

미생물 community 의 lumen 분비와 host 의 lumen 흡수를 결합해 **미생물→host cross-feeding** 을
분해한다(어떤 미생물 대사체가 host 로 유입·소비되는가). 정량은 toy(정성) — Human-GEM 시 실 의미.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HostImpact:
    """미생물→host 영향 분해."""

    microbe_to_host: dict[str, float] = field(default_factory=dict)   # lumen 횡단 유입(min)
    unused_secretion: dict[str, float] = field(default_factory=dict)  # host 미사용 분비
    host_viable: bool = False
    host_biomass: float = 0.0


def host_impact(
    microbial_secretion: dict[str, float], host_result: object, *, eps: float = 1e-6,
) -> HostImpact:
    """미생물 lumen 분비(metabolite→flux>0) + host lumen 흡수 → cross-feeding 분해.

    microbe_to_host = min(분비량, host 흡수량) (실제 횡단 = 둘 중 작은 쪽).
    unused_secretion = 분비 − host 사용 (host 가 다 못 쓴 잔여, ≥0).
    """
    host_uptake = getattr(host_result, "lumen_uptake", {})
    viable = bool(getattr(host_result, "viable", False))
    biomass = float(getattr(host_result, "biomass", 0.0))

    crossing: dict[str, float] = {}
    unused: dict[str, float] = {}
    for met, secreted in microbial_secretion.items():
        if secreted <= eps:
            continue
        taken = min(secreted, abs(host_uptake.get(met, 0.0)))
        if taken > eps:
            crossing[met] = taken
        leftover = secreted - taken
        if leftover > eps:
            unused[met] = leftover
    return HostImpact(
        microbe_to_host=crossing, unused_secretion=unused,
        host_viable=viable, host_biomass=biomass)
