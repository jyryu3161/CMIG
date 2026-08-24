"""Recon3D generic human GEM smoke tests.

`Recon3D.xml` is a user-provided generic human model. It has no `_lumen`/`_blood` ids, but its
exchange names contain a small, reviewable set of intestinal-lumen and portal-blood assignments.
The remaining generic extracellular exchanges stay unclassified, so partial evidence is never
promoted to quantitative-coupling readiness.

Round 6 (track H): these had skipped for the project's entire life because the resolution order
looked only at `$CMIG_RECON3D_PATH`, `fixtures/Recon3D.xml` and `./Recon3D.xml` — never at
`data/gems/`, which is where `scripts/download_human_gems.py` actually puts the model. Resolution
now goes through :mod:`cmig.io.gem_paths` so the CLI defaults and these tests search the same
places. The assertions were also thin: `biomass > 1.0` on Recon3D passes on 755.003, which is a
**maintenance** optimum, so the test as written asserted that a maintenance rate is a healthy
biomass. It now pins the measured value and requires the objective-structure verdict alongside it.
"""

from __future__ import annotations

import pytest

from cmig.core.host import benchmark_generic_host, solve_generic_host, summarize_host_model
from cmig.io.gem_paths import human_gem_candidates, resolve_human_gem

cobra = pytest.importorskip("cobra")


_RECON3D = resolve_human_gem("Recon3D")

pytestmark = pytest.mark.skipif(
    _RECON3D is None,
    reason=(
        "Recon3D.xml not found in any of "
        + ", ".join(str(path) for path in human_gem_candidates("Recon3D"))
        + " — run scripts/download_human_gems.py"
    ),
)

#: Gurobi optimum of Recon3D's SHIPPED DEFAULT objective `BIOMASS_maintenance`. This is a
#: maintenance turnover rate, NOT a growth rate, and is pinned here so that a change to the
#: objective handling shows up as a number rather than as prose.
_MAINTENANCE_OPTIMUM = 755.0032155506631


@pytest.fixture(scope="module")
def recon3d():
    return cobra.io.read_sbml_model(str(_RECON3D))


def test_recon3d_summary_detects_generic_human_gem(recon3d):
    summary = summarize_host_model(recon3d)

    assert summary.model_id == "Recon3D"
    assert summary.n_reactions == 10600
    assert summary.n_metabolites == 5835
    assert summary.n_genes == 2248
    assert summary.n_exchanges == 1560
    assert summary.objective_reactions == ["BIOMASS_maintenance"]
    assert sorted(summary.compartments) == ["c", "e", "g", "i", "l", "m", "n", "r", "x"]
    assert summary.has_lumen_blood_interfaces
    assert summary.interface_classification["n_lumen"] == 25
    assert summary.interface_classification["n_blood"] == 31
    assert summary.interface_classification["n_unclassified"] == 1504
    assert summary.interface_classification["n_conflicted"] == 0
    assert summary.interface_classification["complete"] is False
    assert all(
        assignment["evidence"]
        for assignment in summary.interface_classification["assignments"]
    )
    assert summary.exchange_examples[0].startswith("EX_")


def test_recon3d_summary_says_the_default_objective_is_not_growth(recon3d):
    """The shipped default is maintenance. A summary that omits that invites a wrong claim."""
    summary = summarize_host_model(recon3d)
    assert summary.objective_warning is not None
    assert "MAINTENANCE" in summary.objective_warning
    assert "NOT a growth rate" in summary.objective_warning


def test_recon3d_solves_as_generic_host_with_gurobi(recon3d):
    """The generic smoke solve reports the model's own objective — here, maintenance."""
    result = solve_generic_host(recon3d, solver="gurobi")

    assert result.status == "optimal"
    assert result.viable
    # Pinned, not `> 1.0`: the loose bound passed on a maintenance optimum without noticing.
    assert result.biomass == pytest.approx(_MAINTENANCE_OPTIMUM, rel=1e-9)
    assert len(result.interface_fluxes) == 56
    assert {item.interface for item in result.interface_fluxes} == {"lumen", "blood"}
    assert all(item.evidence for item in result.interface_fluxes)
    assert result.lumen_uptake == {}


def test_recon3d_benchmark_warns_that_the_objective_is_not_growth(recon3d):
    """`host-benchmark` reported 755.003 with a warnings list that mentioned only the interfaces."""
    result = benchmark_generic_host(recon3d, solver="gurobi")

    assert result.solve.status == "optimal"
    assert result.solve.biomass == pytest.approx(_MAINTENANCE_OPTIMUM, rel=1e-9)
    assert not result.quantitative_coupling_ready
    assert any("MAINTENANCE" in warning for warning in result.warnings)
    assert any(
        "sinks/demands" in warning and "not attributable" in warning
        for warning in result.warnings
    )
    assert any(
        "classification is partial" in warning and "1504 unclassified" in warning
        for warning in result.warnings
    )


def test_recon3d_growth_objective_is_available_and_distinct_from_maintenance(recon3d):
    """A growth question has an answer on this model — it just is not the default objective."""
    with recon3d as model:
        model.objective = "BIOMASS_reaction"
        summary = summarize_host_model(model)
        assert summary.objective_reactions == ["BIOMASS_reaction"]
        assert summary.objective_warning is None
        result = solve_generic_host(model, solver="gurobi")
    assert result.status == "optimal"
    # Not equal to the maintenance optimum: they are different questions about the same model.
    assert result.biomass != pytest.approx(_MAINTENANCE_OPTIMUM, rel=1e-6)
    # Both optima are large because Recon3D's boundary bounds are ±1000 with no physiological
    # calibration; neither number is a physiological human growth rate.
    assert result.biomass > 1.0
