"""Phase 3.1 — Host-Microbe (config B, toy host). Plan SC: SC-HM1~HM6·HI1~HI3.

synthetic toy host(정성 — Human-GEM 아님)로 2-interface sign·viability·host impact 검증.
config B 확정: micom 0.39.0 Community 에 host 파라미터 없음(probe) → CMIG 2-compartment.
"""

from __future__ import annotations

import pytest

pytest.importorskip("cobra")

from cmig.core.host import (  # noqa: E402
    InterfaceFlux,
    classify_host_exchanges,
    solve_host,
)
from cmig.core.host_impact import host_impact  # noqa: E402
from cmig.synthetic_host import build_host_model, lumen_availability_from_pair  # noqa: E402


def test_host_viable_on_microbial_scfa():
    """SC-HM1: 미생물 SCFA(lumen ac+but) → host viable + biomass>0 + SCFA 흡수."""
    r = solve_host(build_host_model(), lumen_availability_from_pair(),
                   maintenance_flux=1.0, solver="gurobi")
    assert r.viable and r.status == "optimal"
    assert r.biomass > 0
    assert abs(r.lumen_uptake.get("ac", 0.0) - 8.0) < 1e-3      # 미생물→host acetate
    assert abs(r.lumen_uptake.get("but", 0.0) - 4.0) < 1e-3     # 미생물→host butyrate


def test_two_interface_classification():
    """SC-HM2: 2-interface(lumen/blood) sign 분류 — sign 단일 진입점."""
    r = solve_host(build_host_model(), lumen_availability_from_pair(), solver="gurobi")
    ifaces = {f.interface for f in r.interface_fluxes}
    assert ifaces == {"lumen", "blood"}
    ac = next(f for f in r.interface_fluxes if f.metabolite == "ac" and f.interface == "lumen")
    assert ac.label == "uptake" and ac.flux < 0                 # 미생물 SCFA 흡수


def test_classify_host_exchanges_direct():
    """SC-HM2: classify_host_exchanges 직접(순수)."""
    rows = classify_host_exchanges(
        {"EX_ac_lumen": -8.0, "EX_co2_blood": 5.0, "EX_x_e": 1.0, "ATPM": 1.0})
    assert all(isinstance(f, InterfaceFlux) for f in rows)
    by = {f.exchange_id: f for f in rows}
    assert by["EX_ac_lumen"].interface == "lumen" and by["EX_ac_lumen"].label == "uptake"
    assert by["EX_co2_blood"].interface == "blood" and by["EX_co2_blood"].label == "secretion"
    assert "EX_x_e" not in by                                    # 비 host-interface 제외


def test_host_non_viable_without_microbiome():
    """SC-HM3: 미생물 SCFA 없음(lumen=0, 탄소원 부재) → host **non-viable** + phantom 흡수 없음.

    colonocyte 가 미생물 butyrate 에 의존 → 미생물 없으면 비viable(정성 의존성). phantom 흡수도 0.
    """
    r = solve_host(build_host_model(), {}, maintenance_flux=1.0, solver="gurobi")
    assert not r.viable and r.status == "infeasible"            # 미생물 없으면 host 사멸
    assert r.lumen_uptake == {}                                  # phantom 흡수 없음(정직성)


def test_host_non_viable_explicit():
    """SC-HM4: maintenance > 공급 → non-viable + 구조화 infeasible diagnostic(silent 위장 금지)."""
    r = solve_host(build_host_model(), {}, maintenance_flux=500.0, solver="gurobi")
    assert not r.viable and r.status == "infeasible"
    assert r.diagnostic is not None and "infeasible" in r.diagnostic


def test_host_not_in_community_objective():
    """SC-HM5: host 는 군집 성장 목적 미포함 — 자체 목적(biomass)·maintenance 가 viability."""
    host = build_host_model()
    # host objective = BIOMASS_host (community growth 아님)
    from cobra.util.solver import linear_reaction_coefficients
    obj = [r.id for r in linear_reaction_coefficients(host)]
    assert obj == ["BIOMASS_host"]


def test_host_impact_decomposition():
    """SC-HI1: 미생물 분비 + host 흡수 → microbe_to_host cross-feeding 분해(둘 다 사용)."""
    res = solve_host(build_host_model(), lumen_availability_from_pair(), solver="gurobi")
    impact = host_impact({"ac": 8.0, "but": 4.0}, res)
    assert impact.host_viable
    assert abs(impact.microbe_to_host.get("ac", 0.0) - 8.0) < 1e-3   # acetate 횡단
    assert abs(impact.microbe_to_host.get("but", 0.0) - 4.0) < 1e-3  # butyrate 횡단


def test_run_host_microbe_end_to_end():
    """SC-HI2: end-to-end — 실 micom community(synthetic pair) 분비 → host (orphan 아님)."""
    pytest.importorskip("micom")
    import tempfile

    from cmig.core.host import run_host_microbe
    from cmig.synthetic_pair import build_pair_taxonomy

    with tempfile.TemporaryDirectory() as td:
        tax = build_pair_taxonomy(td)
        host_res, impact = run_host_microbe(
            tax, build_host_model(), solver="gurobi", tradeoff_f=0.5)
    # 실 community 는 butyrate(6.25) 분비 → host 가 흡수해 viable
    assert host_res.viable
    assert impact.microbe_to_host.get("but", 0.0) > 1.0             # 미생물→host butyrate 횡단


def test_host_lp_gate():
    """SC-HM6: LP 부재 → fail-fast(osqp qp_only)."""
    from cmig.core.single_model import SingleModelUnavailableError
    with pytest.raises(SingleModelUnavailableError):
        solve_host(build_host_model(), {"ac": 1.0}, solver="osqp")
