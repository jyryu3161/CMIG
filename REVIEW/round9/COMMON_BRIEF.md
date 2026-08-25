# Round-9 Common Brief (all tracks)

You are one of six parallel implementation agents working on CMIG in an isolated
git worktree. Read `REVIEW/ORCHESTRATION_NOTES.md` — its rules are binding.
Highlights, plus what changed since round 8:

1. **No git commands at all** (branch/checkout/add/commit). Leave everything
   uncommitted in the working tree; the coordinator reviews and commits.
2. **File ownership is absolute.** This round:
   - `cmig/cli/main.py`, `cmig/core/workflow_manifest.py`,
     `cmig/core/workflow_envelope_golden.{py,json}` are owned by track V1 only.
   - `pyproject.toml`/`uv.lock` are frozen for every track.
   - `CHANGELOG.md`, `README.md`, `docs/**`, `.claude/skills/**` are
     coordinator-owned; put proposed entries in your report.
   If a needed change is outside your ownership, record it in the report's
   Integration notes — do not make it.
3. **Environment.** Your venv is pre-synced; use `uv run --no-sync` for
   everything. The sandbox cannot read `~/.cache/uv` — set
   `UV_CACHE_DIR=/tmp/cmig-round9-<track>-uv-cache` on every uv invocation.
   Never run `uv sync` yourself.
4. **Scientific honesty** (project law): no number without its basis, no silent
   behavior change, keep warnings/diagnostics, policy markers keep their
   meaning. Intentional behavior changes go in your proposed-CHANGELOG section.
5. **Hash discipline.** The frozen 11-component solve `run_hash` must not move.
   `uv run --no-sync cmig golden verify-envelope` must stay green for all 17
   existing kinds; only V1 may add kinds (additively, via the documented
   generator). On unexpected drift: STOP and record it.
6. **Exit criteria**: ruff clean; `mypy cmig` 0 errors; owned tests green;
   envelope gate per rule 5; report written (NOT committed) at
   `REVIEW/round9/report_V<n>.md` with (a) what/why, (b) verification log,
   (c) proposed CHANGELOG entries, (d) integration notes/risks, (e) proposals
   deliberately not implemented. Write the report only when genuinely done —
   the coordinator's monitor watches for that file.
7. QtWebEngine cannot start in this sandbox (SIGTRAP) — report it, don't chase
   it; the coordinator re-runs GUI sets on the host. If blocked on anything,
   record the blocker and continue with the rest of your scope.

Key references: `REVIEW/round8/COORDINATOR_LOG.md` (what just landed and the
deferred list this round draws from), `CHANGELOG.md` `[Unreleased]`,
`docs/USER_GUIDE.md`.
