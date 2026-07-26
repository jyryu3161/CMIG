"""B1(silent half)/B6/B7 regression — 실패가 랭킹의 0 이나 최상위 "ok" 로 위장되지 않는지.

세 가지를 고정한다.
1. host-search: 평가 실패 후보는 랭킹에서 빠지고 별도 `unevaluated` 블록 + warnings + 카운트로
   보고된다 (score=0 으로 섞이면 "host objective 가 진짜 0" 과 구별 불가).
2. 최상위 status 는 하위 상태 중 최악에서 파생된다.
3. inspect-run 은 status 를 안 쓰는 요약에 대해서도 "unknown" 으로 끝내지 않고, 파생 여부를
   status_source 로 밝힌다.
"""

from __future__ import annotations

import csv
import json

from cmig.cli.main import (
    _inspect_run_dir,
    _resolve_run_status,
    _run_status_from_solve,
    _worst_status,
    _write_host_search_bigg_outputs,
)


def _row(members: tuple[str, ...], *, ok: bool, score: float) -> dict[str, object]:
    return {
        "members": members,
        "evaluation_status": "ok" if ok else "failed",
        "score": score,
        "host_objective_value": score,
        "host_status": "optimal" if ok else "failed",
        "host_viable": ok,
        "target": "ac",
        "target_transfer": 0.0,
        "community_growth": 0.4 if ok else 0.0,
        "community_status": "optimal" if ok else "failed",
        "warnings": [],
        "diagnostic": None if ok else "Unable to retrieve attribute 'X'",
    }


def _write(tmp_path, ranked, unevaluated, warnings):
    _write_host_search_bigg_outputs(
        ranked,
        tmp_path,
        target="ac",
        metric="objective_value",
        n_candidates_total=len(ranked) + len(unevaluated),
        n_candidates_evaluated=len(ranked),
        n_candidates_failed=len(unevaluated),
        unevaluated=unevaluated,
        warnings=warnings,
        ranking_parameters={},
        biomass_basis={"kind": "validation"},
    )
    return json.loads((tmp_path / "host_search_summary.json").read_text())


def test_failed_candidate_is_not_ranked_as_zero(tmp_path):
    ranked = [_row(("A",), ok=True, score=1.0), _row(("B",), ok=True, score=0.5)]
    unevaluated = [_row(("A", "B"), ok=False, score=0.0)]
    summary = _write(tmp_path, ranked, unevaluated, ["1 of 3 candidates could not be evaluated"])

    ranked_members = [tuple(row["members"]) for row in summary["top_ranked"]]
    assert ranked_members == [("A",), ("B",)]
    assert all(row["evaluation_status"] == "ok" for row in summary["top_ranked"])
    # 실패 후보는 분리된 블록에만 존재한다.
    assert [tuple(r["members"]) for r in summary["unevaluated"]] == [("A", "B")]
    assert summary["n_candidates_failed"] == 1
    assert summary["n_candidates_evaluated"] == 2
    assert summary["warnings"], "실패 후보가 있으면 최상위 warnings 가 비어 있을 수 없다"
    # B6: 일부 후보가 평가 불가면 최상위는 ok 가 아니다.
    assert summary["status"] == "degraded"
    # 실패 원인은 사람이 읽을 수 있는 파일로도 남는다.
    rows = list(csv.DictReader((tmp_path / "host_search_unevaluated.csv").read_text().splitlines()))
    assert rows[0]["members"] == "A+B"
    assert "Unable to retrieve attribute" in rows[0]["diagnostic"]


def test_all_ok_stays_ok_and_writes_no_unevaluated_file(tmp_path):
    summary = _write(tmp_path, [_row(("A",), ok=True, score=1.0)], [], [])
    assert summary["status"] == "ok"
    assert summary["n_candidates_failed"] == 0
    assert summary["unevaluated"] == []
    assert not (tmp_path / "host_search_unevaluated.csv").exists()
    assert "host_search_unevaluated.csv" not in summary["artifacts"]


def test_no_evaluable_candidate_is_failed(tmp_path):
    summary = _write(tmp_path, [], [_row(("A",), ok=False, score=0.0)], ["nothing evaluable"])
    assert summary["status"] == "failed"
    assert summary["top_ranked"] == []


def test_worst_status_ordering_and_unknown_is_pessimistic():
    assert _worst_status("ok", "ok") == "ok"
    assert _worst_status("ok", "degraded") == "degraded"
    assert _worst_status("degraded", "failed") == "failed"
    # 모르는 값을 성공으로 낙관하지 않는다.
    assert _worst_status("ok", "who_knows") == "failed"
    assert _run_status_from_solve("optimal") == "ok"
    for bad in ("infeasible", "unbounded", "solver_failed"):
        assert _run_status_from_solve(bad) == "failed"


def test_explicit_status_wins_over_derivation():
    assert _resolve_run_status({"status": "degraded"}, {}) == ("degraded", "summary")


def test_ranking_summary_without_status_is_derived_not_unknown():
    optimal = {"top_ranked": [{"status": "optimal"}, {"status": "optimal"}]}
    assert _resolve_run_status(optimal, {}) == ("ok", "derived")
    mixed = {"top_ranked": [{"status": "optimal"}, {"status": "missing"}]}
    assert _resolve_run_status(mixed, {}) == ("degraded", "derived")
    assert _resolve_run_status({"top_ranked": []}, {}) == ("failed", "derived")


def test_solve_manifest_without_status_is_derived_from_diagnostic():
    assert _resolve_run_status({}, {"run_hash": "abc", "diagnostic": None}) == ("ok", "derived")
    assert _resolve_run_status({}, {"run_hash": "abc", "diagnostic": "x"}) == (
        "degraded",
        "derived",
    )


def test_empty_run_dir_still_reports_unknown_honestly():
    assert _resolve_run_status({}, {}) == ("unknown", "unknown")


def test_inspect_run_recognises_model_quality_kind(tmp_path):
    (tmp_path / "model_quality.json").write_text(
        json.dumps({"n_models": 1, "reports": [{"solve_status": "optimal"}]})
    )
    payload = _inspect_run_dir(tmp_path)
    assert payload["kind"] == "model_quality"     # 이전엔 "unknown"
    assert payload["status"] == "ok"
    assert payload["status_source"] == "derived"


def test_inspect_run_flags_a_non_optimal_model_quality_report(tmp_path):
    (tmp_path / "model_quality.json").write_text(
        json.dumps({"n_models": 2, "reports": [
            {"solve_status": "optimal"}, {"solve_status": "infeasible"}
        ]})
    )
    assert _inspect_run_dir(tmp_path)["status"] == "degraded"
