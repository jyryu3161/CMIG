# Round-7 Common Brief (all tracks)

You are one of six parallel implementation agents working on CMIG in an isolated
git worktree. A coordinator (final reviewer) will review your diff, run the full
gates, and merge. Follow this brief exactly.

## Ground rules

1. **File ownership is absolute.** Your track brief lists the files/directories you
   own. Do not modify anything outside that list. In particular:
   - `cmig/cli/main.py` is owned by track T1 only.
   - `pyproject.toml` and `uv.lock` may be changed by track T3 only.
   - Serialization affecting `run_hash` (`cmig/core/workflow_manifest.py`,
     `cmig/core/manifest.py`, `cmig/core/golden.py`) may be changed by T1 only,
     and only via the documented schema-evolution procedure.
   If you believe a change outside your ownership is required, do NOT make it —
   record it in the "Integration notes" section of your report instead.
2. **Branch & commits.** Your startup prompt names your track branch; create it
   first thing with `git checkout -B <branch-name>` in this worktree. Commit with
   titles starting `round7 <branch-name>` (round-6 convention). Small, reviewable
   commits are preferred over one giant commit.
3. **Environment.** The worktree has its own venv: run `uv sync --all-extras --group dev`
   once before starting. Use `uv run <cmd>` for everything. Do not add or upgrade
   dependencies (except T3, per its brief).
4. **Scientific honesty (project law).** Never report a computed number without its
   basis; keep existing warnings/diagnostics intact; no silent behavior changes;
   markers like `boundary_isolation_policy` / `host_isolation_policy` must keep
   their meaning. When behavior intentionally changes, add a CHANGELOG entry under
   `## [Unreleased]` in the appropriate subsection.
5. **Exit criteria (all must hold before you declare done).**
   - `uv run ruff check .` → clean
   - `uv run pytest -q tests/<your-owned-test-files>` → green
   - `uv run cmig golden verify-envelope` → unchanged (unless your brief explicitly
     says you are evolving the schema, in which case follow the procedure)
   - A report committed at `REVIEW/round7/report_<track-id>.md` containing:
     (a) what changed and why, (b) verification log (commands + results),
     (c) integration notes / risks for the coordinator, (d) proposals you
     deliberately did NOT implement (out of ownership or out of scope).
6. **Do not touch other tracks' report files** or `REVIEW/round7/BRIEF_*.md`.
7. If you get blocked (missing asset, failing precondition, ambiguous spec),
   record the blocker in your report and continue with the rest of your scope.
   Do not improvise outside ownership to unblock yourself.

## Key reference documents (read before coding)

- `README.md` — Scope And Limitations section
- `CHANGELOG.md` `## [Unreleased]` — recent round-5/6 semantics
- `REVIEW/FINAL_REPORT_ROUND5_2026-07-26.md` — "Known open, deliberately"
- `.claude/skills/cmig-metabolic-analysis/SKILL.md` — user-facing contract
