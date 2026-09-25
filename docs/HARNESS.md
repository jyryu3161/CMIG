# CMIG phase harness

This repository-local harness sequences a validated phase on the current checkout. It adapts the useful sequential prompting, stdin handoff, prior-step summaries, and common Codex/Claude hooks from `../kbase_kinase` commit `77354f94b844a8c64e7cd47691ac20a2e96214b3` (`scripts/execute.py`, `.codex/hooks*`, `.claude/commands*`). It is standalone: no sibling checkout is read at runtime. CMIG changes the reference's all-Astra, agent-edited status, automatic checkout/commit/push, blanket bypass and permissive pytest exit-5 behavior. Runner-owned state and independent checks determine completion.

## Setup and use

Explicitly provision the environment once:

```bash
uv sync --extra engine --extra render --extra stats
uv run --no-sync python scripts/execute.py --help
```

Copy `phases/templates/phase-index.json` into `phases/<name>/index.json`, add `step0.md`, `step1.md`, etc. with the `step.md` template, and add the phase name to `phases/index.json` if you want a source catalogue entry. The example declares a plan report as an implementation input and an implementation output as a review input; earlier declared outputs may be read by later steps. Tailor all paths, checks and acceptance text to the task. The templates cannot run directly. The final step must be an Astra review. Roles, paths, nonempty Acceptance sections, check IDs, integer timeouts and attempts are validated before any live mutation.

```bash
uv run --no-sync python scripts/execute.py <name> --dry-run
uv run --no-sync python scripts/execute.py <name>
uv run --no-sync python scripts/execute.py <name> --resume
```

Dry-run prints resolved roles, models, checks, scope and deadlines. It does not invoke Codex, run checks, write state, change Git, or need a model account or solver license. Live execution uses `gpt-6-sol` for implementation, `gpt-6-astra` for plans and reviews, and medium reasoning effort. Plan/review are read-only; a report path is written by the runner from the structured response. Implement uses the user's configured sandbox by default. This authorized dispatch uses approval policy `never`; the CLI exposes `--approval-policy on-request` for a differently configured workspace. `--trusted-hooks` is an explicit opt-in for vetted hook trust bypass; ordinary persisted trust is the default. There is no model fallback. The installed `codex-cli 0.156.1` supports `codex -a never exec` with `--model`, `--sandbox`, `--json`, `--output-schema`, `--output-last-message` and stdin `-`; `--full-auto` is not used.

State records `user-configured` when no implementation sandbox flag is supplied. That label does not prove Codex's effective sandbox or inheritance of a parent session's CLI override; inspect the actual Codex configuration for that claim.

The default keeps the current branch, current index and unrelated edits, and makes no commit or push. `--branch <new>` is opt-in and requires a clean checkout; it refuses an existing name. `--commit` requires a clean initial checkout and stages only validated owned paths after the final review passes. There is no push option. Pre-existing changes to owned paths block launch. Unexpected writes are diagnosed and retained for inspection, never reset. Runner state and attempt logs live in ignored `.run/harness/<phase>/`; raw model output may contain project data, so keep that directory local.

## Acceptance and recovery

A child must exit zero, write schema-valid final JSON, return a role-appropriate result, stay in scope, and pass every runner-executed check. The final review must return `pass`; `changes_requested` keeps the phase incomplete. A failed or skipped pytest collection, missing command, timeout or malformed JUnit cannot count as success. `max_attempts` defaults to one and caps at three; ordinary implementation/check failures can retry with feedback. Timeout, interruption, blocker and scope violation stop immediately. A live nested runner is refused.

State writes are atomic and an exclusive lock rejects a second writer. If interrupted, inspect `.run/harness/<phase>/state.json` and its lock before recovery. A `running`, `error`, `blocked`, `cancelled` or unknown state is not inferred complete. `--resume` requires a compatible state schema, successful attempt/check evidence, the same phase definition and check code, HEAD, branch, index, protected initial files, declared inputs and completed outputs. It resumes pending steps only. Do not delete a lock or edit state blindly; diagnose the owning process and inputs first. Run logs keep each attempt's JSONL, stderr, final JSON and check/JUnit evidence. No credentials or full environment dump is recorded.

The hook configuration in `.codex/hooks.json` and `.claude/settings.json` calls the same Python scripts. `PreToolUse` blocks common destructive shell accidents within 10 seconds. `Stop` runs only smoke within a 90-second outer limit and gives bounded feedback once; it skips reentrant invocations. Hook feedback never replaces runner acceptance. Hook launchers locate the repository from a nested working directory, and checks require the repository `.venv` Python, including `.venv/Scripts/python.exe` on Windows. If that interpreter is missing, the check is blocked with setup guidance.

On POSIX, timed-out or interrupted checks terminate their process group even if the leader already exited. Windows cleanup uses `taskkill /T` and a descendant snapshot fallback; native Windows process behavior still needs a Windows run before claiming that platform validated.

## Check tiers

Run a tier directly with `uv run --no-sync python scripts/harness_checks.py --tier <name>`. Check definitions and deadlines are in that file; tiers expand to deduplicated command IDs.

| Tier | Meaning |
| --- | --- |
| `smoke` | Ruff and the three harness regression modules; no solver, GUI, model or network; 75-second budget. |
| `quality` | Smoke, lock, release version, strict `mypy cmig`, envelope gate and the current license-free CI selection; 900-second budget. |
| `solver` | Golden version/hash gate plus fresh engine, search policy and service tests; needs tracked microbial GEMs and a working Gurobi license; 1,800-second budget. |
| `gui` | Offscreen app shell, round-5 and launcher regressions with Qt; 1,800-second budget. This is not visual usability approval. |
| `full` | Quality, golden gate, whole pytest suite and publication smoke; 2,700-second budget and all extras/fixtures/license for the claimed scope. |

For installing this harness, quality plus `uv build` and `uv run --no-sync python scripts/audit_distribution.py dist/*` are required. Licensed solver and GUI validation belong to later scientific/product changes. The golden version/hash command does not re-solve. A solver capability listing does not prove a Gurobi license. Synthetic or mocked search tests do not establish metabolic accuracy or GEM throughput. Optional skipped external host fixtures must be reported as partial coverage; mandatory tier skips are not accepted. Publication validation follows `docs/PUBLICATION_VALIDATION.md` with real inputs and provenance, and is not silently launched by Stop.

The root `AGENTS.md` is the canonical development rule source; `CLAUDE.md` imports it. The existing metabolic-analysis skill remains a user workflow aid. The published sdist excludes `docs/HARNESS.md`, `AGENTS.md`, `.codex/`, `.claude/`, `phases/` and the new harness runner, check catalogue, schema and regression modules. Other `scripts/` and `tests/` members retain the existing distribution policy. The README links to this guide in the source repository so its link also works from a published sdist.
