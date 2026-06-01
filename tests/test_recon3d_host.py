"""Recon3D generic human GEM smoke tests.

`Recon3D.xml` is a user-provided generic human model. It is not a CMIG 2-interface host
fixture, so these tests validate honest generic-GEM handling instead of pretending it has
`_lumen`/`_blood` coupling exchanges.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmig.core.host import solve_generic_host, summarize_host_model

cobra = pytest.importorskip("cobra")


_ROOT = Path(__file__).resolve().parents[1]


def _recon3d_path() -> Path:
    env_path = os.environ.get("CMIG_RECON3D_PATH")
    if env_path:
        return Path(env_path).expanduser()
    for candidate in (_ROOT / "fixtures" / "Recon3D.xml", _ROOT / "Recon3D.xml"):
        if candidate.exists():
            return candidate
    return _ROOT / "fixtures" / "Recon3D.xml"


_RECON3D = _recon3d_path()


pytestmark = pytest.mark.skipif(
    not _RECON3D.exists(), reason="Recon3D.xml fixture is not present"
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
