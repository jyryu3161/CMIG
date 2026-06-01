"""Minimal medium cardinality MILP (실제 cobra + Gurobi). FR-2.3 / §4.5."""

import pytest

pytest.importorskip("cobra")

from cmig.core.medium import (  # noqa: E402
    MILPInfeasibleError,
    MILPUnavailableError,
    MinimalMediumResult,
    limiting_nutrients,
    minimal_medium_cardinality,
)


@pytest.fixture(scope="module")
def textbook():
    import cobra

    return cobra.io.load_model("textbook")          # e_coli_core


def test_minimal_medium_cardinality_real_milp(textbook):
    """실제 cardinality MILP — e_coli_core 최소 배지(glc·nh4·pi 등 소수)."""
    res = minimal_medium_cardinality(textbook, min_objective_value=0.1)
    assert isinstance(res, MinimalMediumResult)
    assert res.n_components == len(res.components) >= 1
    assert res.components == sorted(res.components)          # 결정적 정렬
    # 글루코스가 필수 영양으로 포함
    assert any("glc" in c for c in res.components)
    assert all(c.startswith("EX_") for c in res.components)


def test_minimal_medium_is_minimal(textbook):
    """cardinality 최소 — full medium 보다 구성요소 수가 적다."""
    res = minimal_medium_cardinality(textbook, min_objective_value=0.1)
    full_uptakes = sum(1 for r in textbook.reactions
                       if r.id.startswith("EX_") and r.lower_bound < 0)
    assert res.n_components <= full_uptakes


def test_limiting_nutrients_are_components(textbook):
    res = minimal_medium_cardinality(textbook, min_objective_value=0.1)
    assert limiting_nutrients(res) == res.components


def test_infeasible_growth_raises(textbook):
    """달성 불가 성장 하한 → MILPInfeasibleError (capability 있음·해 없음, TC-8)."""
    with pytest.raises(MILPInfeasibleError):
        minimal_medium_cardinality(textbook, min_objective_value=1000.0)
    # capability 부재와 infeasible 은 별개 — infeasible 은 MILPUnavailableError 아님.
    assert not issubclass(MILPInfeasibleError, MILPUnavailableError)


def test_tc10_u_base_always_included(textbook):
    """TC-10 [MIN-MEDIUM-U]: U 기본집합 {H₂O,H⁺,Pi} 항상 포함."""
    from cmig.core.medium import DEFAULT_U_BASE
    res = minimal_medium_cardinality(textbook, min_objective_value=0.1)
    assert set(DEFAULT_U_BASE) <= set(res.components)


def test_tc10_oxygen_mode_anaerobic_excludes_o2(textbook):
    """TC-10: anaerobic → O₂ exchange 제외, aerobic 과 다른 결과."""
    from cmig.core.medium import O2_EXCHANGE
    ana = minimal_medium_cardinality(textbook, 0.1, oxygen_mode="anaerobic")
    assert O2_EXCHANGE not in ana.components
    assert ana.oxygen_mode == "anaerobic"


def test_tc10_invalid_oxygen_mode_raises(textbook):
    """TC-10: 잘못된 oxygen_mode → ValueError (fail-fast)."""
    with pytest.raises(ValueError):
        minimal_medium_cardinality(textbook, 0.1, oxygen_mode="microaerophilic")
