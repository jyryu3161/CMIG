"""C3 — sandbox no-change 시 단일-GEM FVA range 동반. Plan SC: SC-F6.

Design Ref(foundations): §6. fva 는 호출자가 단일 cobra 모델 FVA 로 산출·주입(community FVA 아님).
"""

from __future__ import annotations

import pytest

from cmig.core.engine import SolveResult
from cmig.core.fva import FVARange
from cmig.core.sandbox import SandboxState, evaluate_sandbox


def _sr(ext):
    return SolveResult(
        objective=0.5, member_growth={"A": 0.3, "B": 0.2}, abundances={"A": 0.5, "B": 0.5},
        external_exchange=ext, member_exchange={"A": {}, "B": {}},
        status="optimal", flux_report_status="full",
        growth_solver="gurobi", flux_solver="gurobi", members=["A", "B"],
    )


def test_no_change_attaches_fva():
    """SC-F6: 변화 없음 + fva 제공 → fva_ranges 동반."""
    base = _sr({"ac": 1.0})
    same = _sr({"ac": 1.0})                       # 변화 없음
    fva = {"EX_ac_e": FVARange("EX_ac_e", -2.0, 5.0)}
    r = evaluate_sandbox(base, same, state=SandboxState.PREVIEW, fva=fva)
    assert r.no_significant_change is True
    assert r.fva_ranges == fva                    # 허용 변동 범위 동반


def test_significant_change_omits_fva():
    """변화 유의 → fva_ranges 미동반(no-change 전용)."""
    base = _sr({"ac": 1.0})
    changed = _sr({"ac": 50.0})                   # 큰 변화
    fva = {"EX_ac_e": FVARange("EX_ac_e", -2.0, 5.0)}
    r = evaluate_sandbox(base, changed, fva=fva)
    assert r.no_significant_change is False
    assert r.fva_ranges is None


def test_no_fva_provided_is_none():
    base = _sr({"ac": 1.0})
    same = _sr({"ac": 1.0})
    r = evaluate_sandbox(base, same)
    assert r.no_significant_change is True and r.fva_ranges is None


def test_real_single_gem_fva_feeds_sandbox():
    """단일-GEM FVA(cobra textbook) → sandbox 주입 통합(SC-F6 실경로)."""
    pytest.importorskip("cobra")
    import cobra

    from cmig.core.fva import flux_variability
    model = cobra.io.load_model("textbook")
    # 몇 개 exchange 의 단일-GEM FVA range 산출
    exchanges = [r.id for r in model.reactions if r.id.startswith("EX_")][:5]
    fva = flux_variability(model, reactions=exchanges, fraction_of_optimum=0.9)
    assert fva and all(rng.lo <= rng.hi for rng in fva.values())

    base = _sr({"ac": 1.0})
    same = _sr({"ac": 1.0})
    r = evaluate_sandbox(base, same, fva=fva)
    assert r.fva_ranges is not None
    assert all(isinstance(v, FVARange) for v in r.fva_ranges.values())
