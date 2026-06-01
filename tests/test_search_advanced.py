"""Phase 3.5/3.6 — search 고급(정규화·Pareto·전략·robustness·explain). Plan SC: SC-SA1~SA7.

대부분 순수 함수(micom 불요)·결정적. robustness 만 micom fixture.
"""

from __future__ import annotations

import pytest

from cmig.core.search import Direction, RankedConsortium, TargetSpec
from cmig.core.search_advanced import (
    Normalizer,
    Strategy,
    explain_consortium,
    mro_mip_prescreen,
    normalize_score,
    pareto_frontier,
    select_strategy,
    weighted_multi_target,
)


def test_normalize_literature_max():
    """SC-SA1: literature_max 정규화 → [0,1], clamp."""
    r = normalize_score(8.0, literature_max=10.0)
    assert abs(r.value - 0.8) < 1e-9 and r.normalizer == Normalizer.LITERATURE_MAX.value
    assert normalize_score(20.0, literature_max=10.0).value == 1.0   # clamp


def test_normalize_observed_fallback_warns():
    """SC-SA1: observed_range 폴백 → 경고(데이터셋 종속 honesty)."""
    r = normalize_score(5.0, observed_min=0.0, observed_max=10.0)
    assert abs(r.value - 0.5) < 1e-9 and r.warning is not None


def test_normalize_requires_normalizer():
    """SC-SA1: normalizer 미지정 → ValueError(강제)."""
    with pytest.raises(ValueError, match="normalizer"):
        normalize_score(5.0)


def test_weighted_multi_target():
    """SC-SA2: 정규화 값 × weight 합."""
    specs = [TargetSpec("ac", weight=2.0), TargetSpec("but", weight=1.0)]
    s = weighted_multi_target({"ac": 0.5, "but": 1.0}, specs)
    assert abs(s - (2.0 * 0.5 + 1.0 * 1.0)) < 1e-9


def test_pareto_frontier():
    """SC-SA3: 2-표적 비지배 점 (둘 다 최대화)."""
    pts = [(1.0, 1.0), (2.0, 1.0), (1.0, 2.0), (2.0, 2.0), (0.5, 0.5)]
    keep = pareto_frontier(pts)
    assert 3 in keep                      # (2,2) 지배적
    assert 4 not in keep                  # (0.5,0.5) 지배됨
    # 단일 비지배: (2,2) 가 모두 지배 → frontier={3}
    assert keep == [3]


def test_pareto_tradeoff_points():
    """SC-SA3: trade-off frontier (서로 비지배)."""
    pts = [(3.0, 1.0), (1.0, 3.0), (2.0, 2.0)]
    keep = pareto_frontier(pts)
    assert set(keep) == {0, 1, 2}         # 셋 다 비지배(trade-off)


def test_select_strategy():
    """SC-SA4: 후보 수 → 전략 dispatch."""
    assert select_strategy(10) == Strategy.EXHAUSTIVE
    assert select_strategy(50) == Strategy.MRO_MIP_GREEDY
    assert select_strategy(500) == Strategy.GA


def test_mro_mip_prescreen():
    """SC-SA5: MRO/MIP greedy pre-screen — MIP 높은 순 + 근사 경고."""
    me = {
        "a": {"ac": 5.0, "glc": -10.0},     # ac 분비, glc 흡수
        "b": {"ac": -3.0, "but": 4.0},      # ac 흡수, but 분비
        "c": {"glc": -8.0},                 # glc 흡수(a 와 경쟁)
    }
    res = mro_mip_prescreen(me, [("a", "b"), ("a", "c"), ("b", "c")], top_k=3)
    assert res[0].members == ("a", "b")     # a→b acetate cross-feeding(MIP=1) 최상
    assert all(r.warning is not None for r in res)   # 근사 경고


def test_explain_consortium():
    """SC-SA7: 자연어 설명."""
    rc = RankedConsortium(("a", "b"), score=16.7, target_flux=16.7,
                          community_growth=0.22, status="optimal")
    text = explain_consortium(rc, TargetSpec("ac", Direction.MAX_SECRETION))
    assert "ac" in text and "분비" in text and "16.7" in text


def test_explain_non_optimal():
    rc = RankedConsortium(("a", "b"), score=float("-inf"), target_flux=0.0,
                          community_growth=0.0, status="infeasible")
    assert "infeasible" in explain_consortium(rc, TargetSpec("ac"))


def test_robustness_fva_fixture():
    """SC-SA6: robustness = target FVA 범위(micom fixture)."""
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.core.search_advanced import robustness_fva
    from cmig.golden_fixture import build_taxonomy

    eng = MicomEngine()
    comm = eng.build_community(build_taxonomy(), cmig_solver="gurobi")
    r = robustness_fva(comm, TargetSpec("ac"), growth_fraction=0.5, solver="gurobi")
    assert r.status == "ok"
    assert r.fva_lo <= r.fva_hi and r.range_width >= 0
