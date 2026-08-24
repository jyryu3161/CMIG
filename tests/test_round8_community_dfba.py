"""Round 8 U6 — scientific pins for well-mixed MICOM community dFBA."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("micom")
pytest.importorskip("cobra")

import cobra  # noqa: E402
import micom  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from cobra import Metabolite, Model, Reaction  # noqa: E402
from micom.data import test_taxonomy as micom_test_taxonomy  # noqa: E402

from cmig.core.dfba import (  # noqa: E402
    CommunityDfbaConfig,
    DfbaConfig,
    run_community_dfba,
    simulate_dfba,
)
from cmig.io.dfba_output import (  # noqa: E402
    COMMUNITY_DFBA_TIMECOURSE_KIND,
    COMMUNITY_DFBA_TIMECOURSE_SCHEMA,
    build_community_timecourse,
    write_community_timecourse,
)

_ECOLI_CORE = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")


def _reaction(
    reaction_id: str,
    metabolites: dict[Metabolite, float],
    *,
    lower: float = 0.0,
    upper: float = 1000.0,
) -> Reaction:
    reaction = Reaction(reaction_id, lower_bound=lower, upper_bound=upper)
    reaction.add_metabolites(metabolites)
    return reaction


def _producer_model() -> Model:
    """One glucose makes one producer biomass unit and forces two cross-feed units."""
    model = Model("producer")
    glucose_e = Metabolite("glc_e", compartment="e", formula="C6H12O6")
    glucose_c = Metabolite("glc_c", compartment="c", formula="C6H12O6")
    crossfeed_e = Metabolite("xfeed_e", compartment="e", formula="C2H4O2")
    crossfeed_c = Metabolite("xfeed_c", compartment="c", formula="C2H4O2")
    biomass = _reaction(
        "BIOMASS_P", {glucose_c: -1.0, crossfeed_c: 2.0}
    )
    model.add_reactions([
        _reaction("EX_glc_e", {glucose_e: -1.0}, lower=-10.0),
        _reaction("GLCtex", {glucose_e: -1.0, glucose_c: 1.0}),
        biomass,
        _reaction("Xtex", {crossfeed_c: -1.0, crossfeed_e: 1.0}),
        _reaction("EX_xfeed_e", {crossfeed_e: -1.0}),
    ])
    model.objective = biomass
    return model


def _consumer_model() -> Model:
    """Consumer biomass has exactly one possible substrate: the producer's cross-feed."""
    model = Model("consumer")
    crossfeed_e = Metabolite("xfeed_e", compartment="e", formula="C2H4O2")
    crossfeed_c = Metabolite("xfeed_c", compartment="c", formula="C2H4O2")
    biomass = _reaction("BIOMASS_C", {crossfeed_c: -1.0})
    model.add_reactions([
        _reaction("EX_xfeed_e", {crossfeed_e: -1.0}),
        _reaction("Xtex", {crossfeed_e: -1.0, crossfeed_c: 1.0}),
        biomass,
    ])
    model.objective = biomass
    return model


def _broken_model() -> Model:
    """A fixed internal flux without a source makes the LP genuinely infeasible."""
    model = Model("broken")
    substrate_e = Metabolite("s_e", compartment="e", formula="C")
    substrate_c = Metabolite("s_c", compartment="c", formula="C")
    a_c = Metabolite("a_c", compartment="c", formula="C")
    b_c = Metabolite("b_c", compartment="c", formula="C")
    biomass = _reaction("BIOMASS", {substrate_c: -1.0})
    model.add_reactions([
        _reaction("EX_s_e", {substrate_e: -1.0}, lower=-10.0),
        _reaction("Stex", {substrate_e: -1.0, substrate_c: 1.0}),
        biomass,
        _reaction("FORCED_INTERNAL", {a_c: -1.0, b_c: 1.0}, lower=1.0, upper=1.0),
    ])
    model.objective = biomass
    return model


def _taxonomy(tmp_path: Path, models: dict[str, Model]) -> pd.DataFrame:
    rows = []
    abundance = 1.0 / len(models)
    for member, model in models.items():
        path = tmp_path / f"{member}.xml"
        cobra.io.write_sbml_model(model, path)
        rows.append({"id": member, "file": str(path), "abundance": abundance})
    return pd.DataFrame(rows)


def _crossfeed_config() -> CommunityDfbaConfig:
    return CommunityDfbaConfig(
        t_end=0.6,
        dt=0.1,
        initial_biomasses={"producer": 0.01, "consumer": 0.01},
        initial_concentrations={"EX_glc_m": 2.0, "EX_xfeed_m": 0.0},
        member_vmax={
            "producer": {"EX_glc_m": 10.0, "EX_xfeed_m": 10.0},
            "consumer": {"EX_xfeed_m": 10.0},
        },
        close_untracked_uptake=True,
    )


def test_crossfeeding_consumer_growth_depends_on_producer(tmp_path: Path) -> None:
    community_taxonomy = _taxonomy(
        tmp_path, {"producer": _producer_model(), "consumer": _consumer_model()}
    )
    with_producer = run_community_dfba(community_taxonomy, _crossfeed_config())

    consumer_taxonomy = community_taxonomy.loc[
        community_taxonomy["id"] == "consumer"
    ].copy()
    without_producer = run_community_dfba(
        consumer_taxonomy,
        CommunityDfbaConfig(
            t_end=0.6,
            dt=0.1,
            initial_biomasses={"consumer": 0.01},
            initial_concentrations={"EX_xfeed_m": 0.0},
            member_vmax={"consumer": {"EX_xfeed_m": 10.0}},
            close_untracked_uptake=True,
        ),
    )

    consumer_trajectory = [
        point.member_biomasses["consumer"] for point in with_producer.timecourse
    ]
    crossfeed_trajectory = [
        point.concentrations["EX_xfeed_m"] for point in with_producer.timecourse
    ]
    # The producer first raises the zero-initialized pool (t=0.1), after which consumer biomass
    # rises by >20x.  The 1e-10 no-growth tolerance is two orders above Gurobi feasibility
    # tolerance propagated through X0=0.01, while the positive signature has >0.2 absolute margin.
    assert with_producer.status == "completed"
    assert with_producer.acceptance.interpretable is True
    assert crossfeed_trajectory[0] == pytest.approx(0.0, abs=1e-12)
    assert crossfeed_trajectory[1] > 0.01
    assert consumer_trajectory[1] == pytest.approx(0.01, abs=1e-10)
    assert consumer_trajectory[-1] > 0.2
    assert without_producer.status == "stalled"
    assert without_producer.timecourse[-1].member_biomasses["consumer"] == pytest.approx(
        0.01, abs=1e-10
    )


def test_one_member_glucose_depletion_matches_single_model() -> None:
    taxonomy = micom_test_taxonomy().iloc[:1].copy()
    member = str(taxonomy.iloc[0]["id"])
    nutrients = {
        "glc__D": 10.0,
        "o2": 1000.0,
        "nh4": 1000.0,
        "pi": 1000.0,
        "h2o": 1000.0,
        "h": 1000.0,
        "co2": 1000.0,
    }
    community = run_community_dfba(
        taxonomy,
        CommunityDfbaConfig(
            t_end=10.0,
            dt=0.1,
            initial_biomasses={member: 0.01},
            initial_concentrations={f"EX_{name}_m": value for name, value in nutrients.items()},
            close_untracked_uptake=True,
        ),
    )
    single = simulate_dfba(
        cobra.io.read_sbml_model(_ECOLI_CORE),
        DfbaConfig(
            t_end=10.0,
            dt=0.1,
            initial_biomass=0.01,
            initial_concentrations={f"EX_{name}_e": value for name, value in nutrients.items()},
            close_untracked_uptake=True,
        ),
    )

    assert len(community.timecourse) == len(single.timecourse)
    biomass_errors = [
        abs(point.member_biomasses[member] - anchor.biomass)
        for point, anchor in zip(community.timecourse, single.timecourse, strict=True)
    ]
    glucose_errors = [
        abs(
            point.concentrations["EX_glc__D_m"]
            - anchor.concentrations["EX_glc__D_e"]
        )
        for point, anchor in zip(community.timecourse, single.timecourse, strict=True)
    ]
    time_errors = [
        abs(point.t - anchor.t)
        for point, anchor in zip(community.timecourse, single.timecourse, strict=True)
    ]
    # Both paths implement the same Euler equations.  The 1e-10 tolerance is deliberately ~500x
    # the measured cross-path maxima (2.2e-14 biomass, 1.9e-13 glucose) and still far below any
    # biologically meaningful concentration change.
    assert max(time_errors) < 1e-12
    assert max(biomass_errors) < 1e-10
    assert max(glucose_errors) < 1e-10
    assert community.timecourse[-1].concentrations["EX_glc__D_m"] < 1e-3
    assert single.timecourse[-1].concentrations["EX_glc__D_e"] < 1e-3
    assert community.status == "solver_failed"
    assert single.status == "infeasible"
    assert community.diagnostic and "solver" in community.diagnostic.lower()
    assert any(event.kind == "adaptive_dt" for event in community.events)
    assert any(event.kind == "solver_failure" for event in community.events)


def test_infeasible_community_stops_with_explicit_diagnostic(tmp_path: Path) -> None:
    taxonomy = _taxonomy(tmp_path, {"broken": _broken_model()})
    result = run_community_dfba(
        taxonomy,
        CommunityDfbaConfig(
            t_end=0.1,
            initial_biomasses={"broken": 0.01},
            initial_concentrations={"EX_s_m": 1.0},
            close_untracked_uptake=True,
        ),
    )

    # MicomEngine intentionally classifies failed primal readout as solver_failed rather than
    # guessing "infeasible".  The known-infeasible construction must still stop at t=0 and expose
    # both a structured diagnostic and event; continuing with zero/partial flux would be dishonest.
    assert result.status == "solver_failed"
    assert result.timecourse[-1].t == 0.0
    assert result.diagnostic and "could not get community growth rate" in result.diagnostic
    assert result.acceptance.interpretable is False
    assert any(event.kind == "solver_failure" for event in result.events)


def test_untracked_uptake_is_structured_and_not_interpretable() -> None:
    taxonomy = micom_test_taxonomy().iloc[:1].copy()
    member = str(taxonomy.iloc[0]["id"])
    result = run_community_dfba(
        taxonomy,
        CommunityDfbaConfig(
            t_end=0.1,
            initial_biomasses={member: 0.01},
            initial_concentrations={"EX_glc__D_m": 10.0},
        ),
    )

    assert result.status == "completed"
    assert {"EX_nh4_m", "EX_o2_m", "EX_pi_m"} <= set(result.untracked_uptake)
    assert result.acceptance.no_untracked_uptake is False
    assert result.acceptance.interpretable is False
    assert any("NOT interpretable" in warning for warning in result.warnings)
    assert any(event.kind == "untracked_uptake" for event in result.events)


def test_nonnegativity_clamp_records_event(tmp_path: Path) -> None:
    taxonomy = _taxonomy(tmp_path, {"producer": _producer_model()})
    result = run_community_dfba(
        taxonomy,
        CommunityDfbaConfig(
            t_end=0.1,
            dt=0.1,
            min_dt=0.1,
            initial_biomasses={"producer": 1.0},
            initial_concentrations={"EX_glc_m": 0.001},
            member_vmax={"producer": {"EX_glc_m": 10.0}},
            close_untracked_uptake=True,
        ),
    )

    assert result.timecourse[-1].concentrations["EX_glc_m"] == pytest.approx(0.0)
    clamp = next(event for event in result.events if event.kind == "nonnegativity_clamp")
    assert 0.0 < clamp.details["scale"] < 1.0
    assert result.acceptance.concentrations_nonnegative is True


def test_community_timecourse_has_distinct_kind_and_atomic_writer(
    tmp_path: Path,
) -> None:
    taxonomy = _taxonomy(tmp_path, {"producer": _producer_model()})
    result = run_community_dfba(
        taxonomy,
        CommunityDfbaConfig(
            t_end=0.1,
            initial_biomasses={"producer": 0.01},
            initial_concentrations={"EX_glc_m": 1.0},
            member_vmax={"producer": {"EX_glc_m": 10.0}},
            close_untracked_uptake=True,
        ),
    )
    table = build_community_timecourse(result)
    assert table.schema.equals(COMMUNITY_DFBA_TIMECOURSE_SCHEMA)
    assert set(table.column("kind").to_pylist()) == {COMMUNITY_DFBA_TIMECOURSE_KIND}
    rows = table.to_pylist()
    assert any(row["entity_type"] == "member" and row["member"] == "producer" for row in rows)
    assert any(row["entity_type"] == "shared_pool" and row["member"] is None for row in rows)

    destination = tmp_path / "community_timecourse.parquet"
    assert write_community_timecourse(result, destination) == destination
    assert pq.read_table(destination).schema.equals(COMMUNITY_DFBA_TIMECOURSE_SCHEMA)
    assert not list(tmp_path.glob(".community_timecourse.parquet.*.tmp"))
