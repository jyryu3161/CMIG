"""CMIG-MRO/MIP + interaction typing (순수). FR-2.4 / §4.5·§10 AN-PAIR."""

from cmig.core.metrics import (
    InteractionType,
    interaction_type,
    mip_community,
    mip_pair,
    mro_community,
    mro_pair,
    secretion_sets,
    uptake_sets,
)


def test_uptake_secretion_sets():
    mex = {"A": {"glc": -10.0, "ac": 5.0}, "B": {"glc": -8.0, "but": 3.0}}
    assert uptake_sets(mex) == {"A": {"glc"}, "B": {"glc"}}
    assert secretion_sets(mex) == {"A": {"ac"}, "B": {"but"}}


def test_mro_pair_jaccard():
    assert mro_pair({"a", "b", "c"}, {"b", "c", "d"}) == 0.5     # ∩=2, ∪=4
    assert mro_pair({"a"}, {"a"}) == 1.0
    assert mro_pair(set(), set()) == 0.0
    assert mro_pair({"a"}, {"b"}) == 0.0


def test_mro_community_mean_pairwise():
    uptakes = {"A": {"glc", "o2"}, "B": {"glc", "o2"}, "C": {"glc"}}
    # pairs: AB=1.0, AC=0.5, BC=0.5 → mean=2/3
    assert round(mro_community(uptakes), 4) == round(2 / 3, 4)
    assert mro_community({"A": {"x"}}) == 0.0                    # 1 멤버 → 0


def test_mip_pair_and_community():
    assert mip_pair({"ac", "co2"}, {"ac", "glc"}) == 1          # ac 만 겹침
    sec = {"A": {"ac"}, "B": set()}
    upt = {"A": set(), "B": {"ac"}}
    assert mip_community(sec, upt) == 1                          # A→B ac 잠재 donation


def test_interaction_types_all_categories():
    base = dict(mono_a=0.5, mono_b=0.5)
    assert interaction_type(**base, co_a=0.6, co_b=0.6) is InteractionType.MUTUALISM
    assert interaction_type(**base, co_a=0.4, co_b=0.4) is InteractionType.COMPETITION
    assert interaction_type(**base, co_a=0.5, co_b=0.5) is InteractionType.NEUTRALISM
    assert interaction_type(**base, co_a=0.6, co_b=0.5) is InteractionType.COMMENSALISM
    assert interaction_type(**base, co_a=0.4, co_b=0.5) is InteractionType.AMENSalism
    assert interaction_type(**base, co_a=0.6, co_b=0.4) is InteractionType.PARASITISM


def test_interaction_type_eps_threshold():
    # 1e-9 변화는 eps(1e-6) 이하 → neutralism
    r = interaction_type(0.5, 0.5, 0.5 + 1e-9, 0.5 - 1e-9)
    assert r is InteractionType.NEUTRALISM
