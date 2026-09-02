"""Medium gap: why a model cannot grow on a diet, and the smallest supplement that fixes it.

Round-10 follow-up. Two independent causes were measured on a real AGORA2 pool held on CMIG's
shipped AGORA gut overlay, and both are pinned here:

1. Isolation policy v1 closed AGORA's ``--> dnarep_c`` style pseudo-reactions, which made **every**
   AGORA/AGORA2 reconstruction non-viable under ``--exact-medium`` whatever the diet contained.
2. The diet genuinely lacks quinones, siroheme and a diacylglycerol for most of those strains.

Before the fix a search reported a ranking of zero-growth "producers"; now such a candidate is
quarantined and `medium-gap` names what to add.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("cobra")

import cobra  # noqa: E402

from cmig.core.boundary import (  # noqa: E402
    BOUNDARY_ISOLATION_POLICY,
    boundary_isolation_violations,
    is_pseudo_supply,
    isolate_boundary,
)
from cmig.core.medium import MILPInfeasibleError, medium_gap  # noqa: E402
from cmig.core.medium_spec import MediumSpec  # noqa: E402


def _reaction(rid, stoich, lower=0.0, upper=1000.0):
    rxn = cobra.Reaction(rid)
    rxn.bounds = (lower, upper)
    rxn.add_metabolites(stoich)
    return rxn


def _agora_like_model() -> cobra.Model:
    """A model shaped like an AGORA reconstruction.

    Biomass consumes a real carbon source, a real cofactor, and a formula-``X`` pseudo-metabolite
    produced by a boundary reaction — the shape that made every AGORA model non-viable.
    """
    model = cobra.Model("agora_like")
    glc_e = cobra.Metabolite("glc__D_e", compartment="e", formula="C6H12O6")
    glc_c = cobra.Metabolite("glc__D_c", compartment="c", formula="C6H12O6")
    mqn_e = cobra.Metabolite("mqn7_e", compartment="e", formula="C46H64O2")
    mqn_c = cobra.Metabolite("mqn7_c", compartment="c", formula="C46H64O2")
    pseudo = cobra.Metabolite("proteinsynth_c", compartment="c", formula="X")
    biomass = _reaction("biomass205", {glc_c: -1.0, mqn_c: -0.01, pseudo: -1.0})
    model.add_reactions([
        _reaction("EX_glc__D_e", {glc_e: -1.0}, lower=-10.0),
        _reaction("GLCabc", {glc_e: -1.0, glc_c: 1.0}),
        _reaction("EX_mqn7_e", {mqn_e: -1.0}, lower=-10.0),
        _reaction("MQNabc", {mqn_e: -1.0, mqn_c: 1.0}),
        _reaction("pbiosynthesis", {pseudo: 1.0}),          # --> proteinsynth_c
        biomass,
    ])
    model.objective = biomass
    return model


# ── the pseudo-supply classification ─────────────────────────────────────────────────────────


def test_policy_marker_records_the_v2_rule() -> None:
    """The marker dates a manifest; results change with it, run_hash does not."""
    assert BOUNDARY_ISOLATION_POLICY == "boundary_reactions_v2"


def test_a_formula_x_supplier_is_a_pseudo_reaction_and_stays_open() -> None:
    model = _agora_like_model()
    pseudo_reaction = model.reactions.get_by_id("pbiosynthesis")
    assert is_pseudo_supply(pseudo_reaction)

    with model as working:
        isolation = isolate_boundary(working, {"EX_glc__D_e": 10.0}, strict_unmatched=False)
        assert "pbiosynthesis" in isolation.pseudo_supply_open
        assert "pbiosynthesis" not in isolation.closed
        # It adds no atoms, so the isolation invariant does not reach it either.
        assert boundary_isolation_violations(working, {"EX_glc__D_e": 10.0}) == {}


def test_a_missing_formula_is_not_treated_as_massless() -> None:
    """"The model did not say" is not "there are no atoms" — an unannotated sink stays closed."""
    model = _agora_like_model()
    unannotated = cobra.Metabolite("mystery_c", compartment="c")
    model.add_reactions([_reaction("SK_mystery_c", {unannotated: -1.0}, lower=-1000.0)])
    assert not is_pseudo_supply(model.reactions.get_by_id("SK_mystery_c"))
    with model as working:
        isolation = isolate_boundary(working, {"EX_glc__D_e": 10.0}, strict_unmatched=False)
        assert "SK_mystery_c" in isolation.closed
        assert "SK_mystery_c" not in isolation.pseudo_supply_open


def test_an_exchange_is_never_reclassified_as_a_pseudo_reaction() -> None:
    """`EX_biomass_e` also carries formula X; granting it uptake would feed a model its product."""
    model = _agora_like_model()
    biomass_e = cobra.Metabolite("biomass_e", compartment="e", formula="X")
    model.add_reactions([_reaction("EX_biomass_e", {biomass_e: -1.0}, lower=-1000.0)])
    with model as working:
        isolation = isolate_boundary(working, {"EX_glc__D_e": 10.0}, strict_unmatched=False)
        assert "EX_biomass_e" in isolation.closed
        assert "EX_biomass_e" not in isolation.pseudo_supply_open


# ── the gap itself ───────────────────────────────────────────────────────────────────────────


def test_gap_reports_a_sufficient_medium_without_proposing_anything() -> None:
    model = _agora_like_model()
    medium = MediumSpec(uptake={"EX_glc__D_e": 10.0, "EX_mqn7_e": 10.0})
    result = medium_gap(model, min_growth=0.1, medium=medium, strict_medium=False)
    assert result.base_is_sufficient is True
    assert result.supplement == [] and result.essential_supplement == []
    assert result.base_growth >= 0.1
    assert "pbiosynthesis" in result.pseudo_supply_open


def test_gap_names_the_missing_nutrient_and_verifies_it_restores_growth() -> None:
    model = _agora_like_model()
    medium = MediumSpec(uptake={"EX_glc__D_e": 10.0})     # the cofactor is missing
    result = medium_gap(model, min_growth=0.1, medium=medium, strict_medium=False)
    assert result.base_is_sufficient is False
    assert result.base_growth == pytest.approx(0.0, abs=1e-9)
    assert result.supplement == ["EX_mqn7_e"]
    # Cardinality-minimal AND leave-one-out verified, then re-solved on the exact reported medium.
    assert result.essential_supplement == ["EX_mqn7_e"]
    assert result.achieved_growth >= 0.1


def test_gap_refuses_a_supplement_larger_than_the_budget() -> None:
    model = _agora_like_model()
    medium = MediumSpec(uptake={"EX_glc__D_e": 10.0})
    with pytest.raises(MILPInfeasibleError):
        medium_gap(
            model, min_growth=0.1, medium=medium, strict_medium=False, max_supplement=0
        )


def test_gap_does_not_fix_an_anaerobe_by_making_it_breathe() -> None:
    """O2 is out of the candidate set under the default anaerobic mode."""
    model = _agora_like_model()
    o2_e = cobra.Metabolite("o2_e", compartment="e", formula="O2")
    o2_c = cobra.Metabolite("o2_c", compartment="c", formula="O2")
    model.add_reactions([
        _reaction("EX_o2_e", {o2_e: -1.0}, lower=-10.0),
        _reaction("O2t", {o2_e: -1.0, o2_c: 1.0}),
        # Oxygen-driven synthesis of the missing cofactor.
        _reaction("MQNSYN", {o2_c: -1.0, model.metabolites.get_by_id("mqn7_c"): 1.0}),
    ])
    # Make oxygen the ONLY route to the cofactor, so the choice is not a tie the MILP breaks
    # arbitrarily: with O2 excluded there is no supplement at all.
    model.remove_reactions(["EX_mqn7_e", "MQNabc"], remove_orphans=True)
    medium = MediumSpec(uptake={"EX_glc__D_e": 10.0})
    with pytest.raises(MILPInfeasibleError):
        medium_gap(model, min_growth=0.1, medium=medium, strict_medium=False)

    aerobic = medium_gap(
        model, min_growth=0.1, medium=medium, strict_medium=False, oxygen_mode="aerobic"
    )
    assert "EX_o2_e" in aerobic.supplement


# ── search quarantines a community that cannot grow ──────────────────────────────────────────


def test_target_solve_quarantines_a_non_viable_community() -> None:
    """A zero-growth community is not a producer, however much flux the LP can route."""
    from cmig.core.search import NON_VIABLE_GROWTH, Direction, TargetSpec, target_max_solve

    class _FakeCommunity:
        """Minimal stand-in: the guard must fire before any community LP is set up."""

        def __init__(self) -> None:
            self.reactions: list[object] = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    spec = TargetSpec("but", direction=Direction.MAX_SECRETION)
    result = target_max_solve(
        _FakeCommunity(), spec, growth_fraction=0.5, mu_community=0.0, solver="gurobi"
    )
    assert result.status == "non_viable"
    assert result.target_flux == 0.0
    assert "cannot grow on this medium" in json.dumps(result.diagnostic)
    assert NON_VIABLE_GROWTH == pytest.approx(1e-6)


def test_run_level_warning_points_at_the_medium_not_the_target() -> None:
    from cmig.core.search_product import PoolRank, _non_viable_warnings

    rows = [
        PoolRank(rank=0, members=("a", "b"), score=float("-inf"), target_flux=0.0,
                 community_growth=0.0, status="non_viable", diagnostic=None),
        PoolRank(rank=0, members=("a", "c"), score=float("-inf"), target_flux=0.0,
                 community_growth=0.0, status="missing", diagnostic=None),
    ]
    warnings = _non_viable_warnings(rows, 5)
    assert len(warnings) == 1
    assert "1 of 5" in warnings[0]
    assert "cmig medium-gap" in warnings[0]
    assert _non_viable_warnings([rows[1]], 5) == []


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────


def test_medium_gap_cli_writes_a_supplemented_medium_marked_as_such(tmp_path: Path) -> None:
    from cmig.cli.main import main

    model_path = tmp_path / "agora_like.xml"
    cobra.io.write_sbml_model(_agora_like_model(), str(model_path))
    medium = tmp_path / "diet.csv"
    medium.write_text("exchange_id,uptake_limit,row_role\nEX_glc__D_m,10.0,nutrient\n")
    out = tmp_path / "gap"

    rc = main(["medium-gap", "--model", str(model_path), "--medium", str(medium),
               "--exact-medium", "--allow-unknown-medium", "--min-growth", "0.1",
               "--out", str(out)])
    assert rc == 0

    payload = json.loads((out / "medium_gap.json").read_text())
    assert payload["n_supplement_required"] == 1
    assert payload["supplement_union_exchanges"] == ["EX_mqn7_e"]
    row = payload["models"][0]
    assert row["status"] == "supplement_required"
    assert row["supplement"] == "EX_mqn7_e"

    # The added row is addressed to the community pool and is never presented as published diet.
    lines = (out / "medium_gap_supplemented.csv").read_text().splitlines()
    assert lines[0] == "exchange_id,uptake_limit,row_role"
    assert "EX_glc__D_m,10.0,nutrient" in lines
    assert any(line.startswith("EX_mqn7_m,") and line.endswith(",gap_supplement") for line in lines)
