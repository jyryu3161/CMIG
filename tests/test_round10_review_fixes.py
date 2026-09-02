"""Round-10 code-review fixes — regression pins.

Each test names the defect it guards against; the fix lives in the module under test.
License-free tests come first, solver-backed ones are skipped without micom/cobra/Gurobi.
"""

from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from cmig.io import atomic as atomic_mod
from cmig.io.atomic import atomic_write_bytes, atomic_write_path, atomic_write_text

# ── io/atomic: published artifacts honour the umask, not mkstemp's 0600 ─────────────────────


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
@pytest.mark.parametrize("writer", ["text", "bytes", "path"])
def test_atomic_writers_publish_with_the_process_file_mode(tmp_path: Path, writer: str) -> None:
    target = tmp_path / f"artifact.{writer}"
    if writer == "text":
        atomic_write_text(target, "x\n")
    elif writer == "bytes":
        atomic_write_bytes(target, b"x\n")
    else:
        atomic_write_path(target, lambda tmp: Path(tmp).write_bytes(b"x\n"))
    expected = 0o666 & ~atomic_mod._UMASK
    assert stat.S_IMODE(target.stat().st_mode) == expected
    # and a plain write beside it has the same mode (the previous 0600 was the odd one out)
    plain = tmp_path / "plain.txt"
    plain.write_text("x\n")
    assert stat.S_IMODE(plain.stat().st_mode) == expected


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_atomic_rewrite_keeps_an_existing_files_mode(tmp_path: Path) -> None:
    target = tmp_path / "keep.json"
    target.write_text("{}\n")
    os.chmod(target, 0o600)
    atomic_write_text(target, '{"v": 2}\n')
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


# ── service/jobrunner: SystemExit from an in-process CLI is a failed job ─────────────────────


def test_jobrunner_marks_a_system_exit_as_failed() -> None:
    from cmig.service import JobRunner, JobStatus
    from cmig.service.jobrunner import JobFailed

    runner = JobRunner(max_workers=1)
    try:
        def exits(ctx: object) -> int:
            raise SystemExit(2)

        job_id = runner.submit("argparse-error", exits)
        # `result` waits and reports the failure as JobFailed — never as a SystemExit that
        # would unwind the caller, and never as a job stuck in RUNNING.
        with pytest.raises(JobFailed):
            runner.result(job_id)
        job = runner.poll(job_id)
        assert job.status is JobStatus.FAILED
        assert job.error is not None and "SystemExit" in job.error
    finally:
        runner.shutdown()


# ── core/host_impact: raw vs normalized metabolite spellings join correctly ──────────────────


def test_host_impact_joins_stereo_metabolites_across_spellings() -> None:
    from cmig.core.host_impact import host_impact

    host = SimpleNamespace(
        viable=True, biomass=1.0,
        lumen_uptake={"lac__d": 5.0},
        lumen_uptake_ranges={"lac__d": (5.0, 5.0)},
    )
    impact = host_impact({"lac__D": 5.0, "but": 1.0}, host)
    assert impact.microbe_to_host == {"lac__D": 5.0}
    assert impact.unused_secretion == {"but": 1.0}
    assert impact.microbe_to_host_ranges["lac__D"] == (5.0, 5.0)


# ── core/sweep: a non-finite metric is a failed condition ────────────────────────────────────


def test_run_sweep_records_non_finite_values_as_failed() -> None:
    from cmig.core.sweep import RunHashCache, SweepAxis, run_sweep

    axes = [SweepAxis("tradeoff_f", [0.3, 0.5, 0.7])]
    values = iter([0.9, float("nan"), float("inf")])
    rows = run_sweep(
        axes,
        run_hash_fn=lambda cond: f"h::{cond.axis_values}",
        solve_fn=lambda cond: next(values),
        metric="growth",
        cache=RunHashCache(),
    )
    assert [row.status for row in rows] == ["ok", "failed", "failed"]
    assert rows[1].value is None and rows[2].value is None
    assert "non-finite" in json.dumps(rows[1].diagnostic)


# ── core/search_product: an all-non-optimal epsilon sweep is disclosed, not dropped ─────────


def test_pareto_sweep_with_no_optimal_level_returns_a_failed_eval(monkeypatch) -> None:
    pd = pytest.importorskip("pandas")
    from cmig.core import search_product
    from cmig.core.search import TargetSpec

    monkeypatch.setattr(
        "cmig.core.search.epsilon_constrained_solve",
        lambda *a, **k: SimpleNamespace(status="solver_no_solution"),
    )
    monkeypatch.setattr(search_product, "_apply_search_medium", lambda *a, **k: None)
    engine = SimpleNamespace(build_community=lambda *a, **k: object())
    taxonomy = pd.DataFrame({"id": ["a", "b"], "file": ["a.xml", "b.xml"]})
    evals = search_product._pareto_points_for_members(
        engine, taxonomy, ("a", "b"), [TargetSpec("but")],
        capability={"but": 1.0}, growth_fraction=0.5, solver="gurobi",
        medium_spec=None, strict_medium=True,
    )
    assert len(evals) == 1
    assert evals[0].status == "failed"
    assert "epsilon" in str(evals[0])


# ── io/model_import: compound suffixes in the fallback model id ─────────────────────────────


@pytest.mark.parametrize(
    "name, expected",
    [("iML1515.xml.gz", "iML1515"), ("model.sbml", "model"), ("m.json", "m"), ("m.mat", "m")],
)
def test_model_id_fallback_strips_compound_suffixes(name: str, expected: str) -> None:
    from cmig.io.model_import import _model_id_from_path

    assert _model_id_from_path(Path(name)) == expected


# ── cli: render-figure --panel honours --width/--height/--dpi without --title ────────────────


def test_render_figure_panel_uses_cli_geometry(tmp_path: Path, monkeypatch) -> None:
    from cmig.cli import main as cli_main

    captured: dict[str, object] = {}

    def fake_render(run_dir, panels, out, **kwargs):
        captured["panels"] = list(panels)
        return []

    monkeypatch.setattr("cmig.render.client.rscript_available", lambda: True)
    monkeypatch.setattr(cli_main, "rscript_available", lambda: True, raising=False)
    monkeypatch.setattr("cmig.render.composer.render_panels_from_run", fake_render)
    from cmig.core.tidy import empty_bundle

    run_dir = tmp_path / "run"
    empty_bundle().write(run_dir)
    rc = cli_main.main([
        "render-figure", "--run-dir", str(run_dir), "--out", str(tmp_path / "panels"),
        "--panel", "network", "--panel", "heatmap",
        "--width", "8", "--height", "8", "--dpi", "300",
    ])
    assert rc == 0, rc
    panels = captured["panels"]
    assert [p.kind for p in panels] == ["network", "heatmap"]
    assert all((p.width_in, p.height_in, p.dpi) == (8.0, 8.0, 300) for p in panels)
    assert [p.title for p in panels] == ["Network", "Heatmap"]


# ── solver-backed pins ──────────────────────────────────────────────────────────────────────


def _core_model_path() -> str:
    micom = pytest.importorskip("micom")
    return os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")


def test_single_model_pfba_and_fba_fail_the_same_way_on_an_infeasible_model() -> None:
    cobra = pytest.importorskip("cobra")
    from cmig.core.single_model import solve_single_model

    model = cobra.io.read_sbml_model(_core_model_path())
    model.reactions.get_by_id("BIOMASS_Ecoli_core_w_GAM").lower_bound = 10.0
    for method in ("FBA", "pFBA"):
        result = solve_single_model(model, method=method, solver="gurobi")
        assert result.status != "optimal", method
        assert math.isnan(result.objective), (method, result.objective)
        assert result.diagnostic


def test_dfba_warns_when_a_tracked_substrate_can_never_be_consumed() -> None:
    cobra = pytest.importorskip("cobra")
    from cmig.core.dfba import DfbaConfig, simulate_dfba

    model = cobra.io.read_sbml_model(_core_model_path())
    assert model.reactions.get_by_id("EX_ac_e").lower_bound == 0.0  # secretion-only
    result = simulate_dfba(
        model,
        DfbaConfig(t_end=0.2, dt=0.1, initial_concentrations={"EX_glc__D_e": 10.0, "EX_ac_e": 5.0}),
        solver="gurobi",
    )
    assert any("vmax == 0" in w and "EX_ac_e" in w for w in result.warnings), result.warnings
    # tracking a product from zero is the normal way to record its production: no warning
    quiet = simulate_dfba(
        model,
        DfbaConfig(t_end=0.2, dt=0.1, initial_concentrations={"EX_glc__D_e": 10.0, "EX_ac_e": 0.0}),
        solver="gurobi",
    )
    assert not any("vmax == 0" in w for w in quiet.warnings)


def test_dfba_cli_manifest_counts_integration_steps(tmp_path: Path) -> None:
    pytest.importorskip("cobra")
    from cmig.cli.main import main

    out = tmp_path / "dfba"
    rc = main(["dfba", "--model", _core_model_path(), "--t-end", "0.3", "--dt", "0.1",
               "--out", str(out)])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    summary = json.loads((out / "dfba_summary.json").read_text())
    assert manifest["summary"]["n_steps"] == summary["n_timepoints"] - 1 > 0


def test_community_dfba_reads_member_flux_for_non_canonical_exchange_ids(tmp_path: Path) -> None:
    cobra = pytest.importorskip("cobra")
    pd = pytest.importorskip("pandas")
    from cobra import Metabolite, Model, Reaction

    from cmig.core.dfba_community import CommunityDfbaConfig, run_community_dfba

    def reaction(rid, stoich, lower=0.0, upper=1000.0):
        rxn = Reaction(rid)
        rxn.bounds = (lower, upper)
        rxn.add_metabolites(stoich)
        return rxn

    model = Model("producer")
    glc_e = Metabolite("glc_e", compartment="e", formula="C6H12O6")
    glc_c = Metabolite("glc_c", compartment="c", formula="C6H12O6")
    biomass = reaction("BIOMASS_P", {glc_c: -1.0})
    model.add_reactions([
        # The exchange id is NOT `EX_<met>_e`; the engine still reports it under `glucose`.
        reaction("EX_glucose_e", {glc_e: -1.0}, lower=-10.0),
        reaction("GLCtex", {glc_e: -1.0, glc_c: 1.0}),
        biomass,
    ])
    model.objective = biomass
    path = tmp_path / "producer.xml"
    cobra.io.write_sbml_model(model, path)
    taxonomy = pd.DataFrame([{"id": "producer", "file": str(path), "abundance": 1.0}])

    result = run_community_dfba(
        taxonomy,
        CommunityDfbaConfig(
            t_end=0.3, dt=0.1,
            initial_biomasses={"producer": 0.1},
            initial_concentrations={"EX_glc_m": 5.0},
            member_vmax={"producer": {"EX_glc_m": 10.0}},
            close_untracked_uptake=True,
        ),
    )
    assert result.status in {"completed", "stalled"}
    first, last = result.timecourse[0], result.timecourse[-1]
    assert last.concentrations["EX_glc_m"] < first.concentrations["EX_glc_m"]
    consumed = [
        tp.member_exchange_fluxes["producer"]["EX_glc_m"]
        for tp in result.timecourse[1:]
        if tp.member_exchange_fluxes
    ]
    assert consumed and min(consumed) < 0.0
