"""P0-B / P0-C — an unevaluable candidate must never occupy a rank, be hidden by --top-k, or be
called "best".

Round-2 findings this pins:

- red-team F1: failed candidates sorted to the bottom on ``score=-inf`` and were then cut by
  ``--top-k``, so the same pool reported the failure at ``--top-k 10`` and hid it at ``--top-k 2``;
- red-team F2 / codex B1: with nothing evaluable, a failed candidate got rank 1, target flux 0, was
  printed as "best", and the run reported ``status: ok``;
- codex B2: multi-target rows the warning called "excluded from ranking" still carried ranks 2/3
  and lived in ``top_ranked``.

Pure ranking/partition logic — no solver.
"""

from __future__ import annotations

import math

from cmig.core.search import Direction, TargetSpec
from cmig.core.search_product import (
    PoolRank,
    _ComboEval,
    _ranking_degeneracy_warnings,
    is_evaluable,
    rank_multi_target,
    unevaluable_warnings,
)

SPECS = [
    TargetSpec("ac", Direction.MAX_SECRETION, 1.0),
    TargetSpec("but", Direction.MAX_SECRETION, 1.0),
]


# ── the evaluability predicate ───────────────────────────────────────────────────

def test_only_optimal_finite_rows_are_evaluable():
    assert is_evaluable("optimal", 12.1) is True
    assert is_evaluable("optimal", 0.0) is True          # zero is a result, not a failure
    assert is_evaluable("infeasible", 0.0) is False
    assert is_evaluable("missing", 0.0) is False
    assert is_evaluable("failed", 0.0) is False
    assert is_evaluable("optimal", float("-inf")) is False
    assert is_evaluable("optimal", float("nan")) is False


# ── the top-level warning that --top-k cannot truncate ───────────────────────────

def test_unevaluable_warning_names_every_dropped_candidate():
    warnings = unevaluable_warnings([(("A", "B"), "infeasible", "LP infeasible")], 3)
    assert len(warnings) == 1
    assert "1 of 3 candidates could not be evaluated" in warnings[0]
    assert "A+B" in warnings[0]


def test_nothing_evaluable_says_there_is_no_best_producer():
    warnings = unevaluable_warnings(
        [(("A",), "missing", None), (("B",), "missing", None)], 2
    )
    assert any("no candidate was evaluable" in w for w in warnings)
    assert any("no best producer" in w for w in warnings)


def test_no_failures_means_no_warning():
    assert unevaluable_warnings([], 3) == []


def test_warning_is_independent_of_how_many_rows_a_caller_will_display():
    """F1: the warning is built from the full failure list, so --top-k cannot erase it."""
    failures = [(("A", "B"), "infeasible", None)]
    assert unevaluable_warnings(failures, 3) == unevaluable_warnings(failures, 3)
    assert "A+B" in unevaluable_warnings(failures, 3)[0]


# ── multi-target: rank 0 means "no rank" ─────────────────────────────────────────

def _eval(members, fluxes, *, status="optimal"):
    signed = {k: float(v) for k, v in fluxes.items()}
    return _ComboEval(members, status, 0.4, dict(fluxes), signed, None, (), "joint_weighted_lp")


def test_unevaluable_multi_target_rows_get_rank_zero():
    rows, _ = rank_multi_target(
        [
            _eval(("A",), {"ac": 10.0, "but": 0.0}),
            _eval(("B",), {}, status="infeasible"),
            _eval(("C",), {"ac": 5.0, "but": 0.0}),
        ],
        SPECS,
        metric="raw_sum",
    )
    by_members = {r.members: r for r in rows}
    # Evaluable rows are ranked 1..N contiguously.
    assert by_members[("A",)].rank == 1
    assert by_members[("C",)].rank == 2
    # The unevaluable row carries no rank at all — not rank 3.
    assert by_members[("B",)].rank == 0
    assert math.isinf(by_members[("B",)].weighted_score)


def test_ranks_are_contiguous_even_when_failures_sort_between_winners():
    rows, _ = rank_multi_target(
        [
            _eval(("A",), {"ac": 1.0, "but": 0.0}),
            _eval(("FAIL",), {}, status="failed"),
            _eval(("B",), {"ac": 9.0, "but": 0.0}),
        ],
        SPECS,
        metric="raw_sum",
    )
    ranked = sorted(r.rank for r in rows if r.rank > 0)
    assert ranked == [1, 2]
    assert [r.members for r in rows if r.rank == 1] == [("B",)]


def test_all_unevaluable_yields_no_ranked_row_at_all():
    rows, _ = rank_multi_target(
        [_eval(("A",), {}, status="missing"), _eval(("B",), {}, status="missing")],
        SPECS,
        metric="raw_sum",
    )
    assert all(r.rank == 0 for r in rows)
    assert [r for r in rows if r.rank > 0] == []


# ── single-target partition semantics (PoolRank level) ───────────────────────────

def _pool_rank(members, score, status="optimal") -> PoolRank:
    return PoolRank(
        rank=0, members=members, score=score, target_flux=score,
        community_growth=0.3, status=status,
    )


def test_partitioning_a_mixed_result_keeps_failures_out_of_the_ranked_list():
    rows = [
        _pool_rank(("A", "B"), 12.1),
        _pool_rank(("A", "C"), float("-inf"), "infeasible"),
        _pool_rank(("B", "C"), 5.1),
    ]
    solved = [r for r in rows if is_evaluable(r.status, r.score)]
    failed = [r for r in rows if not is_evaluable(r.status, r.score)]
    assert [r.members for r in solved] == [("A", "B"), ("B", "C")]
    assert [r.members for r in failed] == [("A", "C")]


def test_degeneracy_warning_ignores_unevaluable_rows():
    """A run whose only zero-scores are failures must not be called an all-zero ranking."""
    scored = [
        (("A",), 12.1, "optimal"),
        (("B",), float("-inf"), "infeasible"),
    ]
    assert _ranking_degeneracy_warnings(scored) == []


def test_all_zero_evaluable_scores_still_warn():
    scored = [(("A",), 0.0, "optimal"), (("B",), 0.0, "optimal")]
    warnings = _ranking_degeneracy_warnings(scored)
    assert any("no candidate achieved a non-zero target flux" in w for w in warnings)


def test_normalized_metric_zero_score_does_not_deny_an_observed_flux():
    """codex B3: a single-candidate min-max range is zero-width; the flux was still 12.1."""
    scored = [(("A",), 0.0, "optimal")]
    normalized = _ranking_degeneracy_warnings(scored, score_is_flux=False)[0]
    flux_based = _ranking_degeneracy_warnings(scored, score_is_flux=True)[0]
    # The flux-based wording asserts the flux itself was zero; the normalized wording must not.
    assert flux_based.startswith("no candidate achieved a non-zero target flux")
    assert not normalized.startswith("no candidate achieved a non-zero target flux")
    assert "scored 0" in normalized
    assert "zero score range" in normalized      # names the real cause
    assert "rather than zero target flux" in normalized   # explicitly declines to deny the flux
