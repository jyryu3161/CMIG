"""Round-6 C1/C2 — `inspect-run` must not invent a verdict it did not derive.

`inspect-run` is the verification step `SKILL.md` mandates for every run, so its `status` is the
one field an automated gate reads. Two defects of the round-5 "fabricated default / dropped
signal" class lived on it:

**C1 (P0).** `_resolve_run_status` ended with `if summary: return "ok", "derived"`. Any run
directory containing *any* recognised summary was therefore certified `ok`, whether or not
anything in it said so. Measured reproduction: `cmig dfba-sensitivity --model models/iML1515.xml`
exits 3 and writes `acceptance.interpretable: false`; `cmig inspect-run` on that directory printed
`status: ok (source: derived)` and exited 0. `dfba_sensitivity.json` carries no `status`, no
`top_ranked`, no `reports` and the command writes no `manifest.json`, so every earlier branch
missed and the run's own honesty verdict was never read. The function's docstring already forbade
exactly this ("모르면 ok 라고 하지 않는다").

The same dropped signal exists one level up: `publication-benchmark`'s dFBA sub-run derives its
manifest status from `dfba_completed` and `dfba_balance_passed` only, so a grid fed by untracked
never-depleting substrates gets `status: ok` in `manifest.json` while `acceptance.interpretable`
beside it is `false`. `acceptance.interpretable` is therefore a *veto* that survives a rosier
manifest, not merely a fall-through.

**C2 (P2).** The text renderer printed `result_digest: not recorded (manifest predates result
digests)` for a brand-new `cmig solve` run. The temporal claim was false — `solve` writes a
`manifest_scope: "solve"` manifest, and only the 13 workflow kinds ever emit a result digest. The
same line was printed for a directory with no `manifest.json` at all, blaming a manifest that does
not exist.
"""

from __future__ import annotations

import argparse
import json

import pytest

from cmig.cli.main import (
    _RESULT_DIGEST_ABSENT_MESSAGES,
    _cmd_inspect_run,
    _inspect_run_dir,
    _resolve_run_status,
    _result_digest_absent_reason,
)
from cmig.core.workflow_envelope_golden import golden_components
from cmig.core.workflow_manifest import write_workflow_manifest

GATE_VOCABULARY = {"ok", "degraded", "failed"}


def _uninterpretable_sensitivity(*, interpretable: bool = False) -> dict:
    """The shape `cmig.io.dfba_output.write_dfba_sensitivity` actually writes."""
    return {
        "dfba_sensitivity_schema_version": "1.0",
        "n_runs": 2,
        "acceptance": {
            "interpretable": interpretable,
            "not_interpretable_because": (
                [] if interpretable
                else ["growth was fed by untracked, never-depleting default-medium substrates"]
            ),
            "balance_passed": True,
            "no_untracked_uptake": interpretable,
            "all_statuses_completed": True,
        },
        "rows": [{"dt": 0.1, "km": 0.01, "status": "completed"}],
        "warnings": [],
    }


# ── C1: the reported defect ────────────────────────────────────────────────────

def test_an_uninterpretable_dfba_sensitivity_run_is_not_reported_ok(tmp_path):
    """The exact reviewer reproduction: exit-3 run, `acceptance.interpretable: false`."""
    (tmp_path / "dfba_sensitivity.json").write_text(json.dumps(_uninterpretable_sensitivity()))
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == "dfba_sensitivity"
    assert payload["status"] != "ok", (
        "a run that declared itself uninterpretable and exited 3 must never be reported ok"
    )
    assert payload["status"] == "failed"
    assert "interpretable" in payload["status_source"]


def test_an_interpretable_dfba_sensitivity_run_is_still_reported_ok(tmp_path):
    """Positive control — the veto must not condemn a grid that passed its own audit."""
    (tmp_path / "dfba_sensitivity.json").write_text(
        json.dumps(_uninterpretable_sensitivity(interpretable=True))
    )
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == "ok"
    assert "interpretable" in payload["status_source"]


def test_the_interpretable_veto_survives_a_manifest_that_says_ok(tmp_path):
    """`publication-benchmark`'s dFBA sub-run: manifest `ok`, artifact `interpretable: false`.

    The bundle's per-sub-run status is derived from `dfba_completed` and `dfba_balance_passed`
    only; the untracked-uptake finding is not in it. A manifest status must not be able to bury
    the artifact's own "this is not a result" stamp.
    """
    (tmp_path / "dfba_sensitivity.json").write_text(json.dumps(_uninterpretable_sensitivity()))
    write_workflow_manifest(
        tmp_path, "dfba", golden_components("dfba"),
        status="ok", artifacts=["dfba_sensitivity.json"],
    )
    payload = _inspect_run_dir(tmp_path)
    assert payload["manifest"]["status"] == "ok", "the manifest's own claim stays readable"
    assert payload["status"] == "failed"
    assert "interpretable" in payload["status_source"]


def test_the_cli_text_output_reports_the_uninterpretable_verdict(tmp_path, capsys):
    (tmp_path / "dfba_sensitivity.json").write_text(json.dumps(_uninterpretable_sensitivity()))
    _cmd_inspect_run(argparse.Namespace(run_dir=str(tmp_path), format="text"))
    assert "status: ok" not in capsys.readouterr().out


# ── C1: the terminal fall-through, across every recognised summary shape ──────

def test_a_recognised_summary_with_no_status_signal_is_unknown_not_ok(tmp_path):
    """`stats-demo` records no run-level outcome at all. "Unknown" is the honest answer."""
    (tmp_path / "stats_summary.json").write_text(json.dumps({
        "scope": "synthetic_demo_values_not_experimental_evidence",
        "summary": [{"group": "western", "n": 4}],
        "test": {"test": "mann_whitney_u", "pvalue": 0.028},
        "fdr_qvalues": [0.028],
        "warnings": [],
    }))
    status, source = _resolve_run_status(
        json.loads((tmp_path / "stats_summary.json").read_text()), {}
    )
    assert status == "unknown", "presence of a summary is not evidence that the run succeeded"
    assert source == "no_status_signal", (
        "a reader must be able to tell 'this kind records no status' from 'nothing was here'"
    )


def test_an_unrecognisable_summary_body_is_unknown_not_ok(tmp_path):
    """Even for a kind that normally carries a status, a body without one is unknown."""
    (tmp_path / "spatial_summary.json").write_text(json.dumps({"metabolite": "ac_e"}))
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == "spatial_preview"
    assert payload["status"] == "unknown"


def test_target_keyed_rankings_are_read_rather_than_falling_through(tmp_path):
    """`search-advanced-fixture --targets a,b` keys `top_ranked` by target, not by position.

    Found by re-running the bundled fixture: the dict shape missed `isinstance(ranked, list)`, so
    an advanced multi-target search reached the fabricated `ok` — including one whose every
    candidate was infeasible.
    """
    (tmp_path / "search_advanced_summary.json").write_text(json.dumps({
        "strategy": "exhaustive",
        "targets": ["ac", "but"],
        "top_ranked": {
            "ac": [{"members": ["a", "b"], "score": 13.4, "status": "optimal"}],
            "but": [{"members": ["a", "b"], "score": None, "status": "infeasible"}],
        },
        "pareto_frontier": [],
        "warnings": [],
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == "advanced_search_fixture"
    assert payload["status"] == "degraded", "an infeasible target must not be averaged away"


def test_target_keyed_rankings_that_ranked_nothing_are_failed(tmp_path):
    (tmp_path / "search_advanced_summary.json").write_text(json.dumps({
        "strategy": "exhaustive",
        "targets": ["ac"],
        "top_ranked": {"ac": []},
        "warnings": [],
    }))
    assert _inspect_run_dir(tmp_path)["status"] == "failed"


def test_an_empty_run_dir_stays_unknown_with_the_unknown_source(tmp_path):
    """The pre-existing honest case must keep its own source, distinct from `no_status_signal`."""
    payload = _inspect_run_dir(tmp_path)
    assert (payload["status"], payload["status_source"]) == ("unknown", "unknown")


# ── C1: kinds that reached the fall-through and DO have a real signal ─────────

@pytest.mark.parametrize(
    ("filename", "solve_status", "expected"),
    [
        ("host_generic_summary.json", "optimal", "ok"),
        ("host_generic_summary.json", "infeasible", "failed"),
        ("host_benchmark.json", "optimal", "ok"),
        ("host_benchmark.json", "infeasible", "failed"),
    ],
)
def test_a_nested_solve_status_is_derived_rather_than_ignored(
    tmp_path, filename, solve_status, expected
):
    """`host-generic` / `host-benchmark` put the solve outcome under `solve.status`.

    Before the fix an infeasible host solve was reported `ok`, because the top level of these two
    summaries has no `status` key and neither command writes a manifest.
    """
    (tmp_path / filename).write_text(json.dumps({
        "model": {"id": "iHN637"},
        "solve": {"status": solve_status, "viable": solve_status == "optimal",
                  "objective_value": 0.22, "diagnostic": None},
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == expected
    assert payload["status_source"] == "solve.status"


def test_stats_sweep_with_withheld_inference_is_not_reported_ok(tmp_path):
    """Round 5 made `stats-sweep` withhold p-values without independent replicates.

    That withholding is recorded in `inference.status`. Reporting the run `ok` hides that the
    summary contains no inferential result at all.
    """
    (tmp_path / "stats_sweep_summary.json").write_text(json.dumps({
        "metric": "growth",
        "group_axis": "solver",
        "groups": {"gurobi": 2},
        "summary": [{"group": "gurobi", "n": 2}],
        "test": None,
        "inference": {"status": "not_run_no_independent_replicates",
                      "replicate_column": None, "confirmed_independent": False},
        "warnings": [],
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == "degraded"
    assert payload["status_source"] == "inference.status"


def test_stats_sweep_with_completed_inference_is_ok(tmp_path):
    (tmp_path / "stats_sweep_summary.json").write_text(json.dumps({
        "metric": "growth",
        "groups": {"a": 3, "b": 3},
        "test": {"pvalue": 0.03},
        "inference": {"status": "completed", "confirmed_independent": True},
        "warnings": [],
    }))
    payload = _inspect_run_dir(tmp_path)
    assert (payload["status"], payload["status_source"]) == ("ok", "inference.status")


def test_a_model_review_that_blocks_the_namespace_gate_is_not_reported_ok(tmp_path):
    """`model-review`'s verdict IS `namespace.blocked`; ignoring it leaves nothing to derive."""
    (tmp_path / "model_review.json").write_text(json.dumps({
        "inferred_origin": "user_provided_gem",
        "model": {"model_id": "iML1515", "objective_warning": None},
        "namespace": {"blocked": True, "coverage_pct": 0.0, "decisions": []},
        "warnings": [],
        "next_actions": [],
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == "degraded"
    assert payload["status_source"] == "namespace.blocked"


def test_a_model_review_that_passes_the_gate_is_ok(tmp_path):
    (tmp_path / "model_review.json").write_text(json.dumps({
        "model": {"model_id": "m", "objective_warning": None},
        "namespace": {"blocked": False, "coverage_pct": 100.0, "decisions": []},
        "warnings": [],
    }))
    assert _inspect_run_dir(tmp_path)["status"] == "ok"


def test_a_host_map_run_that_matched_nothing_is_not_reported_ok(tmp_path):
    """A `host-map` directory whose manifest could not be written must not certify itself."""
    (tmp_path / "host_map_summary.json").write_text(json.dumps({
        "kind": "host_exchange_map",
        "n_microbial_secretions": 0,
        "n_exact": 0,
        "n_unmatched": 0,
        "entries": [],
        "warnings": [],
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == "failed"
    assert payload["status_source"] == "host_map_counts"


def test_a_host_map_run_with_no_exact_matches_is_degraded(tmp_path):
    (tmp_path / "host_map_summary.json").write_text(json.dumps({
        "kind": "host_exchange_map",
        "n_microbial_secretions": 5,
        "n_exact": 0,
        "entries": [],
        "warnings": [],
    }))
    assert _inspect_run_dir(tmp_path)["status"] == "degraded"


def test_a_publication_benchmark_summary_reports_its_own_failed_checks(tmp_path):
    """`publication_benchmark.json` records `overall_passed`; the fall-through ignored it."""
    (tmp_path / "publication_benchmark.json").write_text(json.dumps({
        "publication_benchmark_schema_version": "1.1",
        "checks": {"search_has_optimal_candidate": False},
        "computational_checks_passed": False,
        "publication_ready": False,
        "overall_passed": False,
        "warnings": [],
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["status"] == "failed"
    assert payload["status_source"] == "computational_checks_passed"


def test_a_publication_benchmark_that_only_missed_a_provenance_check_is_degraded(tmp_path):
    (tmp_path / "publication_benchmark.json").write_text(json.dumps({
        "checks": {"host_coupling_has_study_biomass_basis": False},
        "computational_checks_passed": True,
        "publication_ready": False,
        "overall_passed": False,
        "warnings": [],
    }))
    assert _inspect_run_dir(tmp_path)["status"] == "degraded"


def test_every_derived_status_stays_inside_the_gate_vocabulary_or_says_unknown(tmp_path):
    """No derivation may leak a raw solver word into the field a gate is written on."""
    bodies = {
        "dfba_sensitivity.json": _uninterpretable_sensitivity(),
        "host_generic_summary.json": {"solve": {"status": "solver_failed"}},
        "host_benchmark.json": {"solve": {"status": "unbounded"}},
        "stats_sweep_summary.json": {"inference": {"status": "not_run_fewer_than_two_replicates"}},
        "model_review.json": {"namespace": {"blocked": True}},
        "host_map_summary.json": {"n_microbial_secretions": 3, "n_exact": 2},
        "publication_benchmark.json": {"computational_checks_passed": True,
                                       "overall_passed": True, "checks": {"a": True}},
        "stats_summary.json": {"summary": []},
    }
    for filename, body in bodies.items():
        run = tmp_path / filename.replace(".json", "")
        run.mkdir()
        (run / filename).write_text(json.dumps(body))
        status = _inspect_run_dir(run)["status"]
        assert status in GATE_VOCABULARY | {"unknown"}, f"{filename} leaked {status!r}"


# ── C2: the false temporal cause ──────────────────────────────────────────────

def _text(tmp_path, capsys) -> str:
    _cmd_inspect_run(argparse.Namespace(run_dir=str(tmp_path), format="text"))
    return capsys.readouterr().out


def test_a_solve_manifest_is_not_accused_of_predating_result_digests(tmp_path, capsys):
    """`cmig solve` never emits a result digest; it does not "predate" one."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "manifest_schema_version": "2.0",
        "manifest_scope": "solve",
        "run_hash": "a" * 64,
        "diagnostic": None,
    }))
    out = _text(tmp_path, capsys)
    assert "result_digest: not recorded" in out
    assert "predates" not in out, "the temporal claim is false for a solve manifest"
    assert "cmig solve" in out and "workflow" in out


def test_a_run_without_a_manifest_does_not_blame_a_manifest(tmp_path, capsys):
    (tmp_path / "dfba_sensitivity.json").write_text(
        json.dumps(_uninterpretable_sensitivity(interpretable=True))
    )
    out = _text(tmp_path, capsys)
    assert "result_digest: not recorded" in out
    assert "predates" not in out
    assert "no manifest.json" in out


def test_a_workflow_manifest_without_a_digest_is_the_only_temporal_case(tmp_path, capsys):
    """Here — and only here — "predates result digests" is a true statement."""
    write_workflow_manifest(
        tmp_path, "host_map", golden_components("host_map"),
        status="ok", artifacts=[],
    )
    payload = json.loads((tmp_path / "manifest.json").read_text())
    del payload["result_digest"]
    (tmp_path / "manifest.json").write_text(json.dumps(payload, sort_keys=True))
    out = _text(tmp_path, capsys)
    assert "predates result digests" in out


@pytest.mark.parametrize(
    ("manifest", "reason"),
    [
        ({}, "no_manifest"),
        ({"manifest_scope": "solve"}, "solve_manifest_never_records_one"),
        ({"manifest_scope": "workflow"}, "workflow_manifest_predates_result_digests"),
        ({"manifest_schema_version": "1.0"}, "manifest_declares_no_scope"),
    ],
)
def test_every_reason_the_resolver_can_return_has_a_message(manifest, reason):
    """A reason without a message would raise KeyError inside the text renderer."""
    assert _result_digest_absent_reason(manifest) == reason
    assert reason in _RESULT_DIGEST_ABSENT_MESSAGES


def test_the_reason_travels_in_the_json_payload_too(tmp_path):
    """`--format json` is what SKILL.md tells an agent to read, so it needs the reason as well."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "manifest_schema_version": "2.0",
        "manifest_scope": "solve",
        "run_hash": "a" * 64,
        "diagnostic": None,
    }))
    payload = _inspect_run_dir(tmp_path)
    assert payload["artifact_integrity"] == "not_recorded"
    assert payload["result_digest_absent_reason"] == "solve_manifest_never_records_one"
