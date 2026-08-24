# Round-7 Coordinator Log

Coordinator: Claude (Fable 5) session. Workers: codex `gpt-5.6-sol`,
`model_reasoning_effort=xhigh`, one per Orca-managed worktree
(`~/orca/workspaces/CMIG/round7-*`), launched as
`codex -a never --sandbox workspace-write` (T3/T5 additionally with
`-c sandbox_workspace_write.network_access=true` for dependency and GEM
downloads). Full plan of record: the approved round-7 plan (six
file-ownership-disjoint tracks after a phase-0 GA landing).

## Phase 0 — GA branch landing

- `origin/agent/ga-consortium-search` (47b7cb7, +1,913/−117 over 10 files)
  reviewed in full: deterministic GA (tie-broken tournament, swap mutation,
  evaluation budget/patience/history), lazy combination counting plus Floyd
  sampling with combinatorial unranking, robustness FVA deferred to the final
  top-k, multi-target `--robustness-fva` turned from silently-inert into an
  explicit rejection.
- Gates before merge: ruff clean; full pytest exit 0; `golden verify-envelope`
  13/13; mypy at the then-baseline 17 errors (all pre-existing on main).
- Merged as `cfa67af`; stale fully-merged branches
  `feat/eval-2026-07-09-recommendations` and
  `feat/r-render-host-wizard-multitarget-dir` deleted.
- Track briefs committed as `a6cf364` (`REVIEW/round7/BRIEF_*.md`) — the branch
  base for every worktree.

## Track review results

| Track | Branch | Verdict | Coordinator interventions |
| --- | --- | --- | --- |
| T1 exact-medium | `feat/exact-medium` | Accepted | Full-suite run caught the round-5 schema-version pin test (`== "1.1"`) conflicting with the intended 1.2 bump — literal updated to 1.2 (the test's own message demands the bump). One new mypy finding on `Context.run` silenced with an explicit result annotation. |
| T2 gui-graph-profile | `feat/gui-graph-profile` | Accepted | Worker sandbox SIGTRAP'd QtWebEngine; coordinator ran all 82 GUI tests green on the host, including the renderer test. |
| T3 io-hardening | `feat/io-hardening` | Accepted | None. Third-seed randomized run re-verified. |
| T4 docs-release | `docs/release-freshness` | Accepted | None. Spot-verified checklist gate, citation scan, tutorial coverage, and that `--exact-medium` was correctly left undocumented for the reconcile step. |
| T5 host-two-interface | `feat/host-two-interface` | Accepted | None on content. Worker self-committed. Coordinator re-ran 64 core host tests with the downloaded Recon3D/RECON1. |
| T6 figure-dedup-tests | `chore/figure-dedup-tests` | Accepted | None. Byte-identity hashes re-verified via the owned test set. |

Worker-environment findings recorded for future rounds:

- The codex managed sandbox blocks linked-worktree git metadata
  (`.git/worktrees/<name>/index.lock` → `Operation not permitted`), so most
  workers could not branch/commit; the coordinator committed after review
  (T3/T5 self-committed via the Orca host terminal path).
- Six concurrent `uv sync --all-extras` runs saturated the network; three
  needed a sequential retry. Workers correctly fell back to the parent venv
  with worktree-pinned imports and said so in their reports.

## Integration (`round7/integration`)

Merge order T4 → T3 → T6 → T5 → T2 → T1. One conflict
(`medium_presets/PROVENANCE_gut_media.md`): T4's symbol citation and T1's
status sentence combined (`7a50d21`).

Coordinator cross-cutting commit (`2254246`):

1. **mypy clean under the pinned `mypy==2.1.0`** — mandatory once T3 pinned the
   checker, since CI runs `mypy cmig`. Track fixes brought 17 → 9; the
   remaining nine (host-ko sort key, four output writers' `artifacts` typing)
   fixed here. `Success: no issues found in 77 source files`.
2. **`cli/main.py` adopts `cmig/render/figure_style`** per T6's mapping; the
   round-5 byte-reproducibility guard now asserts both writer modules consume
   the shared policy object; `tests/test_figure_publication_export.py` imports
   moved to the canonical home.
3. **T5's requested CLI wiring**: side-aware `{host_exchange, interface}`
   reviewed-map values accepted (validated by
   `host_types.reviewed_interface_entry`; legacy strings byte-compatible),
   `host-map` artifacts gained `interface`/`interface_evidence` and side
   counts, `host-generic` reports `interface_classification`,
   `PublicationBenchmarkConfig.host_interface_map` widened to the core type.
4. **Docs reconcile**: CHANGELOG round-7 entries (all six tracks), stale
   "not implemented" sentence corrected; README exact-medium section and
   atomic-scope update; SKILL.md exact-medium decision point + flag row and
   the GA landing's multi-target `--robustness-fva` rejection.
5. `tests/test_cli_publication.py` stub module extended with
   `cli_exact_medium` (the T6-era stub predated T1's dispatch-scope import).

Second integration fix, caught by the final randomized full suite: T5's
`__getattr__` removal silently changed patch semantics — `cli/main.py` and
`publication_benchmark` imported `run_bigg_host_microbe` *through*
`cmig.core.host`, whose new static binding no longer follows a monkeypatch on
`host_coupling`, so the round-5 non-optimal-host-LP guard tests were
exercising the real solver instead of their stub (`test_round5_final_fixes.py`
failed 2–3 tests depending on order). Fixed by importing the coupling entry
points from their defining module `cmig.core.host_coupling`; `host.py` keeps
the re-export for API compatibility. This is the round's best argument for
running the full suite at integration rather than trusting per-track green.

## Final gates on `round7/integration`

- `uv run ruff check .` → All checks passed.
- `uv run mypy cmig` → Success, 0 errors in 77 files (baseline was 17).
- `uv run cmig golden verify-envelope` → unchanged for 13 workflow kinds
  (the single intended schema-1.2 drift was re-blessed inside T1).
- `uv run cmig golden verify` → all solver goldens match installed MICOM and
  published run_hash (Gurobi + OSQP).
- Full randomized pytest (`--randomly-seed=20260824`): see the result recorded
  in the merge commit to main.

## Deferred / follow-up (candidates for round 8)

- `edges.parquet.weight` value fix (dual-solver golden re-bless) — still the
  top known-open scientific item.
- Figure writers and the `cmig/cli/main.py` / core Parquet call sites T3 listed
  remain non-atomic.
- Gut-overlay closure rows: removing them for exact-mode users needs a
  `build_gut_media.py` generator change (T1 correctly declined under data-table
  ownership).
- GUI: heatmap/scenario-diff/sandbox delta overlays; Sweep tab still drives the
  fixture only; pair/delta/single CLI surfacing; stats 5b/5c; 0.2.0 release
  execution per `docs/release-drafts/`.
