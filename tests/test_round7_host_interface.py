"""Round-7 T5: evidence-backed host interfaces and side-aware coupling."""

from __future__ import annotations

import pytest

cobra = pytest.importorskip("cobra")

from cmig.core.host import (  # noqa: E402
    classify_host_interfaces,
    run_bigg_host_microbe,
    solve_bigg_host,
    summarize_host_model,
)
from cmig.core.host_map import build_host_map  # noqa: E402
from cmig.core.host_map_probe import (  # noqa: E402
    interface_classification_probe_observations,
)
from cmig.io.gem_paths import resolve_human_gem  # noqa: E402


def _exchange(model, reaction_id, metabolite_id, compartment, bounds=(0.0, 1000.0)):
    from cobra import Metabolite, Reaction

    metabolite = Metabolite(metabolite_id, compartment=compartment)
    reaction = Reaction(reaction_id)
    reaction.add_metabolites({metabolite: -1.0})
    reaction.bounds = bounds
    model.add_reactions([reaction])
    return reaction


def _single_substrate_host(*, exchange_name: str = ""):
    from cobra import Metabolite, Model, Reaction

    model = Model("single_substrate_host")
    outside = Metabolite("ac_e", compartment="e")
    inside = Metabolite("ac_c", compartment="c")
    exchange = Reaction("EX_ac_e")
    exchange.name = exchange_name
    exchange.add_metabolites({outside: -1.0})
    exchange.bounds = (0.0, 1000.0)
    transport = Reaction("ACt")
    transport.add_metabolites({outside: -1.0, inside: 1.0})
    transport.bounds = (0.0, 1000.0)
    biomass = Reaction("BIOMASS_host")
    biomass.add_metabolites({inside: -1.0})
    biomass.bounds = (0.0, 1000.0)
    model.add_reactions([exchange, transport, biomass])
    model.objective = biomass
    return model


def _two_compartment_coupling_host():
    from cobra import Metabolite, Model, Reaction

    model = Model("two_compartment_coupling_host")
    ac_e = Metabolite("ac_e", compartment="e")
    ac_c = Metabolite("ac_c", compartment="c")
    o2_b = Metabolite("o2_blood", compartment="blood")
    o2_c = Metabolite("o2_c", compartment="c")
    ac_exchange = Reaction("EX_ac_e")
    ac_exchange.add_metabolites({ac_e: -1.0})
    ac_exchange.bounds = (0.0, 1000.0)
    blood_exchange = Reaction("BLOOD_O2")
    blood_exchange.add_metabolites({o2_b: -1.0})
    blood_exchange.bounds = (0.0, 1000.0)
    ac_transport = Reaction("ACt")
    ac_transport.add_metabolites({ac_e: -1.0, ac_c: 1.0})
    o2_transport = Reaction("O2t")
    o2_transport.add_metabolites({o2_b: -1.0, o2_c: 1.0})
    biomass = Reaction("BIOMASS_host")
    biomass.add_metabolites({ac_c: -1.0, o2_c: -1.0})
    model.add_reactions([
        ac_exchange,
        blood_exchange,
        ac_transport,
        o2_transport,
        biomass,
    ])
    model.compartments = {
        "e": "extracellular space",
        "blood": "portal blood",
        "c": "cytosol",
    }
    model.objective = biomass
    return model


def test_classifier_uses_compartment_pair_metadata_and_suffix_evidence():
    from cobra import Model

    host = Model("paired_compartment_host")
    generic = _exchange(host, "EX_ac_e", "ac_e", "e")
    blood = _exchange(host, "BLOOD_O2", "o2_b", "b")
    suffix = _exchange(host, "EX_but_lumen", "but_lumen", "lumen")
    host.compartments = {
        "e": "extracellular space",
        "b": "portal blood",
        "lumen": "intestinal lumen",
    }

    result = classify_host_interfaces(host)
    by_exchange = result.by_exchange()

    assert by_exchange[generic.id].interface == "lumen"
    assert any(
        evidence.rule == "paired_external_compartment"
        for evidence in by_exchange[generic.id].evidence
    )
    assert by_exchange[blood.id].interface == "blood"
    assert any(
        evidence.rule == "explicit_compartment"
        for evidence in by_exchange[blood.id].evidence
    )
    assert by_exchange[suffix.id].interface == "lumen"
    assert any(
        evidence.rule == "exchange_id_suffix"
        for evidence in by_exchange[suffix.id].evidence
    )
    assert result.has_lumen_blood_interfaces
    assert result.complete


def test_generic_extracellular_alone_is_not_silently_called_lumen():
    host = _single_substrate_host()

    summary = summarize_host_model(host)

    assert not summary.has_lumen_blood_interfaces
    assert summary.interface_classification["n_unclassified"] == 1
    assert summary.interface_classification["assignments"] == []


def test_reaction_and_metabolite_annotations_are_reviewable_side_evidence():
    from cobra import Model

    host = Model("annotated_host")
    lumen = _exchange(host, "EX_drug_e", "drug_e", "e")
    lumen.annotation = {"cmig.interface": "apical lumen"}
    blood = _exchange(host, "EX_hormone_e", "hormone_e", "e")
    next(iter(blood.metabolites)).annotation = {
        "cmig.interface": "basolateral blood"
    }

    result = classify_host_interfaces(host)
    by_exchange = result.by_exchange()

    assert by_exchange[lumen.id].interface == "lumen"
    assert by_exchange[lumen.id].evidence[0].rule == "reaction_annotation"
    assert by_exchange[blood.id].interface == "blood"
    assert by_exchange[blood.id].evidence[0].rule == "metabolite_annotation"


def test_conflicting_signals_stay_unclassified_until_reviewed_override():
    host = _single_substrate_host(exchange_name="Exchange in portal blood")
    exchange = host.reactions.get_by_id("EX_ac_e")
    exchange.id = "EX_ac_lumen"
    host.repair()

    conflict = classify_host_interfaces(host)
    assert conflict.assignments == ()
    assert conflict.conflicted_exchange_ids == ("EX_ac_lumen",)

    reviewed = classify_host_interfaces(
        host,
        interface_map={
            "ac": {"host_exchange": "EX_ac_lumen", "interface": "lumen"}
        },
    )
    assignment = reviewed.assignments[0]
    assert assignment.interface == "lumen"
    assert assignment.reviewed
    assert assignment.evidence[0].rule == "reviewed_interface_map"


def test_host_map_carries_inferred_side_and_reviewed_override_evidence():
    from cobra import Model

    host = Model("host")
    host_exchange = _exchange(host, "EX_ac_e", "ac_e", "e", (-1000.0, 1000.0))
    host_exchange.name = "Exchange reaction for acetate in portal blood"
    microbe = Model("microbe")
    _exchange(microbe, "EX_ac_e", "ac_e", "e")

    inferred = build_host_map(host, {"m": microbe})
    assert inferred.entries[0].interface == "blood"
    assert inferred.entries[0].interface_evidence[0]["rule"] == "side_specific_metadata"
    assert inferred.n_blood == 1

    reviewed = build_host_map(
        host,
        {"m": microbe},
        interface_map={
            "ac_e": {"host_exchange": "EX_ac_e", "interface": "lumen"}
        },
    )
    assert reviewed.entries[0].interface == "lumen"
    assert reviewed.entries[0].interface_evidence[0]["rule"] == "reviewed_interface_map"
    assert reviewed.n_lumen == 1


def test_host_map_sees_explicit_blood_boundary_outside_cobra_exchange_accessor():
    from cobra import Model

    host = _two_compartment_coupling_host()
    microbe = Model("microbe")
    _exchange(microbe, "EX_o2_e", "o2_e", "e")

    result = build_host_map(host, {"m": microbe})
    entry = result.entries[0]

    assert entry.host_exchange == "BLOOD_O2"
    assert entry.match_type == "normalized"
    assert entry.interface == "blood"
    assert entry.interface_evidence[0]["rule"] == "explicit_compartment"


def test_plain_reviewed_map_keeps_legacy_coupling_meaning():
    """A pre-round-7 string map still couples even if new metadata calls the route blood-side."""
    pytest.importorskip("gurobipy")
    host = _single_substrate_host(exchange_name="Exchange in portal blood")

    result = solve_bigg_host(
        host,
        {"ac": 5.0},
        interface_map={"ac": "EX_ac_e"},
        solver="gurobi",
    )

    assert result.status == "optimal"
    assert result.biomass == pytest.approx(5.0)
    flux = next(item for item in result.interface_fluxes if item.exchange_id == "EX_ac_e")
    assert flux.interface == "bigg_external"
    assert flux.evidence == ()


def test_structured_map_enforces_lumen_only_microbial_coupling():
    pytest.importorskip("gurobipy")
    host = _single_substrate_host()

    blood = solve_bigg_host(
        host,
        {"ac": 5.0},
        interface_map={
            "ac": {"host_exchange": "EX_ac_e", "interface": "blood"}
        },
        solver="gurobi",
    )
    assert blood.status == "optimal"
    assert blood.biomass == pytest.approx(0.0)
    assert blood.lumen_uptake == {}
    assert any("blood/basolateral" in warning for warning in blood.warnings)

    lumen = solve_bigg_host(
        host,
        {"ac": 5.0},
        interface_map={
            "ac": {"host_exchange": "EX_ac_e", "interface": "lumen"}
        },
        solver="gurobi",
    )
    assert lumen.biomass == pytest.approx(5.0)
    flux = next(item for item in lumen.interface_fluxes if item.exchange_id == "EX_ac_e")
    assert flux.interface == "lumen"
    assert flux.evidence[0]["rule"] == "reviewed_interface_map"


def test_structured_blood_side_accepts_host_medium_not_microbes():
    pytest.importorskip("gurobipy")
    host = _single_substrate_host()
    interface_map = {
        "ac": {"host_exchange": "EX_ac_e", "interface": "blood"}
    }

    result = solve_bigg_host(
        host,
        {},
        host_medium={"ac": 3.0},
        interface_map=interface_map,
        solver="gurobi",
    )
    assert result.biomass == pytest.approx(3.0)
    flux = next(item for item in result.interface_fluxes if item.exchange_id == "EX_ac_e")
    assert flux.interface == "blood"

    with pytest.raises(ValueError, match="host_medium is the blood/basolateral supply"):
        solve_bigg_host(
            host,
            {},
            host_medium={"ac": 3.0},
            interface_map={
                "ac": {"host_exchange": "EX_ac_e", "interface": "lumen"}
            },
            solver="gurobi",
        )


def test_two_compartment_coupling_opens_lumen_and_blood_boundaries_independently():
    pytest.importorskip("gurobipy")
    host = _two_compartment_coupling_host()
    interface_map = {
        "ac": {"host_exchange": "EX_ac_e", "interface": "lumen"},
        "o2": {"host_exchange": "BLOOD_O2", "interface": "blood"},
    }

    result = solve_bigg_host(
        host,
        {"ac": 2.0},
        host_medium={"o2": 3.0},
        interface_map=interface_map,
        solver="gurobi",
    )

    assert result.status == "optimal"
    assert result.biomass == pytest.approx(2.0)
    by_exchange = {item.exchange_id: item for item in result.interface_fluxes}
    assert by_exchange["EX_ac_e"].interface == "lumen"
    assert by_exchange["BLOOD_O2"].interface == "blood"


def test_host_map_probe_carries_side_evidence_without_changing_legacy_map_digest():
    observations = interface_classification_probe_observations()["classification"]
    assert observations["n_lumen"] == 1
    assert observations["n_blood"] == 1
    assignments = {item["exchange_id"]: item for item in observations["assignments"]}
    assert assignments["EX_sfx_lumen"]["evidence"][0]["rule"] == "exchange_id_suffix"
    assert assignments["EX_ste_e"]["evidence"][0]["rule"] == "side_specific_metadata"


def test_host_static_reexports_have_no_module_getattr_cycle_workaround():
    from cmig.core import host

    assert "__getattr__" not in host.__dict__
    assert callable(run_bigg_host_microbe)
    assert callable(solve_bigg_host)


@pytest.mark.skipif(
    resolve_human_gem("RECON1") is None,
    reason="RECON1.xml not present; run scripts/download_human_gems.py",
)
def test_recon1_generic_extracellular_boundary_remains_honestly_unclassified():
    model = cobra.io.read_sbml_model(str(resolve_human_gem("RECON1")))

    classification = classify_host_interfaces(model)

    assert classification.n_exchanges == 404
    assert classification.assignments == ()
    assert len(classification.unclassified_exchange_ids) == 404
    assert classification.conflicted_exchange_ids == ()
    assert not classification.has_lumen_blood_interfaces
