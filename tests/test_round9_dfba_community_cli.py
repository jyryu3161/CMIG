"""Round 9 V1 — reachable community dFBA CLI and reproducibility envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("cobra")
pytest.importorskip("micom")

import cobra  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from cobra import Metabolite, Model, Reaction  # noqa: E402

from cmig.cli.main import _inspect_run_dir, main  # noqa: E402
from cmig.io.dfba_output import COMMUNITY_DFBA_TIMECOURSE_KIND  # noqa: E402


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
    model = Model("producer")
    glucose_e = Metabolite("glc_e", compartment="e", formula="C6H12O6")
    glucose_c = Metabolite("glc_c", compartment="c", formula="C6H12O6")
    crossfeed_e = Metabolite("xfeed_e", compartment="e", formula="C2H4O2")
    crossfeed_c = Metabolite("xfeed_c", compartment="c", formula="C2H4O2")
    biomass = _reaction("BIOMASS_P", {glucose_c: -1.0, crossfeed_c: 2.0})
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


def _taxonomy(path: Path, models: dict[str, Model]) -> Path:
    model_dir = path / "models"
    model_dir.mkdir(parents=True)
    rows = []
    for member, model in models.items():
        model_path = model_dir / f"{member}.xml"
        cobra.io.write_sbml_model(model, model_path)
        rows.append({
            "id": member,
            "file": str(model_path.relative_to(path)),
            "abundance": 1.0 / len(models),
        })
    taxonomy_path = path / "taxonomy.csv"
    pd.DataFrame(rows).to_csv(taxonomy_path, index=False)
    return taxonomy_path


def _crossfeed_argv(taxonomy: Path, out: Path) -> list[str]:
    return [
        "dfba-community",
        "--taxonomy", str(taxonomy),
        "--t-end", "0.6",
        "--dt", "0.1",
        "--initial", "EX_glc_m=2",
        "--initial", "EX_xfeed_m=0",
        "--initial-biomass", "producer=0.01",
        "--initial-biomass", "consumer=0.01",
        "--member-vmax", "producer:EX_glc_m=10",
        "--member-vmax", "producer:EX_xfeed_m=10",
        "--member-vmax", "consumer:EX_xfeed_m=10",
        "--close-untracked-uptake",
        "--out", str(out),
    ]


def test_crossfeeding_cli_writes_interpretable_inspectable_run(tmp_path: Path) -> None:
    taxonomy = _taxonomy(
        tmp_path, {"producer": _producer_model(), "consumer": _consumer_model()}
    )
    out = tmp_path / "run"

    assert main(_crossfeed_argv(taxonomy, out)) == 0

    expected = {
        "community_dfba_summary.json",
        "community_dfba_timecourse.parquet",
        "community_dfba_events.json",
        "manifest.json",
    }
    assert expected <= {path.name for path in out.iterdir()}
    summary = json.loads((out / "community_dfba_summary.json").read_text())
    assert summary["status"] == "completed"
    assert summary["acceptance"]["interpretable"] is True
    assert summary["final_member_biomasses"]["consumer"] > 0.2
    assert summary["config"]["initial_abundances"] == {
        "consumer": 0.5,
        "producer": 0.5,
    }
    assert summary["timing"]["n_step_solves"] == len(
        summary["timing"]["step_solve_seconds"]
    )
    assert summary["timing"]["community_build_seconds"] >= 0.0

    timecourse = pq.read_table(out / "community_dfba_timecourse.parquet")
    assert set(timecourse.column("kind").to_pylist()) == {COMMUNITY_DFBA_TIMECOURSE_KIND}
    events = json.loads((out / "community_dfba_events.json").read_text())
    assert events["n_events"] == len(events["events"])

    manifest = json.loads((out / "manifest.json").read_text())
    components = dict(manifest["components"])
    spec = components["community_dfba_spec"]
    assert manifest["workflow_kind"] == "community_dfba"
    assert spec["initial_biomasses"] == {"consumer": 0.01, "producer": 0.01}
    assert spec["initial_concentrations"] == {"EX_glc_m": 2.0, "EX_xfeed_m": 0.0}
    assert spec["member_vmax"]["consumer"] == {"EX_xfeed_m": 10.0}
    assert spec["death_washout"] == "not_modeled"
    assert not ({"timing", "events", "acceptance"} & set(spec))
    assert manifest["result_digest"]["cross_run_comparable"] is False

    inspection = _inspect_run_dir(out)
    assert inspection["kind"] == "community_dfba"
    assert inspection["summary_file"] == "community_dfba_summary.json"
    assert inspection["run_hash"] == manifest["run_hash"]
    assert inspection["artifact_integrity"] == "verified"
    assert inspection["result_digest"]["match"] is True


def test_noninterpretable_verdict_exits_three_or_is_explicitly_softened(
    tmp_path: Path,
) -> None:
    taxonomy = _taxonomy(tmp_path, {"consumer": _consumer_model()})
    base = [
        "dfba-community",
        "--taxonomy", str(taxonomy),
        "--t-end", "0.1",
        "--initial", "EX_xfeed_m=0",
        "--initial-biomass", "consumer=0.01",
        "--member-vmax", "consumer:EX_xfeed_m=10",
        "--close-untracked-uptake",
    ]
    failed_out = tmp_path / "failed"
    softened_out = tmp_path / "softened"

    assert main([*base, "--out", str(failed_out)]) == 3
    assert main([*base, "--allow-failed-run", "--out", str(softened_out)]) == 0

    for out in (failed_out, softened_out):
        summary = json.loads((out / "community_dfba_summary.json").read_text())
        manifest = json.loads((out / "manifest.json").read_text())
        assert summary["status"] == "stalled"
        assert summary["acceptance"]["interpretable"] is False
        assert summary["acceptance"]["not_interpretable_because"]
        assert manifest["status"] == "failed"


def test_explicit_solver_failure_writes_diagnostic_and_exits_three(
    tmp_path: Path,
) -> None:
    taxonomy = _taxonomy(tmp_path, {"broken": _broken_model()})
    out = tmp_path / "solver_failed"

    assert main([
        "dfba-community",
        "--taxonomy", str(taxonomy),
        "--t-end", "0.1",
        "--initial", "EX_s_m=1",
        "--initial-biomass", "broken=0.01",
        "--close-untracked-uptake",
        "--out", str(out),
    ]) == 3

    summary = json.loads((out / "community_dfba_summary.json").read_text())
    events = json.loads((out / "community_dfba_events.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    assert summary["status"] == "solver_failed"
    assert summary["diagnostic"]
    assert summary["acceptance"]["interpretable"] is False
    assert any(event["kind"] == "solver_failure" for event in events["events"])
    assert manifest["status"] == "failed"
    assert manifest["diagnostic"] == summary["diagnostic"]


def test_duplicate_repeated_mapping_is_an_input_error(tmp_path: Path) -> None:
    taxonomy = _taxonomy(tmp_path, {"consumer": _consumer_model()})

    assert main([
        "dfba-community",
        "--taxonomy", str(taxonomy),
        "--t-end", "0.1",
        "--initial", "EX_xfeed_m=0",
        "--initial", "EX_xfeed_m=1",
        "--initial-biomass", "consumer=0.01",
        "--out", str(tmp_path / "not_written"),
    ]) == 2
    assert not (tmp_path / "not_written").exists()
