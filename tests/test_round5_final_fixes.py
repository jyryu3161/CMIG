"""Round-5 final gate — four live instances of the fabricated-default / dropped-signal class.

The class this round exists to eliminate: *a failed computation must never be replaced by a
plausible default, and a figure that cannot be drawn honestly must be annotated rather than drawn
clean*. Four sites survived the round's own sweep, all pre-existing on `main` and all reproduced
end-to-end by the final reviewer:

1. `strain-growth`'s figure applied ``or 0.0`` to a member whose alone-solve raised, so a
   never-measured strain was drawn as a **measured zero bar** beside a real community bar — which
   reads as obligate syntrophy. Every other layer of the same command (CSV blank, JSON null,
   degraded summary tier, run-level warning, GUI em dash) was already honest; only the `.svg` and
   `.tiff` that go in the manuscript fabricated. The corrected pattern already existed ~80
   lines below it, in `_abundance_impact_plot_series`.
2. `sweep` hard-coded ``"status": "ok"`` in its summary and derived the manifest status as
   ``"ok" if rows else "failed"`` — but `rows` *includes* failures, so the `failed` branch was
   reachable only for an empty grid. An all-failed grid was certified ok by the summary, the
   manifest, `inspect-run` **and** the exit code, with no warning printed.
3. `host-search-bigg` hard-coded ``"evaluation_status": "ok"`` in its success branch, while
   `core/host_coupling` *returns* (rather than raises) ``HostSolveResult(False, status, 0.0, …)``
   for a non-optimal host LP. A score of 0.0 was therefore ranked and painted in the "evaluated ok"
   colour while the same row's `warnings` cell said "the reported host objective is not a result".
4. `inspect-run` printed "certifies the ARTIFACT BYTES — verified" although **no workflow declared
   its figures** in the manifest `artifacts` list, so a figure overwritten with
   ``<svg>FABRICATED FIGURE</svg>`` still passed; and when a *declared* artifact was tampered the
   mismatch was reported loudly on stderr in text mode only, while `status` stayed `ok`, the exit
   code stayed 0 and `--format json` said nothing.

Plus the reviewer's item 5: `_compact_manifest` whitelisted 12 keys and dropped `diagnostic`,
`warnings` and `provenance`, so the `medium_policy` marker created this round — the marker whose
whole purpose is to let a reader tell which medium semantics produced a number — never reached the
tool's own inspection command.

Every test below was captured failing before the corresponding fix and re-checked by reverting it.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from cmig.cli import main as cli

# ─────────────────────────────────────────────────────────────────────────────────
# 1. strain-growth: a never-measured leg is not a zero bar
# ─────────────────────────────────────────────────────────────────────────────────

def _sg_row(
    member: str,
    *,
    single: float | None,
    single_status: str,
    community: float | None,
    community_status: str = "optimal",
) -> dict[str, object]:
    """The exact row shape `_cmd_strain_growth` builds (see main.py member append)."""
    return {
        "member": member,
        "single_growth": single,
        "single_status": single_status,
        "community_member_growth": community,
        "community_status": community_status,
        "n_objective_terms": 1,
    }


SG_ROWS = [
    # alone-solve raised: single_growth is None and single_status is "failed"
    _sg_row("strainA", single=None, single_status="failed", community=0.5),
    _sg_row("strainB", single=0.8, single_status="optimal", community=0.6),
    # a genuinely measured zero — the value the fabricated one was indistinguishable from
    _sg_row("strainC", single=0.0, single_status="optimal", community=0.0),
]


def test_an_unmeasured_strain_growth_leg_is_nan_not_a_fabricated_zero():
    """`_optional_float(None) or 0.0` -> 0.0 was the whole defect. NaN draws no bar."""
    single, community, unmeasured = cli._strain_growth_plot_series(SG_ROWS)
    assert math.isnan(single[0]), "a member whose alone-solve raised must not get a bar height"
    assert single[1] == pytest.approx(0.8)
    assert community[0] == pytest.approx(0.5), "the community leg DID solve and stays plotted"
    # The discrimination that matters: a real zero is still a real zero.
    assert single[2] == pytest.approx(0.0)
    assert community[2] == pytest.approx(0.0)
    assert unmeasured == ["strainA"]


def test_a_nonfinite_growth_is_also_treated_as_unmeasured():
    rows = [_sg_row("strainD", single=float("nan"), single_status="optimal", community=0.4)]
    single, _community, unmeasured = cli._strain_growth_plot_series(rows)
    assert math.isnan(single[0])
    assert unmeasured == ["strainD"]


def test_a_failed_community_leg_is_also_not_drawn_as_zero():
    rows = [_sg_row("strainE", single=0.3, single_status="optimal",
                    community=None, community_status="infeasible")]
    single, community, unmeasured = cli._strain_growth_plot_series(rows)
    assert single[0] == pytest.approx(0.3)
    assert math.isnan(community[0])
    assert unmeasured == ["strainE"]


def test_the_strain_growth_figure_says_a_member_was_not_evaluable(tmp_path):
    """A reader who only ever sees the TIFF has no other way to learn a leg was never solved."""
    pytest.importorskip("matplotlib")
    cli._write_strain_growth_figures(SG_ROWS, tmp_path)
    svg = (tmp_path / "strain_growth_plot.svg").read_text()
    assert "not evaluable" in svg, "the omitted bar must be marked on the figure itself"
    assert "1 of 3 members not evaluable" in svg, "the count belongs in the title"


def test_the_strain_growth_figure_makes_no_such_claim_when_everything_solved(tmp_path):
    """Otherwise the annotation would be noise and readers would learn to ignore it."""
    pytest.importorskip("matplotlib")
    ok_rows = [row for row in SG_ROWS if row["single_status"] == "optimal"]
    cli._write_strain_growth_figures(ok_rows, tmp_path)
    svg = (tmp_path / "strain_growth_plot.svg").read_text()
    assert "not evaluable" not in svg


def test_no_cli_expression_reintroduces_the_or_zero_default():
    """``<maybe None> or 0.0`` is this defect class's signature — keep it out of the CLI module.

    Parsed rather than grepped, so the prose explaining the defect does not trip it, and so an
    ``or 0`` / ``or 0.0`` written any other way still does.
    """
    import ast

    tree = ast.parse(Path(cli.__file__).read_text())
    offending = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)
        and any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, (int, float))
            and not isinstance(value.value, bool)
            and value.value == 0
            for value in node.values[1:]
        )
    ]
    assert offending == [], f"a fabricated-zero default is back at cli/main.py:{offending}"


# ─────────────────────────────────────────────────────────────────────────────────
# 2. sweep: an all-failed grid is not "ok"
# ─────────────────────────────────────────────────────────────────────────────────

def _sweep_rows(*statuses: str):
    from cmig.core.sweep import SweepRow

    return [
        SweepRow(
            condition_id=f"cond-{index:04d}",
            axis_values={"tradeoff_f": 0.5},
            metric="growth",
            value=None if status != "ok" else 1.0,
            run_hash="" if status != "ok" else "a" * 64,
            status=status,
            diagnostic=None if status == "ok" else '{"code": "solver_error"}',
            cache_hit=False,
        )
        for index, status in enumerate(statuses)
    ]


def test_sweep_status_is_derived_from_the_per_condition_statuses():
    assert cli._sweep_run_status(_sweep_rows("ok", "ok")) == "ok"
    assert cli._sweep_run_status(_sweep_rows("ok", "failed")) == "degraded"
    assert cli._sweep_run_status(_sweep_rows("failed", "failed")) == "failed"
    assert cli._sweep_run_status([]) == "failed"


def test_sweep_names_the_failed_conditions_in_its_warnings():
    warnings = cli._sweep_warnings(_sweep_rows("ok", "failed", "failed"))
    assert warnings, "a partly failed grid cannot report an empty warning list"
    joined = " ".join(warnings)
    assert "cond-0001" in joined and "cond-0002" in joined
    assert cli._sweep_warnings(_sweep_rows("ok", "ok")) == []


@pytest.fixture
def sweep_fixture(tmp_path):
    """Real synthetic-pair GEMs on disk, a valid medium and a medium naming a bogus exchange."""
    pytest.importorskip("micom")
    from cmig.synthetic_pair import build_pair_taxonomy

    taxonomy = build_pair_taxonomy(tmp_path / "models")
    tax_csv = tmp_path / "tax.csv"
    taxonomy.to_csv(tax_csv, index=False)
    good = tmp_path / "medium_good.csv"
    good.write_text("exchange_id,uptake_limit\nEX_glc__D_m,20.0\n")
    bogus = tmp_path / "medium_bogus.csv"
    bogus.write_text("exchange_id,uptake_limit\nEX_totallybogus_m,10.0\nEX_glc__D_m,20.0\n")
    return SimpleNamespace(tax_csv=tax_csv, good=good, bogus=bogus, root=tmp_path)


def _run_sweep(sweep_fixture, *mediums: Path, out_name: str) -> tuple[int, dict, dict]:
    out = sweep_fixture.root / out_name
    argv = [
        "sweep", "--taxonomy", str(sweep_fixture.tax_csv), "--assume-bigg-namespace",
        "--tradeoff-fs", "0.5", "--out", str(out),
    ]
    if mediums:
        argv += ["--mediums", ",".join(str(path) for path in mediums)]
    rc = cli.main(argv)
    return (
        rc,
        json.loads((out / "sweep_summary.json").read_text()),
        json.loads((out / "manifest.json").read_text()),
    )


def test_an_all_failed_sweep_is_reported_failed_everywhere(sweep_fixture):
    """The reviewer's RV-1, reached by a plain medium file and no unusual flags."""
    import pyarrow.parquet as pq

    rc, summary, manifest = _run_sweep(sweep_fixture, sweep_fixture.bogus, out_name="all_failed")
    parquet = pq.read_table(sweep_fixture.root / "all_failed" / "sweep.parquet").to_pydict()
    assert set(parquet["status"]) == {"failed"}, "the data layer was always honest"

    assert summary["status"] == "failed"
    assert summary["n_failed"] == summary["n_runs"] and summary["n_ok"] == 0
    assert summary["warnings"], "no presentation layer may be silent about an all-failed grid"
    assert manifest["status"] == "failed"
    assert manifest["warnings"], "the manifest's own warning list must carry it too"
    assert rc == cli.EXIT_ANALYSIS_FAILED, "a pipeline gating on $? must not accept this run"

    inspected = cli._inspect_run_dir(sweep_fixture.root / "all_failed")
    assert inspected["status"] == "failed"


def test_a_partly_failed_sweep_is_degraded_and_still_exits_zero(sweep_fixture):
    rc, summary, manifest = _run_sweep(
        sweep_fixture, sweep_fixture.good, sweep_fixture.bogus, out_name="partial",
    )
    assert summary["status"] == "degraded"
    assert summary["n_failed"] == 1 and summary["n_ok"] == 1
    assert manifest["status"] == "degraded"
    assert rc == 0, "a degraded run is still a run; only `failed` is a non-zero exit"


def test_a_fully_successful_sweep_is_still_ok(sweep_fixture):
    """Otherwise the new status derivation would be a false alarm generator."""
    rc, summary, manifest = _run_sweep(sweep_fixture, sweep_fixture.good, out_name="all_ok")
    assert summary["status"] == "ok"
    assert summary["n_failed"] == 0
    assert summary["warnings"] == []
    assert manifest["status"] == "ok"
    assert rc == 0


def test_an_all_failed_sweep_can_be_waived_explicitly(sweep_fixture):
    out = sweep_fixture.root / "waived"
    rc = cli.main([
        "sweep", "--taxonomy", str(sweep_fixture.tax_csv), "--assume-bigg-namespace",
        "--tradeoff-fs", "0.5", "--mediums", str(sweep_fixture.bogus),
        "--allow-failed-run", "--out", str(out),
    ])
    assert rc == 0
    assert json.loads((out / "sweep_summary.json").read_text())["status"] == "failed", \
        "the waiver changes the exit code, never the recorded status"


# ─────────────────────────────────────────────────────────────────────────────────
# 3. host-search-bigg: a non-optimal host LP is not an ok result
#    4. inspect-run: the manifest declares the figures it advertises
# ─────────────────────────────────────────────────────────────────────────────────

def _bigg_result(*, host_status: str, community_status: str = "optimal", biomass: float = 0.0):
    from cmig.core.host import BiggHostMicrobeResult, HostSolveResult

    host = HostSolveResult(
        host_status == "optimal", host_status, biomass, [], {},
        None if host_status == "optimal" else '{"code": "infeasible"}',
    )
    return BiggHostMicrobeResult(
        community_status=community_status,
        community_growth=0.9,
        microbial_secretion={},
        member_secretion={},
        matched_exchanges={},
        unmatched_metabolites=[],
        host_result=host,
        impact=SimpleNamespace(microbe_to_host={"ac": 1.2} if host_status == "optimal" else {}),
        warnings=[] if host_status == "optimal" else [
            f"host solve was not optimal (status={host_status}); the reported host objective "
            "is not a result"
        ],
    )


@pytest.fixture
def host_search(tmp_path, monkeypatch):
    """Drive the real `_cmd_host_search_bigg` on real SBML files with a stubbed coupling solve.

    The stub is the point: `solve_bigg_host` RETURNS for a non-optimal host LP, so the defect lives
    on the success path and cannot be reached by making the solve raise.
    """
    pytest.importorskip("micom")
    from cmig.core import host_coupling
    from cmig.synthetic_pair import build_pair_taxonomy

    taxonomy = build_pair_taxonomy(tmp_path / "models")
    tax_csv = tmp_path / "tax.csv"
    taxonomy.to_csv(tax_csv, index=False)

    state = SimpleNamespace(host_status="infeasible")

    def fake_run(sub, host_model, **_kw):
        return _bigg_result(host_status=state.host_status, biomass=0.0)

    monkeypatch.setattr(host_coupling, "run_bigg_host_microbe", fake_run)

    def run(out_name: str) -> tuple[int, dict, dict]:
        out = tmp_path / out_name
        rc = cli._cmd_host_search_bigg(argparse.Namespace(
            host=str(taxonomy["file"][0]), taxonomy=str(tax_csv), model_dir=None,
            recursive=False, solver="gurobi", min_size=2, max_size=2, top_k=10,
            target="ac", metric="objective_value", host_weight=None, target_weight=None,
            host_reference=None, target_reference=None, tradeoff_f=0.5,
            microbial_biomass_gdw=1.0, host_biomass_gdw=1.0,
            biomass_basis_kind="validation", biomass_basis_source="synthetic fixture",
            microbe_medium=None, host_medium=None, exchange_suffix="_e", interface_map=None,
            host_objective=None, exclude_metabolites=None, include_currency_metabolites=False,
            keep_host_uptake=False, accept_unreviewed_map=False, allow_failed_run=False,
            out=str(out),
        ))
        return (
            rc,
            json.loads((out / "host_search_summary.json").read_text()),
            json.loads((out / "manifest.json").read_text()),
        )

    return SimpleNamespace(run=run, state=state, root=tmp_path)


def test_a_non_optimal_host_lp_is_not_ranked_as_an_ok_candidate(host_search):
    """The reviewer's RV-3: `evaluation_status` was a literal, so score 0.0 got rank 1."""
    rc, summary, manifest = host_search.run("infeasible_host")
    assert summary["top_ranked"] == [], "a host LP that was never optimal has no score to rank"
    assert [row["members"] for row in summary["unevaluated"]] == [["consumer", "producer"]]
    assert summary["n_candidates_evaluated"] == 0
    assert summary["n_candidates_failed"] == 1
    assert summary["status"] == "failed"
    assert summary["warnings"], "the run-level warning list cannot be empty here"
    assert manifest["status"] == "failed"
    assert rc == cli.EXIT_ANALYSIS_FAILED


def test_a_non_optimal_host_lp_publishes_no_number_at_all(host_search):
    """0.0 from `HostSolveResult(False, status, 0.0, …)` is not a measurement of anything."""
    import csv as csv_mod

    host_search.run("infeasible_host")
    rows = list(csv_mod.DictReader(
        (host_search.root / "infeasible_host" / "host_search_rankings.csv")
        .read_text().splitlines()
    ))
    assert rows == [], "an unevaluable candidate does not belong in the ranking CSV"
    unevaluated = list(csv_mod.DictReader(
        (host_search.root / "infeasible_host" / "host_search_unevaluated.csv")
        .read_text().splitlines()
    ))
    assert unevaluated[0]["members"] == "consumer+producer"
    assert "infeasible" in unevaluated[0]["diagnostic"]


def test_the_host_search_figure_paints_no_failed_candidate_in_the_ok_colour(host_search):
    pytest.importorskip("matplotlib")
    host_search.run("infeasible_host")
    svg = (host_search.root / "infeasible_host" / "host_search_plot.svg").read_text()
    assert "#3182bd" not in svg, "the 'evaluated ok' blue must not appear when nothing evaluated"
    # With the failure correctly excluded, an empty bar set is all the figure alone would show.
    assert "1 of 1 candidates not evaluable" in svg


def test_the_host_search_figure_makes_no_such_claim_when_everything_evaluated(host_search):
    pytest.importorskip("matplotlib")
    host_search.state.host_status = "optimal"
    host_search.run("all_ok")
    svg = (host_search.root / "all_ok" / "host_search_plot.svg").read_text()
    assert "not evaluable" not in svg


def test_an_optimal_host_lp_is_still_ranked_ok(host_search):
    """The fix must not turn every candidate into a failure."""
    host_search.state.host_status = "optimal"
    rc, summary, manifest = host_search.run("optimal_host")
    assert [row["evaluation_status"] for row in summary["top_ranked"]] == ["ok"]
    assert summary["status"] == "ok"
    assert manifest["status"] == "ok"
    assert rc == 0


# ── 4a: the manifest declares the figures, so "certifies the ARTIFACT BYTES" is true ──

def test_the_workflow_manifest_declares_the_figures_the_summary_advertises(host_search):
    host_search.state.host_status = "optimal"
    _rc, summary, manifest = host_search.run("declared")
    assert "host_search_plot.svg" in manifest["artifacts"]
    assert "host_search_plot.tiff" in manifest["artifacts"]
    # Two lists in one run directory that disagree is the defect; they are now one list.
    assert sorted(manifest["artifacts"]) == sorted(summary["artifacts"])
    assert set(manifest["result_digest"]["artifacts"]) == set(manifest["artifacts"])
    assert manifest["result_digest"]["missing_artifacts"] == []


def test_a_fabricated_figure_no_longer_passes_result_digest(host_search):
    """The reviewer's RV-4, verbatim: an overwritten publication figure must be caught."""
    host_search.state.host_status = "optimal"
    host_search.run("tampered_figure")
    run_dir = host_search.root / "tampered_figure"
    (run_dir / "host_search_plot.svg").write_text("<svg>FABRICATED FIGURE</svg>")
    inspected = cli._inspect_run_dir(run_dir)
    assert inspected["result_digest"]["match"] is False
    assert "host_search_plot.svg" in inspected["result_digest"]["changed_artifacts"]


# ── 4b: a detected tamper reaches `status`, the exit code and the JSON payload ──

def _host_map_run(tmp_path):
    """A minimal run directory with a real workflow manifest over declared artifacts."""
    from cmig.core.workflow_envelope_golden import golden_components
    from cmig.core.workflow_manifest import write_workflow_manifest

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "host_exchange_map.csv").write_text("metabolite,host_exchange\nac_e,EX_ac_e\n")
    (tmp_path / "host_map_summary.json").write_text(json.dumps({"n_exact": 1}))
    write_workflow_manifest(
        tmp_path, "host_map", golden_components("host_map"),
        status="ok", artifacts=["host_exchange_map.csv", "host_map_summary.json"],
    )
    return tmp_path


def test_a_tampered_declared_artifact_makes_inspect_run_report_a_failed_run(tmp_path):
    run_dir = _host_map_run(tmp_path / "run")
    (run_dir / "host_exchange_map.csv").write_text("metabolite,host_exchange\n")
    inspected = cli._inspect_run_dir(run_dir)
    assert inspected["artifact_integrity"] == "mismatch"
    assert inspected["status"] == "failed", "the headline verdict must participate"
    assert inspected["status_source"] == "result_digest_mismatch"
    # The manifest's own recorded status stays visible rather than being overwritten.
    assert inspected["manifest"]["status"] == "ok"


def test_a_tampered_declared_artifact_makes_inspect_run_exit_non_zero(tmp_path, capsys):
    run_dir = _host_map_run(tmp_path / "run")
    (run_dir / "host_exchange_map.csv").write_text("metabolite,host_exchange\n")
    assert cli._cmd_inspect_run(
        argparse.Namespace(run_dir=str(run_dir), format="text")
    ) == cli.EXIT_ANALYSIS_FAILED
    assert "result_digest: MISMATCH" in capsys.readouterr().err


def test_the_json_format_is_not_silent_about_a_tampered_artifact(tmp_path, capsys):
    run_dir = _host_map_run(tmp_path / "run")
    (run_dir / "host_exchange_map.csv").write_text("metabolite,host_exchange\n")
    rc = cli._cmd_inspect_run(argparse.Namespace(run_dir=str(run_dir), format="json"))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["artifact_integrity"] == "mismatch"
    assert payload["status"] == "failed"
    assert payload["result_digest"]["match"] is False
    assert "result_digest: MISMATCH" in captured.err, "json mode was completely silent before"
    assert rc == cli.EXIT_ANALYSIS_FAILED


def test_an_untampered_run_still_reports_its_own_status_and_exits_zero(tmp_path, capsys):
    run_dir = _host_map_run(tmp_path / "run")
    rc = cli._cmd_inspect_run(argparse.Namespace(run_dir=str(run_dir), format="json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact_integrity"] == "verified"
    assert payload["status"] == "ok" and payload["status_source"] == "manifest"
    assert rc == 0


def test_a_manifest_predating_result_digests_is_not_claimed_verified(tmp_path, capsys):
    run_dir = _host_map_run(tmp_path / "run")
    payload = json.loads((run_dir / "manifest.json").read_text())
    del payload["result_digest"]
    (run_dir / "manifest.json").write_text(json.dumps(payload, sort_keys=True))
    rc = cli._cmd_inspect_run(argparse.Namespace(run_dir=str(run_dir), format="json"))
    assert json.loads(capsys.readouterr().out)["artifact_integrity"] == "not_recorded"
    assert rc == 0, "absence of the field is not evidence of tampering"


# ─────────────────────────────────────────────────────────────────────────────────
# 5. inspect-run surfaces the signals the manifest already records
# ─────────────────────────────────────────────────────────────────────────────────

def test_inspect_run_surfaces_the_medium_policy_marker_of_a_workflow_run(tmp_path):
    from cmig.core.medium_spec import MEDIUM_POLICY

    run_dir = _host_map_run(tmp_path / "run")
    compact = cli._inspect_run_dir(run_dir)["manifest"]
    assert compact["medium_policy"] == MEDIUM_POLICY, \
        "the marker exists so a reader can tell which medium semantics produced a number"


def test_inspect_run_surfaces_warnings_diagnostic_and_summary_values(tmp_path):
    from cmig.core.workflow_envelope_golden import golden_components
    from cmig.core.workflow_manifest import write_workflow_manifest

    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    write_workflow_manifest(
        run_dir, "host_map", golden_components("host_map"),
        status="degraded", artifacts=[],
        diagnostic="medium_unapplied",
        warnings=["EX_totallybogus_m was requested but never applied"],
        summary={"n_exact": 7},
    )
    compact = cli._inspect_run_dir(run_dir)["manifest"]
    assert compact["diagnostic"] == "medium_unapplied"
    assert compact["warnings"] == ["EX_totallybogus_m was requested but never applied"]
    assert compact["summary"] == {"n_exact": 7}


def test_inspect_run_surfaces_the_solve_manifests_provenance(tmp_path):
    """The `--allow-unknown-medium` dropped-nutrient diagnostic lives here (reviewer's RV-5)."""
    from cmig.core.medium_spec import MEDIUM_POLICY

    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "manifest_schema_version": "2.0",
        "run_hash": "c" * 64,
        "artifacts": [],
        "diagnostic": {"detail": {"warning": {
            "code": "medium_unapplied",
            "detail": {"exchange_ids": ["EX_totallybogus_m"]},
        }}},
        "provenance": {"medium_policy": MEDIUM_POLICY},
    }))
    compact = cli._inspect_run_dir(run_dir)["manifest"]
    assert compact["provenance"]["medium_policy"] == MEDIUM_POLICY
    assert compact["diagnostic"]["detail"]["warning"]["code"] == "medium_unapplied"


def test_a_caller_cannot_overwrite_the_writer_stamped_medium_policy(tmp_path):
    """`{"medium_policy": …, **provenance}` let a caller win against the adjacent comment."""
    from cmig.core.medium_spec import MEDIUM_POLICY
    from cmig.io.solve_output import solve_provenance

    assert solve_provenance({"medium_policy": "a_lie"})["medium_policy"] == MEDIUM_POLICY
    assert solve_provenance({"solver_build": "x"})["solver_build"] == "x"
