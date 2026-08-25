# Round 9 V2 report — answer quality

Date: 2026-08-25  
Track: V2 / `fix/answer-quality`

## Outcome

Both assigned answer-quality defects are fixed.

1. `community_contributions` now fails closed with the existing
   `MissingAbundanceError` when a member abundance is absent, non-finite, or negative. It no
   longer converts a per-taxon flux into a purported community contribution with an invented
   factor of 1.0. A recorded abundance of zero remains a valid numeric zero.
2. The scalar multi-target ranking's `pareto` column is now real N-dimensional Pareto-frontier
   membership for any supported target count. It uses the same dominance helper as
   `--multi-metric pareto`; equal vectors remain tied members of the frontier, dominated rows are
   false, and unevaluable rows remain false.

No solve golden, workflow-envelope, manifest, CLI implementation, dependency, documentation, or
coordinator-owned file was changed. The search-summary schema is unchanged; the values of the
existing `pareto` boolean and the warning list intentionally change for rankings with more than
two targets.

## What changed and why

### 1. Missing-abundance decision record

Selected contract: **fail closed**.

`member_exchange` is a per-taxon flux. A community contribution requires
`per_taxon_flux * relative_abundance`. `abundance is None` means that MICOM did not provide that
required scaling input. It does not mean abundance 1.0 and does not establish that the member is
the entire community. `community_contributions` therefore now raises the same
`MissingAbundanceError` used when tidy 1.3 edge construction cannot establish its community
basis. The function also aligns with the tidy policy for `NaN`, infinite, and negative
abundances. Zero is distinct from missing and produces a valid zero contribution.

The losing factor-1 option fails scientifically in two ways:

- it publishes an unweighted per-taxon value as an abundance-weighted community quantity;
- it creates a mixed basis within one contribution map when other members do have abundances,
  after which `target_turnover_share` and `target_secretion_share` can rank and plot a fabricated
  number.

Returning a contribution-map `NaN` with a warning was also rejected. Both share helpers aggregate
the map numerically, so a `NaN` can poison every share or require another silent fallback. The
required library contract is a hard error. A batch consumer may isolate the failed point, but it
must then publish null cells and a diagnostic rather than a scientific number.

#### Consumer trace: missing abundance before and after

| Consumer | Before | After |
|---|---|---|
| Direct `community_contributions` caller | Missing or absent abundance became weight `1.0`; e.g. flux `2.0` became contribution `2.0`. | Raises `MissingAbundanceError`; no contribution map or share is returned. |
| `abundance-impact` `target_influence_share`, `target_secretion_share`, and `target_member_contribution` | The missing member supplied a rankable fabricated contribution; the sweep point retained the solve's optimal status. | The existing per-point error boundary records `status: failed`, the missing-abundance diagnostic, and null scientific cells (blank in CSV). No fabricated share reaches an artifact. |
| `search_advanced.mro_mip_prescreen` | Unchanged. It imports `mip_pair`, `mro_pair`, `secretion_sets`, and `uptake_sets`; it never calls `community_contributions` and has no abundance input. | Unchanged for the same reason. |
| `pair.analyze_pair` | Unchanged. It imports other metric helpers only. | Unchanged for the same reason. |

Repository-wide import/call tracing found no other production caller of
`community_contributions`. `target_turnover_share` and `target_secretion_share` remain pure
consumers of a valid contribution map; the hard error prevents them from receiving the invalid
map.

`cmig/cli/main.py` was not edited because V1 owns it. Its point-isolation behavior already gives
null-with-diagnostic output, but an all-failed abundance sweep currently still returns exit code
0. That remaining command-level exit issue is called out under Integration notes.

### 2. Arbitrary-target Pareto column

`rank_multi_target` now:

1. selects evaluable rows;
2. constructs each row's direction-adjusted objective vector in target order;
3. sends all vectors to `pareto_frontier_nd`;
4. maps the returned frontier indices back to the original rows.

Domination is the standard maximisation rule: another row must be greater than or equal on every
target and strictly greater on at least one. Exact equal vectors therefore do not dominate one
another and both remain `pareto=True`. Failed/unevaluable rows are excluded from the frontier and
retain `pareto=False`.

The two Pareto surfaces now share code rather than merely resembling one another:

- the legacy two-dimensional `pareto_frontier` API delegates to `pareto_frontier_nd`;
- the scalar-ranking column calls `pareto_frontier_nd` for every target count;
- `--multi-metric pareto` already calls `pareto_frontier_nd` for its epsilon-sweep points.

Their solve semantics remain intentionally distinct. The scalar column describes dominance among
the one displayed joint weighted-LP vector per consortium. Pareto **mode** constructs multiple
epsilon-constrained vectors per consortium and reports the non-dominated subset of that larger
trade-off set. They now use one dominance definition without falsely claiming that the scalar
column performs the mode's epsilon sweep.

The obsolete warning that said an N-target `pareto=False` meant “not evaluated” was removed.
For more than two targets it now means the same thing it means for two targets: the evaluated row
is dominated. An unevaluable row remains separately disclosed by `rank=0`, non-optimal `status`,
and its diagnostic.

### Files edited

- `cmig/core/metrics.py` — shared fail-closed abundance validation.
- `cmig/core/search_advanced.py` — one N-dimensional dominance implementation and a
  backward-compatible 2D wrapper.
- `cmig/core/search_product.py` — N-dimensional scalar-column calculation and removal of the
  obsolete warning.
- `tests/test_phase4_batch2_regressions.py` — replaced the old factor-1 assertion with the
  fail-closed contract and refreshed the N-dimensional regression description.
- `tests/test_round9_answer_quality.py` — new missing/invalid/zero-abundance, real-Gurobi consumer,
  3-target ties/dominance/failure, and warning regressions.

No other test file was edited. Existing search, scaling, metrics, abundance-impact, and domain
accuracy test files were run as verification.

## Real Gurobi verification

### Missing abundance, library-to-consumer path

`test_real_gurobi_missing_abundance_becomes_a_failed_null_sweep_point` built the synthetic
producer/consumer community and completed its cooperative-tradeoff solve with real Gurobi at
target-member fraction 0.5. The solved result was then fault-injected by replacing the producer's
reported abundance with `None` before the contribution library call.

Observed after the change:

- `community_contributions` raised `MissingAbundanceError`;
- the abundance-impact row was `status: failed`;
- the diagnostic contained `member abundance missing`;
- `target_influence_share`, `target_secretion_share`, and
  `target_member_contribution` were JSON null (and therefore not fabricated numeric values).

This uses a real solve while injecting precisely the absent readout that the contract must handle;
it does not claim that the solver naturally omitted the field in this fixture.

### Three-target scalar Pareto column

A real Gurobi `search_model_pool_multi` run used two MICOM bundled E. coli models as singleton
candidates, scalar metric `raw_sum`, and three maximised targets: `ac`, `co2`, and `etoh`.

Both tied rows solved optimally and reported the achieved vector
`(ac=0.0, co2=41.40491665510194, etoh=0.0)`. Both were correctly `pareto=True`, and the result had
no stale “pareto was NOT computed” warning. The deterministic pure regression separately covers
the more discriminating 3-target mix: two specialists, a balanced point, an exact balanced tie,
a dominated point, and a failed row.

## Verification log

Every command used:

```text
UV_CACHE_DIR=/tmp/cmig-round9-V2-uv-cache uv run --no-sync ...
```

### Lint and typing

```text
ruff check .
All checks passed!; exit 0

mypy cmig
Success: no issues found in 78 source files; exit 0
```

### Owned and relevant regressions

```text
pytest -q \
  tests/test_metrics.py \
  tests/test_search_product.py \
  tests/test_search_product_ga_scaling.py \
  tests/test_search_advanced.py \
  tests/test_search_multi_target_metrics.py \
  tests/test_phase4_batch2_regressions.py \
  tests/test_round5_domain_accuracy.py \
  tests/test_round9_answer_quality.py \
  tests/test_cli_solve.py::test_abundance_impact_cli_sweeps_target_member_fraction \
  tests/test_round5_p3_io_exception.py::test_abundance_impact_figure_drops_points_that_were_never_solved \
  tests/test_round5_p3_io_exception.py::test_abundance_impact_failed_point_is_blank_not_zero

186 passed; 2 expected warnings (one COBRA infeasible-status warning and one explicit legacy-edge
basis warning); exit 0
```

The new round-9 file was rerun after formatting:

```text
pytest -q tests/test_round9_answer_quality.py
7 passed; exit 0
```

`tests/test_search_product_ga_scaling.py` is included in the 186-test set and stayed green, so the
multi-target candidate-count/materialisation guard was not regressed.

### Frozen scientific/provenance gates

```text
cmig golden verify
Gurobi run_hash 29844e2910360332… OK
OSQP run_hash a422eb89d019f917… OK
MICOM 0.39.0 matches both published goldens; exit 0

cmig golden verify-envelope
17/17 workflow kinds OK + float normalization probe
envelope serialization unchanged; exit 0
```

No QtWebEngine test was required by this non-GUI track.

## Proposed CHANGELOG entries

- **Missing abundance now fails target-share calculation:**
  `community_contributions` raises `MissingAbundanceError` when a member abundance is missing,
  non-finite, or negative instead of assuming abundance 1.0. This aligns abundance-impact target
  contributions with tidy 1.3's fail-closed community-basis policy. A recorded zero abundance
  remains a valid zero contribution; failed sweep points publish null shares plus a diagnostic.
- **N-dimensional scalar-ranking Pareto membership:** the existing `pareto` boolean in
  multi-target scalar rankings is now computed for any number of targets. Equal frontier vectors
  remain true, dominated rows are false, and unevaluable rows remain rank 0/false with a
  diagnostic. `--multi-metric pareto` mode keeps its epsilon-constraint solve semantics while both
  surfaces share the same N-dimensional dominance implementation.
- `search_summary.json` keeps the same shape, but for rankings with more than two targets the
  existing `pareto` values and warnings intentionally change: the cells now disclose actual
  frontier membership and the obsolete “not evaluated” warning is gone.

## Integration notes / risks — coordinator action

1. **All-failed abundance-impact exit code (`cmig/cli/main.py`, V1-owned):** the existing inner
   boundary correctly converts `MissingAbundanceError` into a failed row with nulls and a
   diagnostic, but `_cmd_abundance_impact` still returns 0 even when every point failed. Consider
   returning `_exit_code_for_status(...)` (respecting `--allow-failed-run`) so shell automation
   cannot mistake an all-invalid sweep for success. The V2 regression deliberately accepts the
   current 0 or a corrected 3 while pinning the artifact contract.
2. **Stale user documentation (coordinator-owned):** update `docs/USER_GUIDE.md` around lines 325
   and 912. It currently says the scalar `pareto` column is two-target-only and that false means
   “not evaluated.” It should say the column is N-dimensional and describes dominance among the
   displayed scalar-solution rows, while Pareto mode additionally performs the epsilon sweep.
3. **Stale skill guidance (coordinator-owned):** the same old limitation appears in
   `.claude/skills/cmig-metabolic-analysis/SKILL.md` and
   `references/{scientific-validity,workflows}.md`. Update those together so an analysis agent
   does not discard a valid 3+ target frontier.
4. **Stale release text (coordinator-owned):** `CHANGELOG.md` lines 156–157 and
   `docs/release-drafts/0.2.0-changelog-draft.md` describe the two-target-only column. Supersede
   them with the proposed entries above.
5. **Exception documentation location:** `MissingAbundanceError` lives in `cmig/core/tidy.py` and
   its class docstring currently speaks only about community-basis edges. V2 reused the exact
   established policy exception without editing non-owned tidy code. The coordinator may broaden
   that docstring to cover any community-basis quantity, including target contributions.
6. **Complexity:** the shared frontier calculation is `O(rows^2 * targets)`. Multi-target search
   is already exhaustively capped by `exhaustive_max` (default 100), so this is bounded and no new
   materialisation path was introduced.

## Proposals deliberately not implemented

- Did not keep the factor-1 fallback. It invents a whole-community abundance and publishes a
  mixed-basis scientific value.
- Did not return a contribution-map `NaN` plus warning. The contribution contract has a required
  scaling input, and downstream share arithmetic would either be poisoned or need another
  fallback. The library fails; the sweep boundary owns null-with-diagnostic batch isolation.
- Did not treat zero abundance as missing. Zero has a defined result: zero contribution.
- Did not introduce a three-valued Pareto column. There was no blocker to computing the actual
  N-dimensional frontier, so the existing boolean can retain its intended true/false meaning.
- Did not implement another Pareto algorithm in `search_product`; duplicating it would allow mode
  and column semantics to drift. Both now use `pareto_frontier_nd`.
- Did not collapse exact tied vectors into one scalar-ranking row. Distinct consortia with equal
  objective vectors are both non-dominated and both remain disclosed.
- Did not add an epsilon tolerance to dominance. That would redefine the published frontier and
  needs an explicit numerical-policy contract; this fix preserves the existing exact comparison
  used by Pareto mode.
- Did not change Pareto mode's epsilon grid, LP count, reporting order, or top-k behavior.
- Did not edit `cmig/cli/main.py`, documentation, skills, CHANGELOG, manifests, dependency files,
  solve goldens, envelope goldens, or any frozen hash component.
