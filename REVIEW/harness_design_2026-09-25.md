# CMIG harness design — 2026-09-25

Design owner: GPT-6 Astra. Implementation owner: GPT-6 Sol. Status: ready for implementation under the existing user authorization; this report does not require another approval round.

Build a small, repository-local adaptation of the `kbase_kinase` sequential phase runner. Preserve its useful workflow, but make completion depend on runner-executed checks, preserve existing worktree edits, and separate cheap development checks from licensed scientific validation. Do not implement product changes as part of harness installation.

## 1. Evidence and provenance

Inspected CMIG at `c45c836f0c12da04404a712f61f53bec0b346675` and reference repository `../kbase_kinase` at `77354f94b844a8c64e7cd47691ac20a2e96214b3`; both were clean at initial inspection. The reference has no literal `harness/` directory: its harness is `scripts/execute.py`, `phases/`, `.codex/hooks*`, and `.claude/commands*`.

Read the reference `AGENTS.md`, `CLAUDE.md`, `.codex/hooks.json`, both hook scripts, `.claude/settings.json`, both command templates, `scripts/execute.py`, `scripts/test_execute.py`, and `scripts/test_codex_hooks.py`. Reuse those mechanisms with attribution in the new runner header and `docs/HARNESS.md`; do not import or execute code from the sibling checkout at runtime. Record the reference commit and intentional deviations, rather than claiming a verbatim copy.

CMIG grounding: `README.md`, `pyproject.toml`, `.github/workflows/ci.yml`, `.gitignore`, root `CMIG_명세서_v3.0.md`, `docs/USAGE.md`, relevant `docs/USER_GUIDE.md` search sections, `docs/PUBLICATION_VALIDATION.md`, `docs/01-plan/schema.md`, baseline PRD/design architecture sections, the golden-solver decision, and the September search review/implementation reports. Checked current search constraints/service, GUI Search controls, solver/golden entry points, and representative ranking, exact-cardinality, checkpoint, scientific-policy, GUI, transaction, and envelope tests. This is design reconnaissance, not a comprehensive code audit or a fresh solver-validation result.

The local `codex-cli 0.156.1` help establishes the installed execution flags. Official [Codex developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli) confirms stdin prompts, explicit model/sandbox selection, structured final output, JSONL events, and the distinction between sandbox bypass and hook-trust bypass. Model names below come from the user's explicit request; availability must be established at execution, never replaced silently.

Coordinator-provided baseline context (not rerun by this design worker): Ruff, strict mypy, versions, envelope, lock, build/distribution audit and the golden version/hash gate passed; the original full suite had 1,537 passed, one AGORA URL-guard failure, and 18 skipped. Evidence is `.run/audit-20260925/baseline-pytest.log`. The product audit owners handle that failure and the whole-codebase coverage matrix; do not expand harness installation into its repair.

## 2. Exact ownership and file map

| Owner | Files | Responsibility |
| --- | --- | --- |
| Astra design, now | `REVIEW/harness_design_2026-09-25.md` | This implementation contract only |
| Sol | `AGENTS.md`, `CLAUDE.md` | Canonical CMIG development rules and thin Claude import |
| Sol | `scripts/execute.py` | Phase validation, model routing, subprocess lifecycle, runner-owned state and completion |
| Sol | `scripts/harness_checks.py` | Single validation catalogue/executor shared by runner and Stop hook; structured check results |
| Sol | `scripts/harness_result.schema.json` | Small final-response schema for Codex; wrapper independently validates required fields |
| Sol | `.codex/hooks.json`, `.codex/hooks/pre_tool_use.py`, `.codex/hooks/stop.py` | Command guard and bounded Stop feedback |
| Sol | `.claude/settings.json`, `.claude/commands/harness.md`, `.claude/commands/review.md` | Same hook scripts, CMIG-specific planning/review commands |
| Sol | `phases/index.json`, `phases/templates/phase-index.json`, `phases/templates/step.md` | Empty phase catalogue and copyable, self-contained authoring templates |
| Sol | `docs/HARNESS.md` | Usage, defaults, provenance, recovery, tiers, and limits |
| Sol | `tests/test_harness_execute.py`, `tests/test_harness_hooks.py`, `tests/test_harness_checks.py` | Mocked Codex and meaningful process/state/check regressions |
| Sol, narrow edits | `.gitignore`, `.github/workflows/ci.yml` | Track only shared Claude config/commands; run the three new test modules in the license-free quality job |
| Astra, after Sol | A separately named report under `REVIEW/` | Review harness implementation and evidence; route fixes back to Sol |
| Runner only | `.run/harness/<phase>/...` | Lock, state, per-attempt JSONL/stderr/final response, validation/JUnit records |

Do not create `AGENTS.ms`. Do not edit existing `scripts/benchmark_search.py`, acquisition, medium-building, distribution-audit, or version-check scripts. Preserve `.claude/skills/cmig-metabolic-analysis/` and any pre-existing local settings. Do not change `cmig/`, dependency pins, golden fixtures, scientific policy, or release versions during this phase. If an actual installation conflict requires more files, document the smallest necessary extension before editing; existing authorization covers routine implementation decisions.

`.gitignore` currently ignores `.claude/*` except `skills/`: add specific exceptions for `settings.json` and `commands/`, leaving `settings.local.json` and other private state ignored. `.run/` already covers harness runtime output. Packaging currently allows `scripts/` and `tests/` in sdist, excludes `REVIEW/`, and selects just three user docs; do not broaden the distribution allowlist to ship developer state or `docs/HARNESS.md`.

## 3. Default behavior and model routing

Proposed public interface:

```text
python scripts/execute.py <phase> --dry-run
python scripts/execute.py <phase>
python scripts/execute.py <phase> --resume
python scripts/execute.py <phase> --branch <new-name> --commit
python scripts/harness_checks.py --tier smoke
python scripts/harness_checks.py --tier quality
python scripts/harness_checks.py --tier solver
python scripts/harness_checks.py --tier gui
python scripts/harness_checks.py --tier full
```

Use `uv run --no-sync python ...` after explicitly synchronizing the chosen environment. The executable files also work with the repository virtualenv Python directly. Runtime must never install dependencies, fetch GEMs, rewrite the lock, create a license, or authenticate automatically.

| Role in phase JSON | Model | Agent permissions | Output |
| --- | --- | --- | --- |
| `plan` | `gpt-6-astra` | Read-only repository inspection | Plan Markdown in final structured response; runner writes declared report path |
| `implement` | `gpt-6-sol` | Existing authorized execution permissions, declared file scope | Scoped changes and proposed completion summary |
| `review` | `gpt-6-astra` | Read-only repository inspection | Findings, coverage limits, and `pass` / `changes_requested` / `blocked` verdict |

Pin model and reasoning effort on every invocation; initial effort `medium`, matching the reference's explicit effort, is a documented configuration default. If later configured differently, record the actual value. Require explicit roles instead of inferring them from step names. No model fallback, implicit OpenRouter routing, or Claude-as-reviewer substitution. A Claude slash command is an entry point to this workflow, not evidence that an Astra review ran.

Construct argv arrays with `shell=False`, send prompts through stdin, and store JSONL events separately from the final JSON response. Use `--model`, `--json`, `--output-schema`, `--output-last-message`, and a noninteractive approval policy supported by the installed CLI (`codex -a never exec ...` on the inspected version). Preserve the invoking user's authorized implementation permissions and record their effective values: this dispatch already has `danger-full-access` and approval policy `never`, so do not insert a new confirmation flow or silently narrow that authorization. In a separately configured workspace, honor its configured sandbox. Plan/review use `--sandbox read-only` to enforce role ownership. Keep AGENTS auto-loading enabled. Preflight CLI help/version and report unsupported flags or model errors clearly.

Default stays on the current branch, makes no commits, and never pushes. Do not blindly copy the reference's blanket sandbox-bypass flag or automatic hook-trust bypass; use the existing authorized permission configuration explicitly. Normal persisted hook trust is preferred; a selected automation option may enable the documented hook-trust bypass for already reviewed hook sources, with the chosen policy recorded. This is configuration, not a new approval ritual for already authorized work. Runner acceptance checks remain mandatory even when the CLI skips untrusted hooks. Do not claim hook execution merely because a hooks file exists.

`--dry-run` validates the entire plan, paths, roles, command catalogue and timeout settings, and prints resolved models/checks/ownership. It starts no Codex subprocess, runs no checks, changes no branch/index, and writes no state. It needs no model account or license. A normal execution starts only pending steps of a new run; existing incomplete state requires `--resume`.

## 4. Changes required in the reference runner

| Reference behavior | CMIG implementation requirement |
| --- | --- |
| Useful sequential steps, stdin prompts, prior summaries, retry feedback | Reuse; include only verified previous summaries and declared input documents |
| `CODEX_MODEL = gpt-6-astra` for all work | Fixed role routing above; Sol writes implementations |
| `_load_guardrails()` injects every top-level `docs/*.md` | Replace with explicit `read_files`; do not flood prompts with the large user guide or obsolete history |
| Agent edits `index.json` to declare itself complete | Phase spec stays immutable during execution; runner alone writes `.run` state after independent checks |
| `completed` is accepted even after nonzero Codex exit | Require zero subprocess exit, valid final JSON, valid role result, scope integrity, and all required checks passing |
| No pending steps means “all completed”; blocker scan examines only a suffix | Validate every step and transition; `error`, `blocked`, unknown or interrupted states can never produce phase success |
| Automatic `feat-...` checkout and `git add -A`; even failed work is committed | Current branch/no commit by default; scoped opt-in commits only after successful validation |
| Three attempts plus agent's own instruction to retry three times | One authority for attempt count; default one, explicit maximum three total attempts per step |
| Single overwritten `stepN-output.json` | Preserve every attempt, command/check result and summary; no raw logs committed by default |
| Plain JSON writes, no lock/schema/path validation | Atomic temp-file replacement, exclusive writer lock, schema checks, contained paths, immutable spec fingerprint |
| Subprocess timeout handles only direct child, text/bytes ambiguity | Terminate the process group/tree created for the attempt, drain output, normalize bytes, record timeout/cancellation |
| Progress elapsed sampled inside the context before it is finalized | Read elapsed after leaving the context; monotonic duration, UTC timestamps |

Keep this stdlib-first: JSON, dataclasses, pathlib, subprocess, and small validation helpers suffice. Do not introduce another orchestration engine, database, web service, or mandatory schema dependency.

### Completion, state, and retries

State transitions: `pending → running → completed | error | blocked`; interrupted `running` is never inferred complete. A phase completes only when every step is completed and its final Astra review verdict is `pass`. Review findings are a successfully produced artifact but `changes_requested` leaves the phase incomplete; send implementation changes back to Sol. No automatic review/fix recursion. Authoring a plan-only artifact can be reported separately; it does not imply the implementation phase completed.

Final JSON contains `status` (`completed`, `error`, `blocked`), nonempty `summary`, and relevant `error_message`/`blocked_reason`; plan/review also return `report_markdown`, review returns `verdict`. The child's `completed` means proposed completion. Checks in the Markdown are explanatory; the executable acceptance definition is the validated JSON plan. Capture that definition before launching the child so edited tests/specs cannot silently change the acceptance command set mid-attempt.

Runner records at least schema version, phase/step/attempt, start/end, parent HEAD and branch, dirty-path baseline, phase/prompt/check-catalogue hashes, model/effort, CLI/Python version, argv, exit code, timeout/cancel flag, check statuses and report/log paths. Never dump all environment variables, authentication data, or Gurobi secret values. Raw logs can still contain sensitive project content; keep them local and ignored.

Default Codex deadline is 1,800 seconds per attempt; accept explicit positive overrides up to 7,200 seconds. Each check has its own deadline and the step has a bounded overall budget derived from declared attempts and checks. Timeout, cancellation, unavailable model/auth/tool/license, malformed state, or scope violation stop immediately with no automatic retry. A configured correction retry is for ordinary implementation/test failure, retains all edits/logs, and receives the previous failure. Do not reset/stash between attempts. Exit 0 = validated completion; 1 = execution/check failure; 2 = invalid request or unresolved prerequisite; 130 = cancellation. Persist a more specific machine status/reason regardless of exit code.

Reject a second writer via a lock containing phase/run identity and PID. Do not delete an apparently stale lock automatically. Resume requires the same phase fingerprint, branch/HEAD and compatible captured file state; changed inputs require an explicit new run or diagnosed recovery, not silent adoption. Revalidate already completed steps' evidence if relevant files changed. Unknown status, duplicate step number/name, empty required AC, missing step file, absolute/traversal path, symlink escape, and nonpositive/boolean timeout are invalid before any mutation.

Set a child-only recursion marker such as `CMIG_HARNESS_DEPTH=1`; nested live `execute.py` invocation rejects immediately. Dry-run and tests do not launch real models. Neither hook may start Codex, Claude, the phase runner, or an Orca worker. The runner is a local sequential process tool; Orca dispatch/lifecycle remains coordinator-owned. Children must not inherit authority to send duplicate `worker_done` for the parent dispatch.

### Preserving user edits

At execution start inspect staged, unstaged and untracked paths, including rename source/destination. Record their content/index state. Allow unrelated dirty paths in default current-branch mode, but reject overlap with the implementation's declared write paths before launching. Pass protected paths to the child and compare them after each attempt; an unexpected mutation is an error and retained for review, never automatically reverted. This is a collaboration guard, not a security sandbox.

Optional `--branch` creates a new branch only from a clean worktree; reject an existing target name instead of switching to it. In Orca-managed worktrees, default to the coordinator-provided checkout and use Orca for any needed placement. Optional `--commit` requires a clean initial index/worktree, stages only the validated changed paths inside this task's scope, checks the staged path set immediately before committing, and treats commit failure as failure. Never use blanket staging, automatic stashing, reset/clean, force push, or change an existing user's staged selection. Do not implement `--push` in the first CMIG version; publishing remains an explicit coordinator/user action.

## 5. CMIG validation tiers and honest coverage

`scripts/harness_checks.py` owns command IDs, prerequisites and deadlines. The runner and hook call the same implementation; avoid a second hard-coded test list in hook code. Results distinguish `passed`, `failed`, `blocked`, and `partial`, with exact argv, return code, elapsed, collected/executed/skipped counts and reasons. Missing command or dependency is a prerequisite failure, not a pass. Pytest exit 5 is always failure. A zero-exit run with no executed tests or unexpected skips cannot satisfy required coverage. Parse structured JUnit rather than green text; retain skips/xfails separately. Expand tier dependencies and deduplicate commands; reuse matching successful evidence for an unchanged tree/check catalogue/environment instead of rerunning identical gates merely because the next role is review.

| Tier | Executed checks | Environment and completion meaning |
| --- | --- | --- |
| `smoke` | Ruff over repository; the three new harness test modules | Dev Python only; mocked Codex, no engine/license/Qt/network. Suitable for Stop feedback |
| `quality` | Smoke; `uv lock --check`; release version script; strict mypy over `cmig`; envelope verify; current CI license-free test selection below | Explicitly sync `engine`, `render`, `stats` first, matching CI. Engine packages installed does not imply licensed solving |
| `solver` | `cmig golden verify`; fresh `tests/test_engine_golden.py`, `tests/test_search_policy_v2.py`, `tests/test_search_service.py` | Real MICOM/Gurobi/OSQP stack, usable license and tracked microbial models. Fresh solves are required |
| `gui` | `tests/test_app_shell.py`, `tests/test_gui_round5_p2.py`, `tests/test_gui_launcher.py` | Quality dependencies plus Qt, offscreen; these are interaction regressions, not visual usability approval or proof of a usable solver |
| `full` | Quality, golden verify, entire `pytest` suite, publication smoke as in CI | All extras, usable solver and external fixtures for claimed scope; preserve exact missing-fixture reasons |

For harness-only completion require `quality`, plus package build/audit because `scripts/` and `tests/` are distribution inputs. No solver/GUI pass is needed to prove a mocked runner works. A future search/science fix requires relevant solver checks; GUI fixes require relevant offscreen checks and visual evidence. The comprehensive audit still needs real UI walkthroughs and study-appropriate scientific scenarios.

Use the same 13 existing license-free selections as CI:

```text
tests/test_sign.py tests/test_namespace_gate.py tests/test_run_hash.py
tests/test_stats.py tests/test_model_quality.py tests/test_workflow_manifest.py
tests/test_workflow_envelope_golden.py tests/test_search_ga.py
tests/test_search_execution.py tests/test_search_benchmark.py
tests/test_search_product_ga_scaling.py tests/test_cli_search_ga_config.py
tests/test_run_transaction.py
```

New harness tests belong in `tests/`, because `pyproject.toml` only discovers that directory by default; the reference's `scripts/test_execute.py` location would be missed. Add the three files to the CI quality selection without deleting existing commands or weakening strict mypy/release/envelope gates. Initial timeout ceilings: smoke 75 seconds total (Ruff 30, harness tests 40, cleanup margin 5), quality 900 seconds, solver/gui 1,800 seconds each, full 2,700 seconds. Log a timeout as failure; tune documented ceilings from actual CI evidence instead of adding hidden retries. The full tier ceiling follows the current solver CI job ceiling, not an expectation that it always takes that long.

Important observed limitations:

- `cmig/core/solver.py:GurobiBackend.capability` uses module importability. `cmig solvers` does **not** establish a working license. A bounded actual Gurobi environment/optimization preflight and the fresh solver tests do.
- `cmig/golden_fixture.py:verify_golden_versions` explicitly performs **no re-solve**: `cmig golden verify` compares installed MICOM and recorded run hashes. It remains required, but cannot replace `tests/test_engine_golden.py`.
- `tests/test_engine_golden.py` skips on absent MICOM. Many GUI tests use `importorskip`. Detect this as missing requested coverage, not scientific success.
- `tests/_gem_fixtures.py` requires tracked microbial GEMs, while absent external human GEMs may skip. A full run with such skips is `partial`; list the excluded node IDs/reasons and do not claim a complete host/publication audit. Explicitly scoped optional skips may be reported, never hidden. Mandatory tier completion still requires its declared coverage.
- A synthetic oracle or mocked engine tests algorithm/control behavior, not real metabolic accuracy or GEM throughput. The existing September benchmark report makes this distinction correctly.
- Do not auto-recapture golden files, relax tolerances, add blanket skips, use `--allow-failed` to pass an AC, switch to OSQP while claiming Gurobi full flux, or install/fetch prerequisites inside a Stop hook.

Publication validation stays an explicit, separately scoped procedure in `docs/PUBLICATION_VALIDATION.md`, with actual model paths and biomass/medium provenance. Its placeholders and network acquisition commands are not default hook/runner checks.

## 6. Hooks without runaway work

Adapt the reference's common Python hooks for Codex and Claude. Hook configuration must locate the repository reliably from non-root working directories and quote paths with spaces. Resolve project Python on POSIX and Windows (`.venv/bin/python`, `.venv/Scripts/python.exe`), falling back only with an explicit missing-environment diagnostic if required tools are unavailable. Do not accidentally use a globally installed pytest against the wrong environment.

PreToolUse has a 10-second outer limit and no subprocess requirement. Accept JSON payload variants with `command` or `cmd`, including argv lists; confirm actual shell tool names for the installed clients rather than assuming the reference's `^Bash$` covers every Codex tool. Preserve guardrails against destructive resets/cleans, force pushes and recursive forced deletion; test common flag-order variants and case handling. Do not echo secrets or whole suspect commands. This is an accident guard, not a shell parser or a security guarantee, and ordinary safe cleanup must remain possible.

Stop calls only `smoke`, with subprocess deadlines above and outer hook timeout 90 seconds. First failure emits a short JSON block reason with command/check identity and bounded output. If `stop_hook_active` is already true, return promptly without starting checks or blocking again. Also use a reentrancy marker for subprocess-based hook tests. A continuation is feedback, never proof of passing: the phase runner independently enforces AC after Codex exits. Both hooks handle malformed JSON and wrong payload types deterministically; missing checks/timeouts are reported rather than throwing an uncaught traceback.

Unit tests invoke Stop with injected/mock checks or a harmless temporary command, never the real smoke catalogue while already running the smoke tests. No hook test may recursively run itself. On timeout/cancellation, terminate only the subprocess group/tree created for that check, including descendants; never kill unrelated Python/Codex processes. Do not leave a pytest/solver process alive after the parent hook is killed. Windows cleanup needs an explicit implementation and mocked/platform tests, rather than POSIX-only assumptions.

## 7. Canonical AGENTS rules and phase authoring

`AGENTS.md` is the only development-rule source. `CLAUDE.md` contains a short explanation and `@AGENTS.md`, with no duplicated rule list. Distinguish the existing metabolic-analysis consumer skill from development instructions; retain it unchanged.

Canonical rules must explain the actual code layout: `cmig/core` contains headless scientific algorithms **and** engine/solver adapters; `service` coordinates jobs/use cases; `io` handles source/provenance/atomic outputs; `cli` and `gui` present those workflows; `render`/`render_r` produce figures. Preserve lazy optional imports and responsive GUI jobs. Do not copy the archived claim that all core modules are free of MICOM/COBRA/Arrow imports, or demand a wholesale relocation in this task. Record a true architecture mismatch for later review.

Include these CMIG invariants, with links to current contract/tests:

1. Delegate community construction/cooperative tradeoff through the MICOM integration, use supported APIs, and retain the exact MICOM pin. Flag undocumented/internal coupling for review; never silently change scientific semantics to satisfy a check.
2. Preserve namespace gates, exchange sign (`+` secretion / `−` uptake), member versus environment flux bases, explicit medium merge/replace behavior, and all-boundary uptake isolation. Do not turn unmatched inputs into silent defaults.
3. Preserve requested/effective membership, finite positive abundances, community/member growth floors, actual joint feasible target vectors, fixed normalization where required, and recorded GA seed/budget/policy. Exact membership count does not establish ecological participation or optimality.
4. Failed/non-viable/unevaluable/cancelled results stay distinguishable from valid zero and from successful runs; never rank them as best. Preserve failure ledger, warnings, exit semantics, and scientific-versus-artifact success.
5. Preserve run hashes, dependency/model/medium provenance, result digests, atomic publication and checkpoint compatibility. Pickle is prohibited. Preview work remains ephemeral until Apply/Save; never modify source GEMs or publish scratch data.
6. Keep Gurobi full-flux versus OSQP approximate labels, host objective/biomass/isolation meaning, dFBA interpretability and statistical independence caveats explicit. Do not manufacture publication validity from unit-test success.
7. Use current Ruff/strict mypy/release/golden/CI commands and meaningful regression tests for behavior. Do not import the reference's blanket TDD demand for every documentation change or its kinase-specific schemas, knowledge-base directories, extraction rules, or one-engine-versus-domain-step restriction.
8. Astra owns plans/reviews, Sol implementations; steps declare file scope, read list, measurable AC, deadlines and report ownership. Preserve user edits and scope; no default commit/push. Existing user authorization is sufficient for preparing and implementing the agreed harness.

Source precedence: explicit user instruction first; root specification and accepted decisions define intended scientific contracts; current user docs/code/tests/CI describe what is presently implemented. Archived PDCA plans and historical review reports are supporting context. When these disagree, describe the mismatch with evidence; do not declare either all historical rules binding or all existing code scientifically correct.

### Phase template

`phases/index.json` starts as `{"phases": []}` and is a source-controlled catalogue, not the runtime status database. The template is a source example and cannot execute directly from `phases/templates/`. A real phase has `index.json` plus numbered `stepN.md` files. Example shape (adapt paths/AC for the actual task):

```json
{
  "schema_version": 1,
  "project": "CMIG",
  "phase": "example-change",
  "steps": [
    {
      "step": 0,
      "name": "implement-change",
      "role": "implement",
      "read_files": ["AGENTS.md", "docs/HARNESS.md"],
      "write_paths": ["scripts/execute.py", "tests/test_harness_execute.py"],
      "checks": ["quality"],
      "timeout_s": 1800,
      "max_attempts": 1
    },
    {
      "step": 1,
      "name": "review-change",
      "role": "review",
      "read_files": ["AGENTS.md", "REVIEW/harness_design_2026-09-25.md"],
      "write_paths": [],
      "report_path": "REVIEW/example-change-review.md",
      "checks": ["quality"],
      "timeout_s": 1800,
      "max_attempts": 1
    }
  ]
}
```

Check identifiers resolve to the executable catalogue. Additional task-specific checks, when needed, use validated argv arrays plus explicit deadline/prerequisites/coverage expectation; never parse shell code out of Markdown. Do not make broad directory globs the default ownership mechanism. Report paths are declared runner writes, collision-checked just like implementation paths; review agents themselves remain read-only.

Each `stepN.md` contains: objective and role; exact files to read; owned paths and non-goals; expected interface/behavior and scientific invariants; exact AC commands corresponding to JSON check IDs; evidence/report requirements; and concrete stop conditions. Include enough context for a fresh session. The Claude `/harness` template creates concrete plans within existing authorization, calls out only genuinely unresolved choices, and never makes fresh approval a ritual prerequisite. `/review` requires Astra, evidence-linked findings and unresolved coverage, and does not self-implement fixes.

Suggested implementation order for Sol: (1) canonical rules/templates and check catalogue; (2) runner state/model/scope/process behavior and tests; (3) hook wiring, ignores, CI selection and guide. Then Astra reviews the complete diff and test evidence before the broader product audit. Do not launch this bootstrap through itself from a dispatched worker; test it with mocks and disposable fixtures.

## 8. Executable acceptance for the harness deliverable

After Sol installs the files, these are required checks from repository root. Synchronization is an explicit one-time setup command, not hidden in verification:

```bash
uv sync --extra engine --extra render --extra stats
uv run --no-sync python scripts/execute.py --help
uv run --no-sync python scripts/harness_checks.py --tier quality
uv build
uv run --no-sync python scripts/audit_distribution.py dist/*
git diff --check
```

The following behaviors must be asserted using temporary repositories, mocked Codex/processes and fake command results; no real Codex billing, solver, GUI, network or changes to the developer's branch are needed:

- Default argv pins Sol; plan/review pin Astra with read-only access. Unsupported role/model/CLI, missing response and nonzero process exit cannot complete a step. AGENTS discovery is retained; dangerous bypass flags are absent by default.
- Dry-run has no mutation/process side effects. Completed summary plus failed AC, pytest exit 5, all-skipped tests, missing tool/license, malformed JUnit or timed-out check all prevent success. Actual check logs/counts survive.
- An error before a later completed step, unknown status, interrupted running state or an empty/malformed phase cannot report “all complete.” A review requesting changes keeps the phase incomplete.
- Resume rejects changed phase/check definitions and incompatible state. Concurrent writers are rejected. Atomic-write failure leaves previous state readable. Distinct attempts retain distinct output.
- Default never checks out/stages/commits/pushes. Staged and unstaged user files survive byte-for-byte and index-for-index; overlap is rejected. Opt-in commit includes only allowed changed files and never captures unrelated staged content. Out-of-scope changes are diagnosed without destructive recovery.
- Timeout and Ctrl-C clean up child descendants, preserve partial output (including byte-valued `TimeoutExpired` output), and never auto-retry. Configured correction attempts cannot exceed their bound. Nested live runner and recursive hook/test invocation terminate promptly.
- Both clients' hook JSON loads; shared commands resolve with spaces/non-root cwd; first Stop failure blocks once, reentrant Stop returns immediately; absent/malformed tools/payloads have bounded diagnostics. Timeouts and command-name variants are tested.
- The shared Claude files are trackable, local private settings stay ignored, `CLAUDE.md` imports the canonical file, no `AGENTS.ms` appears, existing analysis skill and unrelated scripts remain unchanged. New tests are explicitly in license-free CI.

Do not introduce live model smoke calls merely to test argv construction. Report “mocked runner contract verified” separately from a later real model invocation. This design report itself changes documentation only; the above are acceptance requirements for Sol, not claims of checks already run.

## 9. Priority areas for the subsequent whole-codebase audit

These are investigation priorities, not fresh confirmed product defects. September's report says the earlier F1–F9 issues were addressed, and current code/tests contain the corresponding guards. Reproduce against the final commit before opening fixes.

| Priority | Current paths / evidence | Audit question and required evidence |
| --- | --- | --- |
| P0 scientific correctness | `core/search.py`, `search_multi.py`, `search_constraints.py`, `search_product.py`; `test_search_policy_v2.py` | Do exact-k and effective membership agree across single/joint/Pareto paths, with finite abundance and growth measured at the target optimum? Test boundary abundances, non-viability, direction domains, fixed/observed normalization, and real joint LP feasibility |
| P0 search completeness/honesty | `search_ga.py`, `search_execution.py`, `search_validation.py`, `service/search_service.py`; GA/checkpoint/partition tests | Are all failures visible, unique-consortium budgets accurate, equal-fitness selection unbiased, resume/parallel results equivalent, and Pareto archives independent of top-k? Preserve donors in synergy cases; local abundance/leave-one-out sensitivity is not causal attribution |
| P0 scientific environment | `medium_spec.py`, `boundary.py`, `host*.py`, `dfba*.py`; strict-medium/isolation tests | Do all entry points apply the same explicit medium and boundary basis; do host/dFBA failures remain invalid results rather than attractive numbers? Re-run study inputs with recorded units, objectives and actual licenses |
| P1 GUI parity and comprehension | `gui/builder.py:SearchView`, `gui/app.py`, `gui/views.py`, `gui/host_view.py`; app-shell/round-5 GUI tests | September controls now exist. Check actual wiring, English/Korean coverage, dense rows at supported window sizes, progressive disclosure, multi-target directions/scales, run invalidation, cancellation latency, disabled states and error recovery using screenshots and real interaction |
| P1 GUI workflow gaps | `SearchView.REQUEST_FIELDS`, strain-growth / abundance-impact / gene-KO actions | Search and adjacent workflows snapshot different controls. Trace whether medium/growth/target settings apply consistently or their differing scope is clearly presented; do not assume every visible input affects every action |
| P1 reproducibility / publication | `io/run_transaction.py`, `core/workflow_manifest.py`, `cli/main.py`, renderer/provenance; envelope/digest/transaction tests | Audit every advertised workflow's input identity, atomic outputs, manifest status and `inspect-run` behavior, including cancellation and export after stale/failed runs |
| P2 architecture / docs | large `cli/main.py` and GUI adapters, archived designs versus accepted decisions | Record actual layer coupling and public API assumptions; identify stale claims without “fixing” science to match a draft. Separate current features, limitations and roadmap |

For the later audit, inventory all advertised workflows and map each to core/service/CLI/GUI, tests and evidence tier. Findings should include severity, exact trigger, expected versus observed result, file/line, reproducible command/test, and whether evidence is static, mocked, licensed solver, or visual. Hand implementation fixes to Sol, then have Astra verify them. Old pass counts, screenshots and numerical values are historical evidence and must not be presented as validation of the new commit.
