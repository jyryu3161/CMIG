"""Synthetic toy host GEM — host-microbe 정성 검증 fixture (§12).

synthetic_pair 와 동일 철학: **실제 Human-GEM 아님 · 종명 없음 · 정량 해석 금지**(정성 2-interface·
viability 검증용). 실 정량/스케일 검증은 Human-GEM(10k+ rxn) 필요 — toy 는 구현·계약 검증 한정.

host 구조(colonocyte-like): lumen interface(장관, 미생물 SCFA: acetate/butyrate 가 **유일 탄소원**)
+ blood interface(전신, O2/CO2만) → ATP 생산 → **ATP maintenance(viability 제약)** + host biomass
(군집 목적 미포함). 생물학적 근거: 대장세포(colonocyte)는 미생물 butyrate 를 주 에너지원으로 의존
→ 미생물 없으면 host 비viable(미생물-host 의존성을 정성 재현).
"""

from __future__ import annotations

from typing import Any

# host 유지(viability) 최소 ATP maintenance flux
HOST_MAINTENANCE = 1.0


def _met(mid: str, compartment: str) -> Any:
    from cobra import Metabolite
    return Metabolite(mid, compartment=compartment)


def _rxn(rid: str, stoich: dict[str, tuple[str, float]], bounds: tuple[float, float]) -> Any:
    from cobra import Reaction
    r = Reaction(rid)
    r.add_metabolites({_met(mid, comp): coef for mid, (comp, coef) in stoich.items()})
    r.bounds = bounds
    return r


def build_host_model() -> Any:
    """toy host cobra Model. lumen(SCFA)·blood(glc/O2) 2-interface + ATPM(viability) + biomass."""
    from cobra import Model

    m = Model("synthetic_host")
    m.add_reactions([
        # --- lumen interface (장관, 미생물 SCFA = 유일 탄소원) ---
        _rxn("EX_ac_lumen", {"ac_lumen": ("lumen", -1)}, (-10, 0)),     # acetate 흡수(미생물)
        _rxn("EX_but_lumen", {"but_lumen": ("lumen", -1)}, (-10, 0)),   # butyrate 흡수(미생물)
        # --- blood interface (전신: O2/CO2만, 탄소원 없음) ---
        _rxn("EX_o2_blood", {"o2_blood": ("blood", -1)}, (-100, 0)),    # O2 흡수(혈액, 풍부)
        _rxn("EX_co2_blood", {"co2_blood": ("blood", -1)}, (0, 1000)),  # CO2 분비(혈액)
        # --- 내부 수송 ---
        _rxn("ACtr", {"ac_lumen": ("lumen", -1), "ac_c": ("c", 1)}, (-1000, 1000)),
        _rxn("BUTtr", {"but_lumen": ("lumen", -1), "but_c": ("c", 1)}, (-1000, 1000)),
        _rxn("O2tr", {"o2_blood": ("blood", -1), "o2_c": ("c", 1)}, (-1000, 1000)),
        _rxn("CO2tr", {"co2_c": ("c", -1), "co2_blood": ("blood", 1)}, (-1000, 1000)),
        # acetate + 2 O2 → 2 ATP + CO2
        _rxn("AC_OX", {"ac_c": ("c", -1), "o2_c": ("c", -2), "atp_c": ("c", 2),
                       "co2_c": ("c", 1)}, (0, 1000)),
        # butyrate + 5 O2 → 5 ATP + CO2 (colonocyte 주 에너지원)
        _rxn("BUT_OX", {"but_c": ("c", -1), "o2_c": ("c", -5), "atp_c": ("c", 5),
                        "co2_c": ("c", 1)}, (0, 1000)),
        # --- viability: ATP maintenance (소비) ---
        _rxn("ATPM", {"atp_c": ("c", -1)}, (HOST_MAINTENANCE, 1000)),
        # --- host biomass (군집 목적 미포함 — host 자체 목적) ---
        _rxn("BIOMASS_host", {"atp_c": ("c", -1)}, (0, 1000)),
    ])
    m.objective = "BIOMASS_host"
    return m


def lumen_availability_from_pair() -> dict[str, float]:
    """synthetic_pair 미생물(acetate/butyrate 분비)의 lumen 가용량(정성 toy 값)."""
    return {"ac": 8.0, "but": 4.0}
