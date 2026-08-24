# Round-8 Coordinator Log

Coordinator: Claude (Fable 5) session. Workers: codex `gpt-5.6-sol` xhigh, one
per Orca worktree (`~/orca/workspaces/CMIG/round8-*`),
`codex -a never --sandbox workspace-write`. Base: `ecce0dd` (briefs on main
after round 7). Round-7 lessons applied: workers run no git (coordinator
commits after review), venvs pre-synced sequentially (6/6 first try), completion
signal = the report file appearing in the worktree.

## Incident

Minutes after dispatch, codex self-updated 0.148.0 → 0.149.1 and every running
TUI lost its tool host (`codex-code-mode-host is missing`). All six workers were
restarted on the new binary and re-prompted; no files had been changed.

## Track review results

| Track | Branch | Verdict | Notes |
| --- | --- | --- | --- |
| U1 pair-delta-single-cli | `feat/pair-delta-single-cli` | Accepted | The round-5 "one API redesign" delivered: unified translated medium contract; the mixed-media amensalism→controlled neutralism demonstration; 4 additive workflow kinds (envelope 13 OK + 4 NEW → 17 OK); solve hashes frozen. |
| U2 edges-weight | `fix/edges-weight` | Accepted | Tidy 1.3 community-basis weights; fail-closed `abundance is None` decision recorded against the losing factor-1.0 contract; 8.44× inversion corrected on a real solve with member-sum = profile identity; dual-solver golden re-bless with byte hashes; run_hash unchanged both solvers. Precisely enumerated every non-owned surface the change makes stale. |
| U3 atomic-adoption | `chore/atomic-adoption` | Accepted | Atomic figures/sweep/golden parquet + best-effort dir fsync; all 8 figure hashes equal round-7 T6's recorded values; exact adoption mappings incl. the insight that render_profile needs a RenderClient change, not a caller wrap. |
| U4 gut-media-generator | `feat/gut-media-generator` | Accepted | `row_role` marker; 717 value pairs ordered-identical and `medium_checksum` invariant (coordinator re-verified independently). |
| U5 gui-sweep-overlays | `feat/gui-sweep-overlays` | Accepted | Real sweep axes, heatmap, delta overlays; 127 GUI tests green on the host (worker sandbox SIGTRAPs QtWebEngine). |
| U6 community-dfba | `feat/community-dfba` | Accepted | 1-member reduction at machine precision (2.2e-14), cross-feeding dependence vs stalled control, build-once 6.68× cheaper; honest Gurobi-only / no-death constraints; CLI + workflow-kind proposals recorded for round 9. |

## Integration (`round8/integration`)

Merge order U4 → U3 → U6 → U2 → U5 → U1: zero conflicts (the ownership
partition held exactly).

Coordinator cross-cutting commits (`24d2120` and the pair-fixture recapture):

1. **Tidy 1.3 fallout** across non-owned surfaces: GUI contribution chart no
   longer re-multiplies abundance (version-aware for raw legacy tables; basis
   note + ko string updated); `solve_output.edge_attribution` now imports
   `EDGE_WEIGHT_BASIS`/`EDGE_WEIGHT_UNIT` from `cmig.core.tidy` (the field had
   become false); composer captions, README's *Reading edges.parquet*, and both
   skill references rewritten for the community basis; the 7 stale-contract
   tests updated to community-weighted expectations; the round-5 basis-pin
   tests now assert the shared constants; `fixtures/pair_acetate_butyrate`
   golden re-captured under schema 1.3.
2. Round-7 exact-medium census test learns `pair`/`single`/`minimal-medium`.
3. U3 mappings applied: `save_figure_atomic` in the two remaining main.py SVG
   writers; atomic Parquet in `TidyBundle.write`, `core/matrix.py`, and
   `_write_sweep_profiles`.
4. `test_round8_gui_sweep_overlays` gained deterministic Qt teardown (all tests
   passed but the process segfaulted at interpreter exit — exit 139).
5. CHANGELOG round-8 entries (BREAKING tidy 1.3 + five Added); README baseline-
   analyses section, row_role/atomic/community-dFBA notes; SKILL.md routing
   rows and flag rosters.

## Final gates on `round8/integration`

- `ruff check .` clean; `mypy cmig` 0 errors in 78 files.
- `golden verify-envelope`: unchanged for **17** workflow kinds (4 added
  additively by U1; no schema bump).
- `golden verify`: both solvers match published run_hash after U2's re-bless.
- Full randomized pytest: recorded in the merge commit to main.

## Deferred / round-9 candidates

- `cmig dfba-community` CLI + `community_dfba` workflow kind (U6's report has
  the exact proposal).
- `cmig/core/metrics.py::community_contributions` still holds a factor-1.0
  fallback for missing abundance — inconsistent with U2's fail-closed contract;
  needs its own track (it feeds search target-share outputs).
- `render_profile`'s R-path fallback overwrite needs a RenderClient-level
  atomic change (U3's analysis).
- Multi-file artifact sets are each atomic per file but not transactional.
- `result_digest.cross_run_comparable` remains false for the four new kinds
  until repeat-run byte determinism is measured.
- 0.2.0 release execution per `docs/release-drafts/` (version bump moves
  `CMIG_CORE_VERSION`, a run-hash input → envelope re-bless procedure).
