"""AN-DELTA — compute_delta. Plan SC: SC-9 (delta)."""

import pytest

from cmig.core.delta import compute_delta
from cmig.core.engine import SolveResult


def _result(members, external, growth=0.5):
    return SolveResult(
        objective=growth,
        member_growth={m: growth for m in members},
        abundances={m: 1.0 / len(members) for m in members},
        external_exchange=external,
        member_exchange={m: {} for m in members},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=list(members),
    )


def test_profile_delta_values():
    base = _result(["A"], {"ac": 5.0, "glc": -10.0}, growth=0.4)
    mod = _result(["A", "B"], {"ac": 8.0, "glc": -10.0, "but": 2.0}, growth=0.45)
    d = compute_delta(base, mod)
    by = {m.metabolite: m for m in d.profile}
    assert by["ac"].delta == 3.0           # 5 → 8
    assert by["glc"].delta == 0.0          # 변화 없음
    assert by["but"].delta == 2.0          # 0 → 2 (신규)
    assert round(d.growth_delta, 4) == 0.05


def test_added_removed_members():
    base = _result(["A", "B"], {"ac": 5.0})
    mod = _result(["A", "B", "C"], {"ac": 5.0})
    d = compute_delta(base, mod)
    assert d.added_members == ["C"]
    assert d.removed_members == []


def test_significant_filters_by_threshold():
    base = _result(["A"], {"ac": 5.0, "co2": 1.0})
    mod = _result(["A"], {"ac": 8.0, "co2": 1.0 + 1e-9})
    d = compute_delta(base, mod)
    sig = d.significant(threshold=1e-6)
    assert [m.metabolite for m in sig] == ["ac"]   # co2 변화는 임계 이하


@pytest.mark.parametrize("micom_needed", [True])
def test_real_add_member_delta(micom_needed):
    """SC-9 통합: 실제 2→3 member community 의 add-member delta."""
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.golden_fixture import TRADEOFF_F, build_taxonomy

    eng = MicomEngine()
    tax3 = build_taxonomy()                 # 3 member
    tax2 = tax3.iloc[:2].copy()             # 2 member (baseline)
    base = eng.cooperative_tradeoff(eng.build_community(tax2, "gurobi"), TRADEOFF_F,
                                    cmig_solver="gurobi")
    mod = eng.cooperative_tradeoff(eng.build_community(tax3, "gurobi"), TRADEOFF_F,
                                   cmig_solver="gurobi")
    d = compute_delta(base, mod)
    assert len(d.added_members) == 1        # 멤버 1개 추가 감지
    assert d.removed_members == []
    assert len(d.profile) > 0
