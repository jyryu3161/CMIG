"""Host Impact — 미생물→host flux decomposition (Roadmap Phase 3.1, §12).

Design Ref: §12 (host impact) / cmig-host.design. Plan SC: SC-HI1~HI3.

미생물 community 의 lumen 분비와 host 의 lumen 흡수를 결합해 **미생물→host cross-feeding** 을
분해한다(어떤 미생물 대사체가 host 로 유입·소비되는가). 정량은 toy(정성) — Human-GEM 시 실 의미.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeVar

from cmig.core.namespace import _normalize_metabolite_id

_V = TypeVar("_V")


def _lookup_by_metabolite(mapping: Mapping[str, _V], metabolite: str) -> _V | None:
    """Exact key first, then the namespace-normalized spelling.

    Host results may carry a metabolite under a different spelling than the microbial
    secretion dict (`lac__D` vs `lac__d`); an exact-only lookup treated such a metabolite as
    "not taken up by the host" and reported the whole secretion as unused.
    """
    if metabolite in mapping:
        return mapping[metabolite]
    wanted = _normalize_metabolite_id(metabolite)
    for key, value in mapping.items():
        if _normalize_metabolite_id(str(key)) == wanted:
            return value
    return None


@dataclass(frozen=True)
class HostImpact:
    """미생물→host 영향 분해."""

    microbe_to_host: dict[str, float] = field(default_factory=dict)   # lumen 횡단 유입(min)
    unused_secretion: dict[str, float] = field(default_factory=dict)  # host 미사용 분비
    host_viable: bool = False
    host_biomass: float = 0.0
    microbe_to_host_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    unused_secretion_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    ambiguous_metabolites: list[str] = field(default_factory=list)
    attribution_method: str = "objective_fixed_fva"


def host_impact(
    microbial_secretion: dict[str, float], host_result: object, *, eps: float = 1e-6,
) -> HostImpact:
    """미생물 lumen 분비(metabolite→flux>0) + host lumen 흡수 → cross-feeding 분해.

    microbe_to_host = min(분비량, host 흡수량) (실제 횡단 = 둘 중 작은 쪽).
    unused_secretion = 분비 − host 사용 (host 가 다 못 쓴 잔여, ≥0).
    """
    host_uptake = getattr(host_result, "lumen_uptake", {})
    host_ranges = getattr(host_result, "lumen_uptake_ranges", {})
    viable = bool(getattr(host_result, "viable", False))
    biomass = float(getattr(host_result, "biomass", 0.0))

    crossing: dict[str, float] = {}
    unused: dict[str, float] = {}
    crossing_ranges: dict[str, tuple[float, float]] = {}
    unused_ranges: dict[str, tuple[float, float]] = {}
    ambiguous: list[str] = []
    for met, secreted in microbial_secretion.items():
        if secreted <= eps:
            continue
        host_range = _lookup_by_metabolite(host_ranges, met)
        if host_range is not None:
            raw_lower, raw_upper = host_range
            lower = min(secreted, max(0.0, float(raw_lower)))
            upper = min(secreted, max(lower, float(raw_upper)))
        else:
            point = min(secreted, abs(_lookup_by_metabolite(host_uptake, met) or 0.0))
            lower = upper = point
        crossing_ranges[met] = (lower, upper)
        unused_ranges[met] = (max(0.0, secreted - upper), max(0.0, secreted - lower))
        if upper - lower <= eps:
            taken = (lower + upper) / 2.0
            if taken > eps:
                crossing[met] = taken
            leftover = secreted - taken
            if leftover > eps:
                unused[met] = leftover
        else:
            ambiguous.append(met)
    return HostImpact(
        microbe_to_host=crossing, unused_secretion=unused,
        host_viable=viable, host_biomass=biomass,
        microbe_to_host_ranges=crossing_ranges,
        unused_secretion_ranges=unused_ranges,
        ambiguous_metabolites=sorted(ambiguous),
    )
