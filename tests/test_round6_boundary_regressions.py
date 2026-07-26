"""Round 6 track B — the findings that travelled with the enumeration defect.

Four separate defects, each measured before it was fixed:

1. **[P0] id-case mapping divergence.** ``run_bigg_host_microbe`` resolved a host exchange from the
   raw metabolite id and ``solve_bigg_host`` from the lowercased one, so a stereo metabolite was
   *reported* as mapped while the LP opened a reaction that does not exist.
2. **[P1] the objective guard never reached the host-coupling commands.**
3. **[P1] a provenance marker that no reader could see**, because ``_compact_manifest`` is a
   whitelist and the marker was added to the writer only.
4. **[P2] `solve_host` on a generic GEM** reported a phantom-fed viable objective.

Plus the P2 coverage guard: the ``data/gems`` entry in the human-GEM search order, whose removal
turned nine failing tests into nine skips and a green exit code.
"""

from __future__ import annotations

import json

import pytest

cobra = pytest.importorskip("cobra")

from _gem_fixtures import (  # noqa: E402
    GEM_DIR_ENV,
    HUMAN_GEM_SEARCH,
    human_gem_path,
    human_gem_skip_reason,
)

# ── 1 [P0]: one id resolver, so the reported map and the applied bounds cannot diverge ──────────


def _stereo_route_host() -> cobra.Model:
    """A host that can take up and metabolise D-lactate. There is no ``EX_lac__d_e``."""
    from cobra import Metabolite, Model, Reaction

    model = Model("stereo_route")
    lac_d_e = Metabolite("lac__D_e", compartment="e")
    lac_d_c = Metabolite("lac__D_c", compartment="c")
    model.add_metabolites([lac_d_e, lac_d_c])
    ex = Reaction("EX_lac__D_e", lower_bound=0.0, upper_bound=1000.0)
    ex.add_metabolites({lac_d_e: -1.0})
    transport = Reaction("LACDt", lower_bound=0.0, upper_bound=1000.0)
    transport.add_metabolites({lac_d_e: -1.0, lac_d_c: 1.0})
    biomass = Reaction("BIOMASS_host", lower_bound=0.0, upper_bound=1000.0)
    biomass.add_metabolites({lac_d_c: -1.0})
    model.add_reactions([ex, transport, biomass])
    model.objective = "BIOMASS_host"
    return model


def test_solve_bigg_host_opens_the_exchange_the_raw_metabolite_id_names():
    """``lac__D`` must resolve to ``EX_lac__D_e``, not to the non-existent ``EX_lac__d_e``.

    BiGG metabolite ids are case-sensitive. Normalization exists to make interface-map lookup and
    currency exclusion tolerant; lowercasing an id before *constructing* a reaction name was never
    part of that, and it silently fed the host nothing.
    """
    pytest.importorskip("gurobipy")
    from cmig.core.host_coupling import solve_bigg_host

    result = solve_bigg_host(
        _stereo_route_host(), {"lac__D": 5.0}, close_unlisted_uptake=True, solver="gurobi"
    )

    assert result.status == "optimal"
    assert result.biomass == pytest.approx(5.0)
    assert result.viable is True


def test_the_reported_map_and_the_applied_bounds_come_from_one_resolver():
    """``matched_exchanges`` was measured to name a reaction the LP never opened.

    Measured before the fix: ``matched_exchanges {'lac__D': 'EX_lac__D_e'}`` published alongside
    host biomass ``0.0`` and ``warnings: []`` — the run asserted a mapping and delivered none.
    """
    pytest.importorskip("gurobipy")
    from cmig.core.engine import SolveResult
    from cmig.core.host_coupling import run_bigg_host_microbe

    class _Engine:
        def build_community(self, _taxonomy, cmig_solver="gurobi"):
            return object()

        def cooperative_tradeoff(self, _community, _tradeoff_f, *, cmig_solver="gurobi"):
            return SolveResult(
                objective=0.4,
                member_growth={"A": 0.4},
                abundances={"A": 1.0},
                external_exchange={"lac__D": 5.0},
                member_exchange={"A": {"lac__D": 5.0}},
                status="optimal",
                flux_report_status="full",
                growth_solver="gurobi",
                flux_solver="gurobi",
                members=["A"],
            )

    result = run_bigg_host_microbe(
        None,
        _stereo_route_host(),
        microbial_biomass_gdw=1.0,
        host_biomass_gdw=1.0,
        biomass_basis_kind="validation",
        biomass_basis_source="round-6 track B regression fixture",
        engine=_Engine(),
    )

    assert result.matched_exchanges == {"lac__D": "EX_lac__D_e"}
    assert result.unmatched_metabolites == []
    # The claim and the LP agree: the mapped exchange actually fed the host.
    assert result.host_result.biomass > 0.0


# ── 2 [P1]: the objective guard reaches every host-coupling command, from one place ─────────────


def _demand_objective_host() -> cobra.Model:
    """Objective is a plain demand reaction with no biomass identity — not a growth rate."""
    from cobra import Metabolite, Model, Reaction

    model = Model("demand_objective")
    ac_e = Metabolite("ac_e", compartment="e")
    ac_c = Metabolite("ac_c", compartment="c")
    model.add_metabolites([ac_e, ac_c])
    ex = Reaction("EX_ac_e", lower_bound=0.0, upper_bound=1000.0)
    ex.add_metabolites({ac_e: -1.0})
    transport = Reaction("ACt", lower_bound=0.0, upper_bound=1000.0)
    transport.add_metabolites({ac_e: -1.0, ac_c: 1.0})
    demand = Reaction("DM_ac_c", lower_bound=0.0, upper_bound=1000.0)
    demand.add_metabolites({ac_c: -1.0})
    model.add_reactions([ex, transport, demand])
    model.objective = "DM_ac_c"
    return model


def test_host_coupling_reports_a_non_biomass_host_objective():
    """`--host-objective` is optional, so the guard has to run on whatever the SBML shipped.

    RECON1's default objective is ``S6T14g``, a Golgi sulfotransferase whose optimum is 0.0.
    Round 5 added this guard and wired it into `strain-growth` and `model-quality` only, so all
    three host-coupling commands published `host_objective` with no caveat anywhere. They all go
    through `run_bigg_host_microbe`, which is why the call is there and not in three CLI handlers.
    """
    pytest.importorskip("gurobipy")
    from cmig.core.engine import SolveResult
    from cmig.core.host_coupling import run_bigg_host_microbe

    class _Engine:
        def build_community(self, _taxonomy, cmig_solver="gurobi"):
            return object()

        def cooperative_tradeoff(self, _community, _tradeoff_f, *, cmig_solver="gurobi"):
            return SolveResult(
                objective=0.4, member_growth={"A": 0.4}, abundances={"A": 1.0},
                external_exchange={"ac": 5.0}, member_exchange={"A": {"ac": 5.0}},
                status="optimal", flux_report_status="full",
                growth_solver="gurobi", flux_solver="gurobi", members=["A"],
            )

    result = run_bigg_host_microbe(
        None,
        _demand_objective_host(),
        microbial_biomass_gdw=1.0,
        host_biomass_gdw=1.0,
        biomass_basis_kind="validation",
        biomass_basis_source="round-6 track B regression fixture",
        exclude_metabolites=set(),
        engine=_Engine(),
    )

    assert result.objective_reactions == ["DM_ac_c"]
    assert result.objective_warning is not None
    assert "boundary reaction" in result.objective_warning
    # It reaches the payload every host-coupling command publishes.
    assert any("host objective:" in warning for warning in result.warnings)


def test_the_objective_guard_runs_even_when_the_community_solve_fails():
    """An unusable objective is a property of the input, not of the solve, so it is not lost."""
    from cmig.core.engine import SolveResult
    from cmig.core.host_coupling import run_bigg_host_microbe

    class _Engine:
        def build_community(self, _taxonomy, cmig_solver="gurobi"):
            return object()

        def cooperative_tradeoff(self, _community, _tradeoff_f, *, cmig_solver="gurobi"):
            return SolveResult(
                objective=0.0, member_growth={}, abundances={}, external_exchange={},
                member_exchange={}, status="infeasible", flux_report_status="none",
                growth_solver="gurobi", flux_solver="gurobi", members=["A"],
            )

    result = run_bigg_host_microbe(
        None, _demand_objective_host(),
        microbial_biomass_gdw=1.0, host_biomass_gdw=1.0,
        biomass_basis_kind="validation", biomass_basis_source="fixture",
        engine=_Engine(),
    )

    assert result.objective_warning is not None
    assert any("host objective:" in warning for warning in result.warnings)


# ── 3 [P1]: every non-hashed provenance marker must reach `inspect-run` ─────────────────────────


def test_every_provenance_marker_survives_the_inspect_run_whitelist():
    """`_compact_manifest` is a whitelist, and a marker missing from it is invisible to readers.

    This is a *structural* assertion, not a spot check on today's two markers: it enumerates the
    mapping the writers stamp from and requires each key to survive the projection. Adding a
    marker without wiring the reader is what made `host_isolation_policy` unreadable.
    """
    from cmig.cli.main import _compact_manifest
    from cmig.core.workflow_manifest import NON_HASHED_PROVENANCE_MARKERS

    manifest = {key: value for key, value in NON_HASHED_PROVENANCE_MARKERS.items()}
    manifest["something_not_whitelisted"] = "dropped"
    compact = _compact_manifest(manifest)

    assert set(NON_HASHED_PROVENANCE_MARKERS) <= set(compact)
    for key, value in NON_HASHED_PROVENANCE_MARKERS.items():
        assert compact[key] == value
    assert "something_not_whitelisted" not in compact


def test_a_workflow_manifest_stamps_every_marker_and_inspect_run_shows_them():
    """End-to-end through the writer and the reader, not just through the whitelist."""
    import tempfile
    from pathlib import Path

    from cmig.cli.main import _inspect_run_dir
    from cmig.core.workflow_manifest import (
        NON_HASHED_PROVENANCE_MARKERS,
        base_components,
        medium_component,
        write_workflow_manifest,
    )

    components = base_components(
        "host_map",
        solver_setting={"solver": None},
        model_checksum="sha256:round6-track-b-fixture",
        medium=medium_component(None, "host_map_no_medium"),
    )
    components["host_spec"] = {"host": "fixture"}
    components["map_spec"] = {"policy": "fixture"}

    with tempfile.TemporaryDirectory() as raw:
        out = Path(raw)
        write_workflow_manifest(out, "host_map", components, status="ok", artifacts=[])
        stored = json.loads((out / "manifest.json").read_text())
        payload = _inspect_run_dir(out)

    for key, value in NON_HASHED_PROVENANCE_MARKERS.items():
        assert stored[key] == value, f"{key} is missing from manifest.json"
        assert payload["manifest"].get(key) == value, f"{key} does not reach inspect-run"


def test_a_solve_manifest_carries_the_markers_into_inspect_run(tmp_path):
    """The solve path stamps the same markers, inside `provenance`, and they reach `inspect-run`."""
    pytest.importorskip("gurobipy")
    pytest.importorskip("micom")
    from cmig.cli.main import _inspect_run_dir, main
    from cmig.core.workflow_manifest import NON_HASHED_PROVENANCE_MARKERS

    out = tmp_path / "fixture"
    assert main(["solve-fixture", "--solver", "gurobi", "--out", str(out)]) == 0
    payload = _inspect_run_dir(out)
    provenance = payload["manifest"]["provenance"]

    for key, value in NON_HASHED_PROVENANCE_MARKERS.items():
        assert provenance[key] == value, f"{key} does not reach inspect-run on a solve manifest"


def test_the_markers_are_not_hash_components():
    """A marker that moved a hash would defeat its own purpose."""
    from cmig.core.manifest import RUN_HASH_COMPONENTS
    from cmig.core.workflow_manifest import (
        NON_HASHED_PROVENANCE_MARKERS,
        workflow_components_for,
    )

    for key in NON_HASHED_PROVENANCE_MARKERS:
        assert key not in RUN_HASH_COMPONENTS
        for kind in ("host_map", "community_solve"):
            try:
                components = workflow_components_for(kind)
            except (KeyError, ValueError):
                continue
            assert key not in components


# ── 4 [P2]: `solve_host` refuses a generic GEM instead of answering a different question ────────


def test_solve_host_refuses_a_generic_gem_rather_than_reporting_a_phantom_objective():
    """Recon3D has `ATPM`, so the maintenance check passed and a phantom-fed objective was viable.

    `solve_host` implements the lumen/blood contract: the lumen is closed and only microbial
    secretion may enter. Recon3D exposes 1560 `EX_*` reactions in neither interface, so the old
    closure loop matched none of them and every one stayed open.
    """
    pytest.importorskip("gurobipy")
    from cmig.core.diagnostics import DiagnosticCode
    from cmig.core.host import solve_host

    path = human_gem_path("Recon3D.xml")
    if path is None:
        pytest.skip(human_gem_skip_reason("Recon3D.xml"))
    host = cobra.io.read_sbml_model(str(path))

    result = solve_host(host, {}, solver="gurobi")

    assert result.viable is False
    assert result.biomass == 0.0
    assert result.diagnostic is not None
    assert DiagnosticCode.HOST_INTERFACE_ABSENT.value in result.diagnostic


def test_solve_host_still_serves_the_two_interface_contract_it_was_written_for():
    """The guard must not break the legitimate path: a lumen/blood host still solves."""
    pytest.importorskip("gurobipy")
    from cmig.core.host import solve_host
    from tests.test_host import build_host_model, lumen_availability_from_pair  # noqa: PLC0415

    result = solve_host(build_host_model(), lumen_availability_from_pair(), solver="gurobi")
    assert result.status == "optimal"


# ── P2: the coverage guard on the human-GEM search order ────────────────────────────────────────


def test_human_gem_search_order_includes_data_gems():
    """Removing this entry re-skipped nine tests and exited 0. A re-skip is not detection.

    The human GEMs are gitignored 27 MB / 14 MB binaries, so their tests legitimately skip when
    absent — which makes the search order itself the only thing that can be asserted
    unconditionally. `data/gems` is where the download puts them; without that entry the suite
    goes green by testing nothing.
    """
    assert "data/gems" in HUMAN_GEM_SEARCH
    assert HUMAN_GEM_SEARCH.index("data/gems") < HUMAN_GEM_SEARCH.index("fixtures")
    assert GEM_DIR_ENV == "CMIG_GEM_DIR"


def test_a_human_gem_skip_names_every_location_it_searched():
    """A skip nobody can diagnose is how the previous one survived a whole project."""
    reason = human_gem_skip_reason("Recon3D.xml")
    assert "$CMIG_RECON3D_PATH" in reason
    assert "data/gems/Recon3D.xml" in reason
    assert "$CMIG_GEM_DIR/Recon3D.xml" in reason
