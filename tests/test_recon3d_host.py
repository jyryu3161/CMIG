"""Recon3D generic human GEM smoke tests.

`Recon3D.xml` is a user-provided generic human model. It is not a CMIG 2-interface host
fixture, so these tests validate honest generic-GEM handling instead of pretending it has
`_lumen`/`_blood` coupling exchanges.
"""

from __future__ import annotations

import pytest
from _gem_fixtures import human_gem_path, human_gem_skip_reason

from cmig.core.host import solve_generic_host, summarize_host_model

cobra = pytest.importorskip("cobra")

# Round 6 (P2): the resolution order used to be `$CMIG_RECON3D_PATH`, `fixtures/`, `./` — none of
# which is where the download script puts the file, so these tests skipped for the entire life of
# the project and the skip read as a pass. The order now lives in `_gem_fixtures` and includes
# `data/gems`, and `test_round6_boundary_regressions` asserts that entry directly, so removing it
# fails a test instead of silently re-skipping this module.
_RECON3D = human_gem_path("Recon3D.xml")

pytestmark = pytest.mark.skipif(
    _RECON3D is None, reason=human_gem_skip_reason("Recon3D.xml")
)


def test_recon3d_summary_detects_generic_human_gem():
    model = cobra.io.read_sbml_model(str(_RECON3D))
    summary = summarize_host_model(model)

    assert summary.model_id == "Recon3D"
    assert summary.n_reactions > 10_000
    assert summary.n_metabolites > 5_000
    assert summary.n_genes > 2_000
    assert summary.n_exchanges > 1_000
    assert "BIOMASS_maintenance" in summary.objective_reactions
    assert "e" in summary.compartments
    assert not summary.has_lumen_blood_interfaces
    assert summary.exchange_examples[0].startswith("EX_")


def test_recon3d_solves_as_generic_host_with_gurobi():
    model = cobra.io.read_sbml_model(str(_RECON3D))
    result = solve_generic_host(model, solver="gurobi")

    assert result.status == "optimal"
    assert result.viable
    assert result.biomass > 1.0
    assert result.interface_fluxes == []
    assert result.lumen_uptake == {}
