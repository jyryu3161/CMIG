"""Round 6 track B — the boundary-isolation primitive and its invariant, on synthetic models.

The companion module ``test_boundary_isolation_gems.py`` asserts the same invariant on the real
GEMs (Recon3D, RECON1 and three bundled microbial models). This one covers the arithmetic and the
edge cases at unit speed, and it does so on cobra models that actually carry a **sink** and a
**demand** — the two reaction classes every previous "close the background" fix in this codebase
could not see, because they are not members of ``model.exchanges``.
"""

from __future__ import annotations

import pytest

from cmig.core.boundary import (
    BOUNDARY_ISOLATION_POLICY,
    BoundaryIsolationError,
    boundary_isolation_violations,
    boundary_reactions,
    close_boundary_supply,
    forced_supply,
    isolate_boundary,
    mass_supplying_boundary,
    realised_boundary_suppliers,
    supply_capacity,
    supply_rate,
)

cobra = pytest.importorskip("cobra")


def _model_with_sink_and_demand() -> object:
    """A cobra model whose boundary is strictly larger than its exchanges.

    ``EX_glc__D_e`` is an exchange (external compartment). ``SK_atp_c`` and ``DM_amp_c`` sit on a
    cytosolic metabolite, so cobra classifies them as boundary reactions but **not** exchanges —
    exactly the Recon3D shape (1806 boundary = 1560 exchanges + 101 sinks + 145 demands).
    """
    from cobra import Metabolite, Model, Reaction

    model = Model("sink_demand")
    glc_e = Metabolite("glc__D_e", compartment="e")
    atp_c = Metabolite("atp_c", compartment="c")
    amp_c = Metabolite("amp_c", compartment="c")
    model.add_metabolites([glc_e, atp_c, amp_c])

    ex = Reaction("EX_glc__D_e", lower_bound=-10.0, upper_bound=1000.0)
    ex.add_metabolites({glc_e: -1.0})
    sk = Reaction("SK_atp_c", lower_bound=-1000.0, upper_bound=1000.0)
    sk.add_metabolites({atp_c: -1.0})
    dm = Reaction("DM_amp_c", lower_bound=0.0, upper_bound=1000.0)
    dm.add_metabolites({amp_c: -1.0})
    model.add_reactions([ex, sk, dm])
    return model


def _model_with_products_side_boundary() -> object:
    """A boundary reaction written ``--> met``, which supplies at POSITIVE flux."""
    from cobra import Metabolite, Model, Reaction

    model = Model("products_side")
    met = Metabolite("nadh_c", compartment="c")
    model.add_metabolites([met])
    supply = Reaction("SK_nadh_c_rev", lower_bound=0.0, upper_bound=500.0)
    supply.add_metabolites({met: 1.0})       # ``--> nadh_c``
    model.add_reactions([supply])
    return model


def _model_with_forced_uptake() -> object:
    """``EX_ac_e [-8.88, -6.84]`` — iAF987's shape. Every feasible flux supplies mass."""
    from cobra import Metabolite, Model, Reaction

    model = Model("forced")
    ac_e = Metabolite("ac_e", compartment="e")
    model.add_metabolites([ac_e])
    ex = Reaction("EX_ac_e", lower_bound=-8.88, upper_bound=-6.84)
    ex.add_metabolites({ac_e: -1.0})
    model.add_reactions([ex])
    return model


# ── the enumeration itself ─────────────────────────────────────────────────────────────────────


def test_boundary_is_a_strict_superset_of_exchanges():
    """The defect in one assertion: ``model.exchanges`` cannot see a sink or a demand."""
    model = _model_with_sink_and_demand()
    boundary = {str(r.id) for r in boundary_reactions(model)}
    exchanges = {str(r.id) for r in model.exchanges}

    assert boundary == {"EX_glc__D_e", "SK_atp_c", "DM_amp_c"}
    assert "SK_atp_c" not in exchanges
    assert "DM_amp_c" not in exchanges
    # ... and the sink is wide open at -1000, i.e. an unbounded mass source.
    assert supply_capacity(model.reactions.get_by_id("SK_atp_c")) == 1000.0


def test_model_medium_does_not_list_the_open_sink():
    """``model.medium`` is the narrowest view of the three and is what instance 1 enumerated."""
    model = _model_with_sink_and_demand()
    assert "SK_atp_c" not in dict(model.medium)
    assert "SK_atp_c" in mass_supplying_boundary(model)


def test_mass_supplying_boundary_flags_non_exchange_suppliers():
    supplies = mass_supplying_boundary(_model_with_sink_and_demand())
    assert set(supplies) == {"EX_glc__D_e", "SK_atp_c"}      # the demand cannot supply
    assert supplies["EX_glc__D_e"].is_exchange is True
    assert supplies["SK_atp_c"].is_exchange is False
    assert supplies["SK_atp_c"].capacity == 1000.0


def test_products_side_boundary_supplies_at_positive_flux():
    """Direction is decided by the stoichiometry, not by the sign of the flux alone."""
    model = _model_with_products_side_boundary()
    reaction = model.reactions.get_by_id("SK_nadh_c_rev")

    assert supply_capacity(reaction) == 500.0
    assert supply_rate(reaction, 3.0) == 3.0        # positive flux SUPPLIES here
    assert supply_rate(reaction, -3.0) == 0.0
    # The dFBA recorder's old test (`flux < -1e-9`) would have scored this as no uptake at all.
    assert realised_boundary_suppliers(model, {"SK_nadh_c_rev": 3.0}) == {"SK_nadh_c_rev": 3.0}


# ── closing and opening ────────────────────────────────────────────────────────────────────────


def test_close_boundary_supply_closes_the_sink_and_reports_it():
    model = _model_with_sink_and_demand()
    with model:
        closure = close_boundary_supply(model)

        assert closure.policy == BOUNDARY_ISOLATION_POLICY
        assert closure.n_boundary == 3
        assert set(closure.closed) == {"EX_glc__D_e", "SK_atp_c"}
        assert closure.non_exchange_closed == ("SK_atp_c",)
        assert mass_supplying_boundary(model) == {}
        # A demand keeps its ability to REMOVE mass — closing that would change the model.
        assert model.reactions.get_by_id("DM_amp_c").upper_bound == 1000.0


def test_isolate_boundary_opens_exactly_the_declared_reactions():
    model = _model_with_sink_and_demand()
    with model:
        isolation = isolate_boundary(model, {"EX_glc__D_e": 2.5})

        assert isolation.opened == {"EX_glc__D_e": 2.5}
        assert model.reactions.get_by_id("EX_glc__D_e").lower_bound == -2.5
        assert model.reactions.get_by_id("SK_atp_c").lower_bound == 0.0
        assert boundary_isolation_violations(model, {"EX_glc__D_e": 2.5}) == {}


def test_isolation_violation_reports_excess_capacity_not_just_a_name():
    model = _model_with_sink_and_demand()
    with model:
        # Only the exchanges were closed — the pre-fix behaviour, reproduced by hand.
        for reaction in model.exchanges:
            reaction.lower_bound = 0.0
        violations = boundary_isolation_violations(model, {})

        assert violations == {"SK_atp_c": 1000.0}


def test_declared_reaction_above_its_declared_limit_is_a_violation():
    """"At the declared bounds" is part of the invariant, not decoration."""
    model = _model_with_sink_and_demand()
    with model:
        isolate_boundary(model, {"EX_glc__D_e": 2.5})
        model.reactions.get_by_id("EX_glc__D_e").lower_bound = -9.0
        assert boundary_isolation_violations(model, {"EX_glc__D_e": 2.5}) == {"EX_glc__D_e": 6.5}


def test_a_directionless_boundary_reaction_cannot_carry_an_uptake_limit():
    """A reaction with no metabolites has no supplying direction, so the request is impossible.

    Silently doing nothing would leave a caller believing a medium had been applied while no bound
    moved — the silent-no-op form of this round's defect. It found a real under-specified test
    double (`test_strain_growth_medium_basis`), whose community stand-in used metabolite-less
    exchange reactions and therefore could not represent the thing the medium code manipulates.
    """
    from cobra import Model, Reaction

    from cmig.core.boundary import set_supply_limit

    model = Model("directionless")
    model.add_reactions([Reaction("EX_nothing_e", lower_bound=-10.0, upper_bound=1000.0)])
    reaction = model.reactions.get_by_id("EX_nothing_e")

    with pytest.raises(BoundaryIsolationError, match="no metabolites"):
        set_supply_limit(reaction, 5.0)


def test_unmatched_declared_reaction_is_refused_by_default():
    model = _model_with_sink_and_demand()
    with model, pytest.raises(BoundaryIsolationError, match="not present in the model"):
        isolate_boundary(model, {"EX_nope_e": 1.0})


# ── forced supply is reported, never mangled ───────────────────────────────────────────────────


def test_forced_uptake_is_reported_and_bounds_are_left_intact():
    """iAF987's shape. cobra's own ``model.medium`` setter raises here; we report instead."""
    model = _model_with_forced_uptake()
    reaction = model.reactions.get_by_id("EX_ac_e")
    assert forced_supply(reaction) == pytest.approx(6.84)

    with model:
        isolation = close_boundary_supply(model)

        assert isolation.forced_supply == pytest.approx({"EX_ac_e": 6.84})
        assert isolation.complete is False
        assert isolation.closed == ()
        # The SBML's bounds are untouched: mangling them would silently change the feasible set.
        assert (reaction.lower_bound, reaction.upper_bound) == (-8.88, -6.84)


def test_strict_isolation_refuses_a_background_it_cannot_close():
    model = _model_with_forced_uptake()
    with model, pytest.raises(BoundaryIsolationError, match="FORCE mass supply"):
        isolate_boundary(model, {}, strict=True)


def test_cobra_medium_setter_cannot_close_a_sink():
    """The reason wrapping the setter is not optional (instance 3, inherited from cobra).

    cobra's setter does ``exchange_rxns = frozenset(self.exchanges)`` and turns off only those.
    If this ever starts passing, cobra changed and the wrapper can be revisited.
    """
    model = _model_with_sink_and_demand()
    with model:
        model.medium = {"EX_glc__D_e": 1.0}
        assert model.reactions.get_by_id("SK_atp_c").lower_bound == -1000.0
        assert boundary_isolation_violations(model, {"EX_glc__D_e": 1.0}) == {"SK_atp_c": 1000.0}
