"""Host-microbe exchange mapping wizard (§12). Pure over toy cobra models."""

from __future__ import annotations

import pytest

pytest.importorskip("cobra")

from cmig.core.host_map import build_host_map  # noqa: E402


def _ex(model, met_id, lb, ub, compartment=None):
    from cobra import Metabolite, Reaction

    met = Metabolite(met_id, compartment=compartment or met_id.rsplit("_", 1)[-1])
    rxn = Reaction(f"EX_{met_id}")
    rxn.add_metabolites({met: -1})
    rxn.bounds = (lb, ub)
    model.add_reactions([rxn])


def test_build_host_map_classifies_exact_normalized_unmatched():
    from cobra import Model

    host = Model("host")
    _ex(host, "ac_e", -1000, 1000)     # host can take up acetate
    _ex(host, "but_e", 0, 1000)        # host has butyrate exchange but uptake closed

    microbe = Model("m1")
    _ex(microbe, "ac_e", 0, 1000)        # secretes acetate -> exact match, host uptake open
    # MICOM member-suffixed id -> normalized -> host EX_but_e. (This slot used to hold
    # `but__D_e`; see test_stereoisomers_are_never_a_normalized_match for why that moved.)
    _ex(microbe, "but_e__Bacteroides", 0, 1000, compartment="e")
    _ex(microbe, "novelmet_e", 0, 1000)  # no host counterpart -> unmatched

    res = build_host_map(host, {"m1": microbe})
    by = {e.metabolite: e for e in res.entries}

    assert by["ac_e"].match_type == "exact"
    assert by["ac_e"].host_exchange == "EX_ac_e" and by["ac_e"].host_can_uptake
    assert by["ac_e"].secreting_members == ["m1"]

    assert by["but_e__Bacteroides"].match_type == "normalized"
    assert by["but_e__Bacteroides"].host_exchange == "EX_but_e"
    assert by["but_e__Bacteroides"].host_can_uptake is False   # host butyrate uptake closed

    assert by["novelmet_e"].match_type == "unmatched"
    assert by["novelmet_e"].host_exchange is None

    assert (res.n_exact, res.n_normalized, res.n_unmatched) == (1, 1, 1)
    assert res.n_host_uptake_capable == 1
    assert any("no host exchange" in w for w in res.warnings)


def test_stereoisomers_are_never_a_normalized_match():
    """Round-5 CC-7 contract change.

    This case used to be classified ``normalized``: the loose id normalizer stripped the trailing
    ``__D``/``__L`` as if it were a MICOM taxon suffix, so `lac__D_e` and `lac__L_e` collapsed to
    the same key. D- and L-lactate are different molecules with different transporters, so a
    heuristic must not assert they are interchangeable — downstream, `solve_bigg_host` opened the
    D exchange from L availability and reported the resulting biomass as a result.
    """
    from cobra import Model

    host = Model("host")
    _ex(host, "lac__L_e", -1000, 1000)     # host consumes L-lactate only
    microbe = Model("m1")
    _ex(microbe, "lac__D_e", 0, 1000)      # microbe secretes D-lactate only

    res = build_host_map(host, {"m1": microbe})
    entry = res.entries[0]
    assert entry.match_type == "unmatched"
    assert entry.host_exchange is None
    assert (res.n_exact, res.n_normalized, res.n_unmatched) == (0, 0, 1)


def test_build_host_map_ignores_uptake_only_microbial_exchanges():
    """Only secretable (upper_bound > 0) microbial exchanges are candidates."""
    from cobra import Model

    host = Model("host")
    _ex(host, "glc__D_e", -1000, 1000)
    microbe = Model("m1")
    _ex(microbe, "glc__D_e", -1000, 0)   # uptake-only (cannot secrete) -> excluded
    res = build_host_map(host, {"m1": microbe})
    assert res.n_microbial_secretions == 0


def test_build_host_map_uses_authoritative_bigg_annotation_for_non_bigg_host_ids():
    from cobra import Model

    host = Model("human_gem_style")
    _ex(host, "MAM01410e", -1000, 1000)
    host_exchange = host.reactions.get_by_id("EX_MAM01410e")
    host_exchange.id = "MAR09809"
    host_exchange.annotation = {"bigg.reaction": "EX_but_e"}
    next(iter(host_exchange.metabolites)).annotation = {"bigg.metabolite": "but"}
    microbe = Model("m1")
    _ex(microbe, "but_e", 0, 1000)

    result = build_host_map(host, {"m1": microbe})
    entry = result.entries[0]
    assert entry.match_type == "annotation"
    assert entry.host_exchange == "MAR09809"
    assert result.n_annotation == 1
