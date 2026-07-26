"""P0-A regression — the `_m` vs `_e` exchange-namespace bridge and *measured* medium equality.

Round-2 evaluators independently confirmed the round-1 "same medium for both legs" fix did not
hold: a community exposes `EX_glc__D_m` while each member model exposes `EX_glc__D_e`, so passing
one MediumSpec to both applied it to **neither**, while the summary still asserted
`single_medium_equals_community_medium: true`. A false assertion of experimental control is worse
than the original bug, so these tests pin three things:

1. translation matches on the *metabolite*, so `_m` presets reach `_e` models;
2. a medium can OPEN a currently-closed exchange (the old primitive gated on `model.medium`, which
   lists only already-open uptakes, making that impossible);
3. equality is computed from the two effective media and is never `True` by assumption.

No solver required — cobra Models only.
"""

from __future__ import annotations

import pytest

cobra = pytest.importorskip("cobra")

from cmig.core.medium_spec import (  # noqa: E402
    MediumSpec,
    apply_medium_translated,
    compare_effective_media,
    effective_medium_by_metabolite,
    exchange_metabolite,
    model_exchange_index,
    translate_medium_for_model,
)


def _model(name: str, exchanges: dict[str, float]) -> cobra.Model:
    """Model whose exchanges are open (bound>0) or closed (bound==0), like a real GEM."""
    model = cobra.Model(name)
    reactions = []
    for exchange_id, open_uptake in exchanges.items():
        metabolite = cobra.Metabolite(exchange_id.removeprefix("EX_"), compartment="e")
        reaction = cobra.Reaction(exchange_id)
        reaction.add_metabolites({metabolite: -1})
        reaction.bounds = (-open_uptake, 1000.0)
        reactions.append(reaction)
    model.add_reactions(reactions)
    return model


# ── metabolite extraction ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("exchange_id", "metabolite"),
    [
        ("EX_glc__D_m", "glc__D"),      # community namespace
        ("EX_glc__D_e", "glc__D"),      # member namespace — same metabolite
        ("EX_lac__L_e", "lac__L"),      # double underscore in the metabolite itself
        ("EX_ac_m", "ac"),
        ("EX_etoh_lumen", "etoh"),      # host interface compartment
        ("ac", "ac"),                   # bare id, no prefix/compartment
    ],
)
def test_exchange_metabolite_is_namespace_free(exchange_id, metabolite):
    assert exchange_metabolite(exchange_id) == metabolite


# ── translation across namespaces ────────────────────────────────────────────────

def test_m_namespace_medium_translates_onto_an_e_namespace_model():
    """The exact failure: an `EX_*_m` preset must reach an `EX_*_e` model."""
    model = _model("member", {"EX_glc__D_e": 10.0, "EX_o2_e": 20.0})
    spec = MediumSpec(uptake={"EX_glc__D_m": 5.0, "EX_o2_m": 1.0})
    translation = translate_medium_for_model(model, spec)
    assert translation.mapping == {"EX_glc__D_m": "EX_glc__D_e", "EX_o2_m": "EX_o2_e"}
    assert translation.unmatched == ()
    assert translation.spec.uptake == {"EX_glc__D_e": 5.0, "EX_o2_e": 1.0}


def test_metabolite_with_no_exchange_is_reported_not_silently_dropped():
    model = _model("member", {"EX_glc__D_e": 10.0})
    spec = MediumSpec(uptake={"EX_glc__D_m": 5.0, "EX_fru_m": 5.0})
    translation = translate_medium_for_model(model, spec)
    assert translation.unmatched == ("EX_fru_m",)
    assert "EX_fru_e" not in translation.spec.uptake


def test_index_covers_closed_exchanges_too():
    """A medium's job is to decide what is open, so a closed exchange must still be indexable."""
    model = _model("member", {"EX_glc__D_e": 0.0, "EX_o2_e": 20.0})
    assert model_exchange_index(model) == {"glc__D": "EX_glc__D_e", "o2": "EX_o2_e"}
    assert "glc__D" not in effective_medium_by_metabolite(model)   # closed → not in medium


def test_apply_can_open_a_closed_exchange():
    """The round-1 primitive gated on `model.medium`, so this was impossible."""
    model = _model("member", {"EX_glc__D_e": 0.0, "EX_o2_e": 20.0})
    apply_medium_translated(model, MediumSpec(uptake={"EX_glc__D_m": 7.0}), strict=True)
    assert model.reactions.EX_glc__D_e.lower_bound == pytest.approx(-7.0)
    assert effective_medium_by_metabolite(model)["glc__D"] == pytest.approx(7.0)


def test_exact_mode_closes_everything_not_offered():
    """A controlled medium is the WHOLE offer, not a patch on top of native bounds."""
    model = _model("member", {"EX_glc__D_e": 10.0, "EX_o2_e": 20.0, "EX_ac_e": 5.0})
    apply_medium_translated(
        model, MediumSpec(uptake={"EX_glc__D_m": 7.0}), strict=True, exact=True
    )
    effective = effective_medium_by_metabolite(model)
    assert effective == {"glc__D": pytest.approx(7.0)}
    assert model.reactions.EX_o2_e.lower_bound == 0.0
    assert model.reactions.EX_ac_e.lower_bound == 0.0


def test_merge_mode_keeps_the_rest_of_the_offer():
    model = _model("member", {"EX_glc__D_e": 10.0, "EX_o2_e": 20.0})
    apply_medium_translated(
        model, MediumSpec(uptake={"EX_glc__D_m": 7.0}), strict=True, exact=False
    )
    effective = effective_medium_by_metabolite(model)
    assert effective["glc__D"] == pytest.approx(7.0)
    assert effective["o2"] == pytest.approx(20.0)


def test_strict_refuses_a_medium_the_model_cannot_honour():
    model = _model("member", {"EX_glc__D_e": 10.0})
    with pytest.raises(ValueError, match="no counterpart"):
        apply_medium_translated(model, MediumSpec(uptake={"EX_fru_m": 5.0}), strict=True)


# ── measured equality, never assumed ─────────────────────────────────────────────

def test_identical_offers_compare_equal_across_namespaces():
    community = {"glc__D": 10.0, "o2": 20.0}
    member = {"glc__D": 10.0, "o2": 20.0}
    equal, differences = compare_effective_media(community, member)
    assert equal is True
    assert differences == {
        "missing_from_candidate": [], "extra_in_candidate": [], "bound_mismatch": []
    }


def test_a_looser_bound_breaks_equality():
    """The default-path defect: community nh4/pi/so4 999999 vs member 5.0 is NOT the same medium."""
    equal, differences = compare_effective_media({"nh4": 999999.0}, {"nh4": 5.0})
    assert equal is False
    assert differences["bound_mismatch"] == ["nh4"]


def test_a_nutrient_open_only_in_the_community_breaks_equality():
    equal, differences = compare_effective_media({"glc__D": 10.0, "fru": 5.0}, {"glc__D": 10.0})
    assert equal is False
    assert differences["missing_from_candidate"] == ["fru"]


def test_a_nutrient_open_only_in_the_member_breaks_equality():
    equal, differences = compare_effective_media({"glc__D": 10.0}, {"glc__D": 10.0, "ac": 1.0})
    assert equal is False
    assert differences["extra_in_candidate"] == ["ac"]


def test_exempt_metabolites_do_not_break_equality():
    """A member with no fructose exchange cannot be offered fructose — biology, not lost control."""
    equal, differences = compare_effective_media(
        {"glc__D": 10.0, "fru": 5.0}, {"glc__D": 10.0}, exempt={"fru"}
    )
    assert equal is True
    assert differences["missing_from_candidate"] == []


def test_equality_is_not_true_merely_because_no_medium_was_requested():
    """Round-1 set the flag from `medium_spec is None`; micom's union medium is never each
    member's native medium, so 'no medium requested' must not imply 'media match'."""
    community = {"glc__D": 999999.0, "fru": 999999.0, "nh4": 999999.0}
    native_member = {"glc__D": 10.0, "nh4": 5.0}
    equal, _ = compare_effective_media(community, native_member)
    assert equal is False


def test_tolerance_absorbs_float_noise_only():
    assert compare_effective_media({"ac": 1.0}, {"ac": 1.0 + 1e-12})[0] is True
    assert compare_effective_media({"ac": 1.0}, {"ac": 1.001})[0] is False
