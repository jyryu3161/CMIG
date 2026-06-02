"""Phase 3.1 — Host-Microbe (config B, toy host). Plan SC: SC-HM1~HM6·HI1~HI3.

synthetic toy host(정성 — Human-GEM 아님)로 2-interface sign·viability·host impact 검증.
config B 확정: micom 0.39.0 Community 에 host 파라미터 없음(probe) → CMIG 2-compartment.
"""

from __future__ import annotations

import pytest

pytest.importorskip("cobra")

from cmig.core.host import (  # noqa: E402
    InterfaceFlux,
    benchmark_generic_host,
    classify_host_exchanges,
    run_bigg_host_microbe,
    solve_bigg_host,
    solve_host,
)
from cmig.core.host_impact import host_impact  # noqa: E402
from cmig.synthetic_host import build_host_model, lumen_availability_from_pair  # noqa: E402


def _bigg_host_model():
    from cobra import Metabolite, Model, Reaction

    def met(mid):
        return Metabolite(mid, compartment="e" if mid.endswith("_e") else "c")

    def rxn(rid, stoich, bounds):
        r = Reaction(rid)
        r.add_metabolites({met(mid): coef for mid, coef in stoich.items()})
        r.bounds = bounds
        return r

    model = Model("bigg_style_host")
    model.add_reactions([
        rxn("EX_but_e", {"but_e": -1}, (0, 1000)),
        rxn("EX_o2_e", {"o2_e": -1}, (0, 1000)),
        rxn("EX_co2_e", {"co2_e": -1}, (0, 1000)),
        rxn("BUTt", {"but_e": -1, "but_c": 1}, (-1000, 1000)),
        rxn("O2t", {"o2_e": -1, "o2_c": 1}, (-1000, 1000)),
        rxn("CO2t", {"co2_c": -1, "co2_e": 1}, (-1000, 1000)),
        rxn("BUT_OX", {"but_c": -1, "o2_c": -2, "co2_c": 1, "atp_c": 4}, (0, 1000)),
        rxn("BIOMASS_host", {"atp_c": -1}, (0, 1000)),
    ])
    model.objective = "BIOMASS_host"
    return model


def _zero_biomass_maintenance_host():
    from cobra import Metabolite, Model, Reaction

    atp = Metabolite("atp_c", compartment="c")
    biomass = Metabolite("biomass_c", compartment="c")
    model = Model("zero_biomass_host")
    src = Reaction("ATP_SRC")
    src.add_metabolites({atp: 1})
    src.bounds = (0, 1000)
    atpm = Reaction("ATPM")
    atpm.add_metabolites({atp: -1})
    atpm.bounds = (0, 1000)
    bio = Reaction("BIOMASS_host")
    bio.add_metabolites({biomass: -1})
    bio.bounds = (0, 1000)
    model.add_reactions([src, atpm, bio])
    model.objective = "BIOMASS_host"
    return model


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


def test_host_feasible_zero_objective_is_not_viable():
    """Optimal but zero objective is non-viable across host solve paths."""
    result = solve_host(_zero_biomass_maintenance_host(), {}, maintenance_flux=1.0)
    assert result.status == "optimal"
    assert result.biomass == 0.0
    assert result.viable is False


def test_host_rejects_negative_lumen_availability():
    with pytest.raises(ValueError, match="non-negative"):
        solve_host(build_host_model(), {"ac": -1.0}, solver="gurobi")


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


def test_bigg_host_direct_coupling_uses_shared_ids():
    """BiGG ids: microbial but -> host EX_but_e without a manual mapping table."""
    res = solve_bigg_host(
        _bigg_host_model(),
        {"but": 4.0},
        host_medium={"o2": 20.0},
        solver="gurobi",
    )
    assert res.status == "optimal" and res.viable
    assert abs(res.lumen_uptake.get("but", 0.0) - 4.0) < 1e-6
    assert any(f.exchange_id == "EX_but_e" for f in res.interface_fluxes)


def test_bigg_host_background_medium_does_not_inflate_microbe_transfer():
    """Background host medium can add uptake capacity, but microbial transfer remains capped."""
    res = solve_bigg_host(
        _bigg_host_model(),
        {"but": 4.0},
        host_medium={"but": 10.0, "o2": 100.0},
        solver="gurobi",
    )
    assert res.status == "optimal"
    assert abs(res.lumen_uptake.get("but", 0.0) - 4.0) < 1e-6
    total_but = next(f for f in res.interface_fluxes if f.exchange_id == "EX_but_e")
    assert abs(total_but.flux + 14.0) < 1e-6


def test_bigg_host_rejects_invalid_availability():
    """Negative/NaN-style availability must fail instead of being abs() corrected."""
    with pytest.raises(ValueError, match="non-negative"):
        solve_bigg_host(
            _bigg_host_model(),
            {"but": -4.0},
            host_medium={"o2": 20.0},
            solver="gurobi",
        )


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


def test_run_bigg_host_microbe_end_to_end():
    """실 MICOM pair secretion -> BiGG host EX_but_e direct coupling."""
    pytest.importorskip("micom")
    import tempfile

    from cmig.synthetic_pair import build_pair_taxonomy

    with tempfile.TemporaryDirectory() as td:
        tax = build_pair_taxonomy(td)
        result = run_bigg_host_microbe(
            tax,
            _bigg_host_model(),
            solver="gurobi",
            tradeoff_f=0.5,
            host_medium={"o2": 100.0},
        )
    assert result.host_result.viable
    assert result.matched_exchanges["but"] == "EX_but_e"
    assert result.impact.microbe_to_host.get("but", 0.0) > 1.0


def test_host_osqp_hybrid_restores_bounds():
    """SC-HM6: osqp hybrid LP 경로가 동작하고 host solve bound 변경을 모델에 남기지 않는다."""
    host = build_host_model()
    before = {
        rid: host.reactions.get_by_id(rid).bounds
        for rid in ("EX_ac_lumen", "ATPM")
    }
    result = solve_host(host, {"ac": 1.0}, solver="osqp")
    assert result.status in ("optimal", "infeasible")
    after = {
        rid: host.reactions.get_by_id(rid).bounds
        for rid in ("EX_ac_lumen", "ATPM")
    }
    assert after == before


def test_generic_host_benchmark_reports_scale_and_readiness():
    """Human-GEM 정량 coupling 전 benchmark 계약: 시간/메모리/readiness를 명시한다."""
    import os

    import cobra
    import micom

    model = cobra.io.read_sbml_model(
        os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
    )
    result = benchmark_generic_host(model, solver="gurobi")
    assert result.summary.n_reactions == 95
    assert result.solve_seconds >= 0.0
    assert result.peak_memory_mb >= 0.0
    assert result.quantitative_coupling_ready is False
    assert any("mapping" in w for w in result.warnings)
