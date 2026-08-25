# Round-9 Track V2 — `fix/answer-quality`

Read `REVIEW/round9/COMMON_BRIEF.md` first. Two answer-quality defects,
both flagged in earlier rounds and both in files nobody else owns this round.

## Goal

1. **`cmig/core/metrics.py::community_contributions` missing-abundance
   fallback.** Round-8 U2 established the fail-closed contract for
   `edges.weight` (`MissingAbundanceError`; a missing abundance is not
   "assume 1.0") and flagged that `community_contributions` still holds a
   factor-1.0-style fallback that can fabricate a target-share contribution
   (`REVIEW/round8/report_U2.md` §Integration note 6). Read the round-5
   material and the current implementation, then adjudicate:
   - align the behavior with the fail-closed policy (preferred), OR document a
     scientifically defensible reason this surface must differ — in either
     case the decision record goes in your report with the losing option's
     failure mode;
   - trace every consumer (`abundance-impact`'s `target_influence_share`,
     `search_advanced` prescreens, anything else importing it) and show what
     their outputs do under a missing abundance before/after. NaN-with-
     diagnostic beats silent fabrication; hard error beats NaN where the
     contract demands it. Update the consumers' tests you own accordingly —
     if a consumer's fix requires `cmig/cli/main.py`, record it as an
     integration note instead.
2. **`pareto` column beyond two targets.** In multi-target search the per-row
   `pareto` column is only computed for exactly two targets; with more, every
   cell stays `False` — "not evaluated" masquerading as "dominated"
   (`docs/USER_GUIDE.md` Scope; round-5 eval finding). Fix properly in
   `cmig/core/search_product.py`: compute true Pareto-frontier membership for
   arbitrary target counts (the per-target capability values exist per row), or
   if you find a principled blocker, change the column to a three-valued
   explicit disclosure (`true`/`false`/`not_evaluated`) — never a silent False.
   Add tests for 3+ targets including ties and dominated/non-dominated mixes.
   Check whether `--multi-metric pareto` mode and the column share code and
   keep their semantics consistent.

## Ownership

- `cmig/core/metrics.py`, `cmig/core/search_product.py`,
  `cmig/core/search_advanced.py` (only if consumer tracing requires it)
- tests: `tests/test_search_product.py`, `tests/test_round9_answer_quality.py`
  (new), existing metrics/abundance-impact test files (list every edit)

## Constraints

- No solve-golden or envelope changes; `search_summary.json` shape changes are
  behavior changes — propose the CHANGELOG entry and check
  `tests/test_search_product_ga_scaling.py` still holds.
- Real Gurobi verification for at least one 3-target pareto case and one
  missing-abundance case end-to-end at the library level.
