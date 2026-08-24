# Round-8 Common Brief (all tracks)

You are one of six parallel implementation agents working on CMIG in an isolated
git worktree. A coordinator (final reviewer) will review your working-tree diff,
run the full gates, commit, and merge. Round-7 operational lessons are baked in
below — follow this brief exactly.

## Ground rules

1. **Do NOT run any `git branch`, `git checkout`, `git add`, or `git commit`.**
   The sandbox blocks linked-worktree git metadata writes; round-7 workers
   wasted effort discovering this. Leave ALL changes uncommitted in the working
   tree. The coordinator reviews the diff and commits on your track branch.
2. **File ownership is absolute.** Your track brief lists what you own. Do not
   modify anything outside it. This round in particular:
   - `cmig/cli/main.py` is owned by track U1 only.
   - `cmig/core/workflow_manifest.py`, `cmig/core/golden.py`, and
     `cmig/core/workflow_envelope_golden.json` may be changed by U1 only, via
     the documented schema/kind procedure.
   - `fixtures/**/expected/**` solve goldens may be re-blessed by U2 only, via
     the documented capture procedure.
   - **No dependency changes at all**: `pyproject.toml` and `uv.lock` are
     frozen for every track this round.
   - `CHANGELOG.md` and `README.md` are coordinator-owned; propose entries in
     your report instead of editing them.
   If a change outside your ownership seems required, record it in your
   report's "Integration notes" — do not make it.
3. **Environment.** Your worktree's venv is pre-synced by the coordinator
   (sequentially, to avoid round-7's parallel-download timeouts). Use
   `uv run --no-sync <cmd>` for everything. If the venv looks incomplete, say
   so in your report and fall back to
   `UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv PYTHONPATH=. uv run --no-sync ...`
   with imports pinned to this worktree — never run `uv sync` yourself while
   the coordinator's sync may still be in flight.
4. **Scientific honesty (project law).** Never report a computed number without
   its basis; keep warnings/diagnostics intact; no silent behavior changes;
   policy markers keep their meaning. Every intentional behavior change goes in
   your report's proposed-CHANGELOG section (coordinator lands it).
5. **Hash discipline.** The frozen 11-component solve `run_hash` must not move.
   Workflow-envelope serialization must be unchanged for existing kinds
   (`uv run --no-sync cmig golden verify-envelope`) except where your brief
   explicitly grants an additive/re-bless procedure. If a gate reports
   unexpected drift, STOP and record it — do not re-bless your way past it.
6. **Exit criteria.**
   - `uv run --no-sync ruff check .` clean
   - `uv run --no-sync mypy cmig` reports **0 errors** (the round-7 baseline is
     zero; you may not add any)
   - your owned test files green, plus any adjacent contract tests your brief
     names
   - `uv run --no-sync cmig golden verify-envelope` unchanged (subject to rule 5)
   - a report written (NOT committed) at `REVIEW/round8/report_U<n>.md` with:
     (a) what changed and why, (b) verification log with commands and results,
     (c) proposed CHANGELOG entries, (d) integration notes / risks,
     (e) proposals deliberately not implemented.
   The coordinator's monitor watches for that report file — write it only when
   you are genuinely done.
7. If blocked, record the blocker and continue with the rest of your scope.

## Key references

- `REVIEW/round7/COORDINATOR_LOG.md` — how round 7 ran, and the deferred list
  this round draws from
- `REVIEW/FINAL_REPORT_ROUND5_2026-07-26.md` §"Known open, deliberately"
- `CHANGELOG.md` `## [Unreleased]` round-7 entries — the semantics you build on
