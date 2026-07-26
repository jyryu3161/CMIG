"""Round-6 track H: real human GEM (Recon3D/RECON1) as the CMIG host.

Two groups of tests live here.

* **Synthetic, always runs.** The sink-supplied-mass defect and the maintenance-objective gap
  reproduce on toy models in milliseconds, so the regression guard does not depend on a 27 MB
  download. These are the tests that would have caught both defects before a human GEM shipped.
* **Recon3D-backed, skips when the model is absent.** The measured numbers from the real model,
  pinned so a future change to the matcher, the isolation rule or the objective guard is visible.

Every assertion here was verified to FAIL with the round-6 production change reverted; see
`REVIEW`/the round-6 report for the paired before/after outputs.
"""

from __future__ import annotations

import pytest

pytest.importorskip("cobra")

from cmig.core.host import (  # noqa: E402
    nonexchange_boundary_uptake,
    summarize_host_model,
)
from cmig.core.host_coupling import solve_bigg_host  # noqa: E402
from cmig.io.gem_paths import resolve_human_gem  # noqa: E402
from cmig.io.model_import import objective_structure_warning  # noqa: E402

# ── synthetic reproductions ────────────────────────────────────────────────────


def _sink_fed_host():
    """A host whose biomass can be built entirely from a `SK_*` sink, with no exchange uptake.

    This is the Recon3D shape in miniature: `EX_ac_e` is the only exchange and it is closed for
    uptake, while `SK_glc_c` sits at ``lower_bound = -1000`` and can supply the carbon for biomass
    on its own. cobra classifies `SK_glc_c` as a sink, **not** an exchange, which is exactly why
    iterating ``model.exchanges`` failed to isolate the host.
    """
    from cobra import Metabolite, Model, Reaction

    def met(mid):
        return Metabolite(mid, compartment="e" if mid.endswith("_e") else "c")

    def rxn(rid, stoich, bounds):
        reaction = Reaction(rid)
        reaction.add_metabolites({met(mid): coef for mid, coef in stoich.items()})
        reaction.bounds = bounds
        return reaction

    model = Model("sink_fed_host")
    model.add_reactions([
        rxn("EX_ac_e", {"ac_e": -1}, (0, 1000)),
        rxn("ACt", {"ac_e": -1, "ac_c": 1}, (-1000, 1000)),
        rxn("SK_glc_c", {"glc_c": -1}, (-1000, 1000)),      # cobra sink: can SUPPLY glc_c
        rxn("GLC_TO_ATP", {"glc_c": -1, "atp_c": 6}, (0, 1000)),
        rxn("AC_TO_ATP", {"ac_c": -1, "atp_c": 1}, (0, 1000)),
        rxn("BIOMASS_host", {"atp_c": -1}, (0, 1000)),
    ])
    model.objective = "BIOMASS_host"
    return model


def test_close_unlisted_uptake_closes_sinks_not_only_exchanges():
    """P0: a host with zero microbial availability must not grow on an open sink.

    Before round 6 ``close_unlisted_uptake`` iterated ``model.exchanges`` only, so `SK_glc_c`
    stayed at -1000 and this returned a fully viable host that no microbe had fed. On the real
    Recon3D that made the coupled `BIOMASS_reaction` **bit-identical** with and without any
    microbial availability (368.01024754644214 either way).
    """
    result = solve_bigg_host(_sink_fed_host(), {}, close_unlisted_uptake=True, solver="gurobi")
    assert result.status == "optimal"
    assert result.biomass == pytest.approx(0.0, abs=1e-9)
    assert not result.viable
    assert any("non-exchange boundary" in warning for warning in result.warnings)
    assert any("SK_glc_c" in warning for warning in result.warnings)


def test_isolated_host_objective_responds_to_microbial_availability():
    """With the sink closed the host objective is actually attributable to the microbes."""
    host = _sink_fed_host()
    without = solve_bigg_host(host, {}, close_unlisted_uptake=True, solver="gurobi")
    with_microbes = solve_bigg_host(
        host, {"ac": 5.0}, close_unlisted_uptake=True, solver="gurobi"
    )
    assert without.biomass == pytest.approx(0.0, abs=1e-9)
    assert with_microbes.biomass == pytest.approx(5.0, rel=1e-6)
    assert with_microbes.biomass > without.biomass


def test_keep_host_uptake_names_the_open_suppliers():
    """`--keep-host-uptake` is legal, but the objective it produces must say it is unattributed."""
    result = solve_bigg_host(_sink_fed_host(), {}, close_unlisted_uptake=False, solver="gurobi")
    assert result.biomass > 0.0
    assert any(
        "not attributable to the microbial availability" in warning
        for warning in result.warnings
    )


def test_nonexchange_boundary_uptake_lists_sinks():
    assert nonexchange_boundary_uptake(_sink_fed_host()) == ["SK_glc_c"]


def test_manifest_stamps_the_host_isolation_policy():
    """The isolation fix moved published answers without moving any `run_hash`.

    Measured on Recon3D: `host-microbe-bigg` `host_objective` 368.010247546 -> 0.0 under the
    bit-identical `run_hash 60b4409749abdb98…`, with only `result_digest` differing
    (`5e0878dd…` -> `9e22bffa…`). That is the situation round 5 introduced `medium_policy` for, so
    the same shape is used: a non-hashed provenance marker, which cannot move a run_hash because
    `hash_components` is the authority on what is hashed.
    """
    from cmig.core.host_coupling import HOST_ISOLATION_POLICY
    from cmig.core.workflow_manifest import (
        base_components,
        build_workflow_manifest,
        medium_component,
    )

    components = base_components(
        "model_quality",
        solver_setting={"solver": "gurobi"},
        model_checksum="sha256:deadbeef",
        medium=medium_component(None, "model_quality_no_medium"),
    )
    components["quality_spec"] = {"n_models": 1}
    payload = build_workflow_manifest("model_quality", components).to_payload()
    assert payload["host_isolation_policy"] == HOST_ISOLATION_POLICY == "all_boundary_uptake_v2"
    # Provenance, not a hash component — adding it must not be able to move any published hash.
    assert "host_isolation_policy" not in payload["hash_components"]
    assert "host_isolation_policy" not in payload["components"]


def _maintenance_objective_model():
    from cobra import Metabolite, Model, Reaction

    model = Model("maintenance_objective_host")
    atp = Metabolite("atp_c", compartment="c")
    source = Reaction("ATP_SRC")
    source.add_metabolites({atp: 1})
    source.bounds = (0, 1000)
    maintenance = Reaction("BIOMASS_maintenance")
    maintenance.name = "Biomass maintenance reaction without replication precursors"
    maintenance.add_metabolites({atp: -1})
    maintenance.bounds = (0, 1000)
    growth = Reaction("BIOMASS_reaction")
    growth.name = "Generic Human Biomass Reaction"
    growth.add_metabolites({atp: -2})
    growth.bounds = (0, 1000)
    model.add_reactions([source, maintenance, growth])
    model.objective = "BIOMASS_maintenance"
    return model


def test_maintenance_objective_is_warned_not_reported_as_growth():
    """Recon3D's shipped default is `BIOMASS_maintenance`; 755.003 is not a growth rate.

    Round 5's guard admitted it in silence because "biomass" is in the name, so the maintenance
    optimum was available to `model-quality`, `host-benchmark` and `host-generic` with no caveat.
    """
    model = _maintenance_objective_model()
    summary = summarize_host_model(model)
    assert summary.objective_reactions == ["BIOMASS_maintenance"]
    assert summary.objective_warning is not None
    assert "MAINTENANCE" in summary.objective_warning
    assert "BIOMASS_maintenance" in summary.objective_warning
    assert "NOT a growth rate" in summary.objective_warning


def test_growth_objective_is_not_warned():
    """The guard must not cry wolf on the reaction a growth question should actually use."""
    model = _maintenance_objective_model()
    model.objective = "BIOMASS_reaction"
    summary = summarize_host_model(model)
    assert summary.objective_reactions == ["BIOMASS_reaction"]
    assert summary.objective_warning is None


def test_objective_structure_warning_accepts_bare_reaction_ids():
    """`model-quality` / `diagnose_model_pool` only hold ids; the checks must still run.

    Passing ids used to make every ``getattr`` miss, so the id came back as ``'?'`` — which is why
    those call sites passed the count alone and got no single-term check at all.
    """
    transport = objective_structure_warning(1, ["S6T14g"])
    assert transport is not None
    assert "S6T14g" in transport
    assert "?" not in transport
    maintenance = objective_structure_warning(1, ["BIOMASS_maintenance"])
    assert maintenance is not None and "MAINTENANCE" in maintenance
    boundary = objective_structure_warning(1, ["EX_ac_e"])
    assert boundary is not None and "boundary reaction EX_ac_e" in boundary
    assert objective_structure_warning(1, ["BIOMASS_Ec_iML1515_core_75p37M"]) is None


def test_model_quality_reports_a_transport_objective_as_not_growth():
    """`model-quality` audited RECON1's `S6T14g` objective with an empty objective warning."""
    from cobra import Metabolite, Model, Reaction

    from cmig.core.model_quality import audit_model_quality

    model = Model("transport_objective_model")
    inside = Metabolite("x_c", compartment="c", formula="C6H12O6", charge=0)
    outside = Metabolite("x_e", compartment="e", formula="C6H12O6", charge=0)
    uptake = Reaction("EX_x_e")
    uptake.add_metabolites({outside: -1})
    uptake.bounds = (-10, 1000)
    transport = Reaction("XT")                          # internal transport, not a boundary
    transport.add_metabolites({outside: -1, inside: 1})
    transport.bounds = (0, 1000)
    model.add_reactions([uptake, transport])
    model.objective = "XT"

    report = audit_model_quality(model, source_path=None, solver="gurobi")
    assert report.objective_reactions == ["XT"]
    assert any("XT" in warning and "not identifiable" in warning for warning in report.warnings)


# ── Recon3D-backed measurements ───────────────────────────────────────────────

_RECON3D = resolve_human_gem("Recon3D")
_RECON1 = resolve_human_gem("RECON1")

recon3d_only = pytest.mark.skipif(
    _RECON3D is None,
    reason="Recon3D.xml not present; run scripts/download_human_gems.py",
)
recon1_only = pytest.mark.skipif(
    _RECON1 is None,
    reason="RECON1.xml not present; run scripts/download_human_gems.py",
)


@pytest.fixture(scope="module")
def recon3d():
    import cobra.io

    return cobra.io.read_sbml_model(str(_RECON3D))


@recon3d_only
def test_recon3d_default_objective_is_maintenance_and_is_warned(recon3d):
    """The single most important scientific fact about this model, pinned.

    `BIOMASS_maintenance` optimizes to 755.0032155506631 with Gurobi. That is a maintenance
    turnover rate. Nothing in CMIG may present it as growth.
    """
    summary = summarize_host_model(recon3d)
    assert summary.model_id == "Recon3D"
    assert summary.objective_reactions == ["BIOMASS_maintenance"]
    assert summary.objective_warning is not None
    assert "MAINTENANCE" in summary.objective_warning
    # The growth reaction the model *does* have, so a caller can switch to it.
    assert "BIOMASS_reaction" in recon3d.reactions
    assert recon3d.reactions.BIOMASS_reaction.name == "Generic Human Biomass Reaction"
    assert len(recon3d.reactions.BIOMASS_reaction.metabolites) == 41


@recon3d_only
def test_recon3d_has_sink_reactions_that_can_supply_mass(recon3d):
    """Measured: 1806 boundary reactions, 1560 exchanges, 95 non-exchange boundary suppliers."""
    summary = summarize_host_model(recon3d)
    assert summary.n_boundary_reactions == 1806
    assert summary.n_exchanges == 1560
    assert summary.n_nonexchange_boundary_uptake == 95
    suppliers = nonexchange_boundary_uptake(recon3d)
    assert len(suppliers) == 95
    assert all(rid.startswith(("SK_", "DM_")) for rid in suppliers)
    assert "SK_glygn2_c" in suppliers


@recon3d_only
def test_recon3d_isolated_host_cannot_grow_on_the_bundled_pool_secretion(recon3d):
    """The honest answer for the bundled 5-member pool: acetate + ethanol + Fe2+ is not enough.

    Before the isolation fix this returned 368.01024754644214 and `viable=True`, a value the
    microbes provably did not affect (the identical number came back with zero availability).
    """
    with recon3d as model:
        model.objective = "BIOMASS_reaction"
        availability = {"ac": 2.5086897646126265, "etoh": 1.7561713989440302,
                        "fe2": 9.831532229737602}
        coupled = solve_bigg_host(
            model, availability, exchange_suffix="_e",
            exclude_metabolites={"h", "h2o", "co2"}, close_unlisted_uptake=True, solver="gurobi",
        )
    assert coupled.status == "optimal"
    assert coupled.biomass == pytest.approx(0.0, abs=1e-6)
    assert not coupled.viable
    assert any("95 non-exchange boundary" in w for w in coupled.warnings)


@recon1_only
def test_recon1_default_objective_is_a_transport_reaction_with_no_biomass():
    """RECON1 ships `S6T14g`, a Golgi sulfotransferase, and has NO biomass reaction at all."""
    import cobra.io

    model = cobra.io.read_sbml_model(str(_RECON1))
    summary = summarize_host_model(model)
    assert summary.model_id == "RECON1"
    assert summary.objective_reactions == ["S6T14g"]
    assert summary.objective_warning is not None
    assert "S6T14g" in summary.objective_warning
    assert "not identifiable as a biomass reaction" in summary.objective_warning
    biomass_like = [
        r.id for r in model.reactions
        if "biomass" in f"{r.id} {r.name or ''}".lower()
        or "growth" in f"{r.id} {r.name or ''}".lower()
    ]
    assert biomass_like == []
