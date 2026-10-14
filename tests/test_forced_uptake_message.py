"""A medium cap below an uptake the model's own bounds force is refused in plain words.

Measured on the bundled iAF987 with `gut_overlay_agora_high_fiber`: its SBML bounds force
`EX_fe3_e` uptake of at least 49.21, the medium caps Fe3+ at 0.1, and the candidate failed with
cobra's "The lower bound must be less than or equal to the upper bound (-0.1 <= -49.21)." The
refusal (and the candidate's status) are unchanged; only the message now says what happened.
"""

from __future__ import annotations

import pytest

cobra = pytest.importorskip("cobra")

from cmig.core.boundary import BoundaryIsolationError, set_supply_limit  # noqa: E402


def _exchange(rid: str, met: str, compartment: str, bounds: tuple[float, float]):
    reaction = cobra.Reaction(rid)
    reaction.add_metabolites({cobra.Metabolite(met, compartment=compartment): -1})
    reaction.bounds = bounds
    return reaction


def test_a_cap_below_a_forced_uptake_names_model_exchange_requirement_and_cap():
    model = cobra.Model("iAF987")
    model.add_reactions([_exchange("EX_fe3_e", "fe3_e", "e", (-67.37, -49.21))])
    reaction = model.reactions.EX_fe3_e
    with pytest.raises(BoundaryIsolationError) as error:
        set_supply_limit(reaction, 0.1)
    message = str(error.value)
    assert message.startswith("iAF987 requires uptake of fe3 ≥ 49.21"), message
    assert "EX_fe3_e" in message and "at most 0.1" in message
    assert reaction.bounds == (-67.37, -49.21)   # nothing was changed


def test_in_a_community_the_member_whose_bounds_force_it_is_named():
    community = cobra.Model("community")
    community.add_reactions([
        _exchange("EX_fe3_m", "fe3_m", "m", (-67.37, -49.21)),
        _exchange("EX_fe3_e__iAF987", "fe3_e__iAF987", "e__iAF987", (-100.0, -49.21)),
        _exchange("EX_fe3_e__iHN637", "fe3_e__iHN637", "e__iHN637", (-100.0, 1000.0)),
    ])
    community.taxa = ["iAF987", "iHN637"]
    with pytest.raises(BoundaryIsolationError) as error:
        set_supply_limit(community.reactions.EX_fe3_m, 0.1)
    assert str(error.value).startswith("iAF987 requires uptake of fe3 ≥ 49.21"), error.value


def test_a_cap_at_or_above_the_forced_uptake_is_applied_as_before():
    model = cobra.Model("iAF987")
    model.add_reactions([_exchange("EX_fe3_e", "fe3_e", "e", (-67.37, -49.21))])
    set_supply_limit(model.reactions.EX_fe3_e, 60.0)
    assert model.reactions.EX_fe3_e.bounds == (-60.0, -49.21)
