"""Real tiny COBRA/MICOM reproductions for SC-02–04 physical boundary contracts."""

from __future__ import annotations

from dataclasses import replace

import cobra
import pandas as pd
import pytest

from cmig.core.dfba import DfbaConfig, simulate_dfba
from cmig.core.dfba_community import CommunityDfbaConfig, run_community_dfba
from cmig.core.engine import MicomEngine
from cmig.core.host_coupling import solve_bigg_host
from cmig.core.medium_spec import MediumSpec, apply_medium_translated
from cmig.core.model_pool import diagnose_model_pool
from cmig.io.model_import import exchange_metabolite_ids, import_model


def toy(*, reverse: bool = False, coefficient: float = 1.0,
        exchange: str = "EX_glc__D_e", hidden: str | None = None) -> cobra.Model:
    model = cobra.Model("physical_boundary")
    e = cobra.Metabolite("glc__D_e", compartment="e", formula="C6H12O6")
    c = cobra.Metabolite("glc__D_c", compartment="c", formula="C6H12O6")
    a = cobra.Metabolite("ac_e", compartment="e", formula="C2H3O2")
    rows = [
        (exchange, {e: coefficient if reverse else -coefficient},
         (0, 10 / coefficient) if reverse else (-10 / coefficient, 1000)),
        ("GLCt", {e: -1, c: 1}, (0, 1000)),
        ("BIOMASS", {c: -1, a: 1}, (0, 1000)),
        ("EX_ac_e", {a: -1}, (0, 1000)),
    ]
    if hidden == "sink":
        rows.append(("SK_glc__D_c", {c: -1}, (-10, 1000)))
    if hidden == "demand":
        rows.append(("DM_glc__D_c", {c: 1}, (0, 10)))
    if hidden == "forced":
        rows.append(("SK_glc__D_c", {c: -1}, (-10, -1)))
    for rid, stoich, bounds in rows:
        reaction = cobra.Reaction(rid)
        reaction.add_metabolites(stoich)
        reaction.bounds = bounds
        model.add_reactions([reaction])
    model.objective = "BIOMASS"
    model.solver = "gurobi"
    return model


def taxonomy(model: cobra.Model, tmp_path) -> pd.DataFrame:
    path = tmp_path / "member.json"
    cobra.io.save_json_model(model, str(path))
    return pd.DataFrame([{"id": "A", "file": str(path), "abundance": 1.0}])


@pytest.mark.parametrize("reverse,coefficient", [(False, 1), (True, 1), (False, 2), (True, 2)])
def test_physical_dfba_and_host_uptake_are_orientation_and_stoichiometry_invariant(
    reverse, coefficient,
):
    model = toy(reverse=reverse, coefficient=coefficient)
    bounds = model.reactions.get_by_id("EX_glc__D_e").bounds
    result = simulate_dfba(model, DfbaConfig(
        t_end=.1, dt=.1, initial_biomass=.1,
        initial_concentrations={"EX_glc__D_e": 1},
        vmax={"EX_glc__D_e": 10}, close_untracked_uptake=True,
    ))
    assert result.status == "completed"
    assert result.timecourse[-1].concentrations["EX_glc__D_e"] == pytest.approx(.900990099)
    assert result.timecourse[-1].exchange_fluxes["EX_glc__D_e"] == pytest.approx(-9.900990099)
    assert model.reactions.get_by_id("EX_glc__D_e").bounds == bounds
    host = solve_bigg_host(model, {"glc__D": 5}, exclude_metabolites=None)
    assert host.status == "optimal"
    assert host.biomass == pytest.approx(5)
    assert host.lumen_uptake_ranges["glc__D"] == pytest.approx((5, 5))
    row = next(f for f in host.interface_fluxes if f.exchange_id == "EX_glc__D_e")
    assert row.flux == pytest.approx(-5)
    assert row.label == "uptake"


@pytest.mark.parametrize("reverse,coefficient", [(False, 1), (True, 1), (False, 2), (True, 2)])
def test_physical_depletion_emergency_clamp_is_orientation_invariant(reverse, coefficient):
    result = simulate_dfba(toy(reverse=reverse, coefficient=coefficient), DfbaConfig(
        t_end=.1, dt=.1, min_dt=.1, initial_biomass=1,
        initial_concentrations={"EX_glc__D_e": .01},
        vmax={"EX_glc__D_e": 10}, close_untracked_uptake=True,
    ))
    assert result.status == "completed"
    point = result.timecourse[-1]
    assert point.concentrations["EX_glc__D_e"] == pytest.approx(0)
    assert point.t == pytest.approx(.1)
    assert point.biomass == pytest.approx(1.01)
    assert point.exchange_fluxes["EX_glc__D_e"] == pytest.approx(-.1)


@pytest.mark.parametrize("exchange", ["EX_glc__D_e", "EX_carbon_e", "carbon_exchange"])
def test_community_and_medium_use_actual_metabolite_identity(exchange, tmp_path):
    model = toy(exchange=exchange)
    translated = apply_medium_translated(model, MediumSpec({"EX_glc__D_e": 5}), exact=True)
    assert translated.mapping["EX_glc__D_e"] == exchange
    pool = taxonomy(model, tmp_path)
    summary = import_model(pool.iloc[0]["file"])
    assert "glc__D" in exchange_metabolite_ids(summary)
    diagnostic = diagnose_model_pool(pool, "glc__D")[0]
    assert diagnostic.matching_exchanges == (exchange,)
    community = MicomEngine().build_community(pool)
    result = MicomEngine().cooperative_tradeoff(community, .5)
    assert result.status == "optimal"
    assert result.member_exchange["A"]["glc__D"] < 0
    assert result.external_exchange["glc__D"] == pytest.approx(
        result.member_exchange["A"]["glc__D"]
    )


@pytest.mark.parametrize("hidden", ["sink", "demand"])
def test_hidden_community_supply_is_closed_or_diagnosed(hidden, tmp_path):
    pool = taxonomy(toy(hidden=hidden), tmp_path)
    config = CommunityDfbaConfig(
        t_end=.1, dt=.1, initial_concentrations={"EX_glc__D_m": 0},
        initial_biomasses={"A": .1},
    )
    open_result = run_community_dfba(pool, config)
    assert open_result.timecourse[-1].member_biomasses["A"] > .1
    assert any(("SK_" if hidden == "sink" else "DM_") in key
               for key in open_result.untracked_uptake)
    assert set(open_result.untracked_uptake_basis.values()) == {"member_biomass"}
    assert not open_result.acceptance.interpretable
    closed = run_community_dfba(pool, replace(config, close_untracked_uptake=True))
    assert closed.timecourse[-1].member_biomasses["A"] == pytest.approx(.1)
    assert not closed.untracked_uptake


def test_forced_community_supply_is_rejected(tmp_path):
    pool = taxonomy(toy(hidden="forced"), tmp_path)
    config = CommunityDfbaConfig(
        t_end=.1, initial_concentrations={"EX_glc__D_m": 0},
        initial_biomasses={"A": .1}, close_untracked_uptake=True,
    )
    with pytest.raises(ValueError, match="forced undeclared suppliers"):
        run_community_dfba(pool, config)


@pytest.mark.parametrize("formula,expected_growth", [("X", True), (None, False)])
def test_explicit_formula_x_pseudo_supply_exception(formula, expected_growth, tmp_path):
    model = cobra.Model("pseudo_process")
    glucose = cobra.Metabolite("glc__D_e", compartment="e", formula="C6H12O6")
    process = cobra.Metabolite("process_c", compartment="c", formula=formula)
    for rid, stoich, bounds in [
        ("EX_glc__D_e", {glucose: -1}, (-10, 1000)),
        ("DM_process_c", {process: 1}, (0, 10)),
        ("BIOMASS", {process: -1}, (0, 1000)),
    ]:
        reaction = cobra.Reaction(rid)
        reaction.add_metabolites(stoich)
        reaction.bounds = bounds
        model.add_reactions([reaction])
    model.objective = "BIOMASS"
    pool = taxonomy(model, tmp_path)
    result = run_community_dfba(pool, CommunityDfbaConfig(
        t_end=.1, initial_concentrations={"EX_glc__D_m": 0},
        initial_biomasses={"A": .1}, close_untracked_uptake=True,
    ))
    assert (result.timecourse[-1].member_biomasses["A"] > .1) is expected_growth
    assert result.untracked_uptake == {}


def test_nonunit_community_input_rejected_before_micom_solve(tmp_path):
    with pytest.raises(ValueError, match="non-unit input exchange stoichiometry"):
        MicomEngine().build_community(taxonomy(toy(coefficient=2), tmp_path))


def test_ambiguous_medium_alias_rejected_with_candidates():
    model = toy()
    extra = cobra.Reaction("carbon_exchange")
    extra.add_metabolites({model.metabolites.get_by_id("glc__D_e"): -1})
    extra.bounds = (-10, 1000)
    model.add_reactions([extra])
    with pytest.raises(ValueError, match="ambiguous medium exchange.*carbon_exchange"):
        apply_medium_translated(model, MediumSpec({"EX_glc__D_m": 5}), exact=True)


def test_duplicate_member_exchanges_aggregate_one_nutrient_without_overwrite(tmp_path):
    model = toy()
    extra = cobra.Reaction("carbon_exchange")
    extra.add_metabolites({model.metabolites.get_by_id("glc__D_e"): -1})
    extra.bounds = (-10, 1000)
    model.add_reactions([extra])
    pool = taxonomy(model, tmp_path)
    engine = MicomEngine()
    community = engine.build_community(pool)
    result = engine.cooperative_tradeoff(community, .5)
    assert result.status == "optimal"
    assert result.member_exchange["A"]["glc__D"] == pytest.approx(
        result.external_exchange["glc__D"]
    )


def _two_member_pool(tmp_path, first: cobra.Model, second: cobra.Model) -> pd.DataFrame:
    rows = []
    for name, model in (("A", first), ("B", second)):
        filename = tmp_path / f"{name}.json"
        cobra.io.save_json_model(model, str(filename))
        rows.append({"id": name, "file": str(filename), "abundance": 1.0})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("reverse", [False, True])
def test_community_zero_member_cap_respects_exchange_orientation(tmp_path, reverse):
    pool = _two_member_pool(tmp_path, toy(reverse=reverse), toy())
    result = run_community_dfba(pool, CommunityDfbaConfig(
        t_end=.1, dt=.1, initial_concentrations={"EX_glc__D_m": 1},
        initial_biomasses={"A": .1, "B": .1},
        member_vmax={"A": {"EX_glc__D_m": 0}, "B": {"EX_glc__D_m": 10}},
        close_untracked_uptake=True,
    ))
    assert result.status == "completed"
    assert result.acceptance.interpretable
    point = result.timecourse[-1]
    assert point.member_biomasses["A"] == pytest.approx(.1)
    assert point.member_exchange_fluxes["A"]["EX_glc__D_m"] == pytest.approx(0)
    assert point.member_exchange_fluxes["B"]["EX_glc__D_m"] == pytest.approx(-9.900990099)


@pytest.mark.parametrize("reverse_extra,blocked_primary", [
    (False, False), (True, False), (False, True),
])
def test_duplicate_channels_share_one_member_budget(
    tmp_path, reverse_extra, blocked_primary,
):
    first = toy()
    if blocked_primary:
        first.reactions.EX_glc__D_e.lower_bound = 0
    extra = cobra.Reaction("second_carbon")
    extra.add_metabolites({first.metabolites.glc__D_e: 1 if reverse_extra else -1})
    extra.bounds = (-1000, 10) if reverse_extra else (-10, 1000)
    first.add_reactions([extra])
    pool = _two_member_pool(tmp_path, first, toy())
    result = run_community_dfba(pool, CommunityDfbaConfig(
        t_end=.2, dt=.1, initial_concentrations={"EX_glc__D_m": 1},
        initial_biomasses={"A": .1, "B": .2},
        member_vmax={"A": {"EX_glc__D_m": 2}, "B": {"EX_glc__D_m": 10}},
        close_untracked_uptake=True,
    ))
    assert result.status == "completed"
    assert result.acceptance.interpretable
    for before, after in zip(result.timecourse, result.timecourse[1:], strict=False):
        cap = 2 * before.concentrations["EX_glc__D_m"] / (
            .01 + before.concentrations["EX_glc__D_m"]
        )
        rate = after.member_exchange_fluxes["A"]["EX_glc__D_m"]
        assert -rate <= cap + 1e-7
        assert -rate == pytest.approx(cap)
        expected_change = sum(
            before.member_biomasses[member]
            * after.member_exchange_fluxes[member]["EX_glc__D_m"]
            * after.step_dt
            for member in ("A", "B")
        )
        assert after.concentrations["EX_glc__D_m"] - before.concentrations[
            "EX_glc__D_m"
        ] == pytest.approx(expected_change)
