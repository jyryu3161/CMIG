"""Phase 1.1 — AN-SINGLE 단일 GEM 분석. Plan SC: SC-AS1~AS6.

micom 번들 e_coli_core (95 reactions·20 exchanges, FBA obj≈0.8739) 로 실 검증.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("micom")
pytest.importorskip("cobra")

import cobra  # noqa: E402
import micom  # noqa: E402

from cmig.core.single_model import (  # noqa: E402
    SingleModelResult,
    exchange_summary,
    growth_feasible,
    single_gene_knockout,
    single_model_fva,
    single_reaction_knockout,
    solve_single_model,
)

_MODEL_PATH = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")


def _model() -> cobra.Model:
    return cobra.io.read_sbml_model(_MODEL_PATH)


def test_fba_optimal():
    """SC-AS1: FBA — obj≈0.8739, status optimal, 95 fluxes."""
    res = solve_single_model(_model(), method="FBA", solver="gurobi")
    assert isinstance(res, SingleModelResult)
    assert res.status == "optimal"
    assert abs(res.objective - 0.8739) < 1e-2
    assert len(res.fluxes) == 95


def test_pfba_matches_objective():
    """SC-AS1: pFBA — 동일 growth(obj) 하 총 flux 최소화. growth ≈ FBA."""
    res = solve_single_model(_model(), method="pFBA", solver="gurobi")
    assert res.status == "optimal"
    assert abs(res.objective - 0.8739) < 1e-2
    assert res.method == "pFBA"


def test_single_model_fva_brackets_growth():
    """SC-AS2: FVA — biomass reaction 범위 lo≤hi, fraction_of_optimum=1 이면 lo≈hi≈opt."""
    ranges = single_model_fva(_model(), fraction_of_optimum=1.0, solver="gurobi")
    assert len(ranges) == 95
    bio = next(r for rid, r in ranges.items() if "BIOMASS" in rid.upper())
    assert bio.lo <= bio.hi
    assert abs(bio.hi - 0.8739) < 1e-2


def test_reaction_knockout_lowers_growth():
    """SC-AS3: 필수 반응 knockout → growth 감소(또는 0). bound 자동 복원."""
    model = _model()
    base = solve_single_model(model, solver="gurobi").objective
    # ENO(enolase) 는 e_coli_core 필수 반응 — knockout 시 growth 급감
    ko = single_reaction_knockout(model, "ENO", solver="gurobi")
    assert ko.objective < base - 1e-6
    # 복원 확인 — 동일 모델 재solve 시 base 회복
    assert abs(solve_single_model(model, solver="gurobi").objective - base) < 1e-6


def test_gene_knockout():
    """SC-AS3: 유전자 knockout (GPR 반영)."""
    model = _model()
    g = next(iter(model.genes)).id
    res = single_gene_knockout(model, g, solver="gurobi")
    assert res.status in ("optimal", "infeasible")


def test_exchange_summary_directions():
    """SC-AS4: exchange 요약 — 방향(sign 단일 진입점). glucose 흡수·acetate/co2 등."""
    rows = exchange_summary(_model(), solver="gurobi")
    assert len(rows) == 20
    dirs = {r["direction"] for r in rows}
    assert dirs <= {"uptake", "secretion", "inactive"}
    # glucose exchange 는 흡수(uptake, flux<0)
    glc = next(r for r in rows if r["reaction_id"] == "EX_glc__D_e")
    assert glc["direction"] == "uptake" and glc["flux"] < 0


def test_growth_feasible():
    """SC-AS5: growth feasibility — e_coli_core 는 성장 가능."""
    assert growth_feasible(_model(), solver="gurobi") is True


def test_invalid_method_rejected():
    with pytest.raises(ValueError, match="method"):
        solve_single_model(_model(), method="MILP")
