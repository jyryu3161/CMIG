# CMIG harness implementation — 2026-09-25

Implementation owner: GPT-6 Sol. Design: `REVIEW/harness_design_2026-09-25.md` by GPT-6 Astra. This report covers repository harness installation only; CMIG application code and audited product defects were not changed. No branch, commit or push was made, and no live Codex model was invoked.

## Files changed

- `AGENTS.md` is the canonical CMIG development rule source, grounded in the current scientific contracts, code layout and tests. `CLAUDE.md` imports it. The existing `.claude/skills/cmig-metabolic-analysis/` was left unchanged.
- `scripts/execute.py` provides validated sequential phases, explicit `gpt-6-sol` implementation and `gpt-6-astra` plan/review, medium reasoning effort, read-only plan/review sandbox, preserved user-configured implementation sandbox, `codex -a never exec` for this dispatch, structured final JSON, process-group deadlines, bounded retries, scoped Git protection, atomic state, lock and resume checks. Defaults retain the current branch/index and make no commit/push. Optional `--branch` and `--commit` require a clean initial checkout; commit stages only owned paths. Raw per-attempt evidence is local under `.run/harness/`.
- `scripts/harness_checks.py` owns the shared smoke, quality, solver, GUI and full catalogues, prerequisites, per-check and tier limits, JUnit coverage assessment, Gurobi optimization/license preflight, process tree cleanup and check records. A passing exit without executed tests or with unexpected skips is not accepted. The runner reuses passed check evidence only for an unchanged Git tree, catalogue and selected environment identity.
- `scripts/harness_result.schema.json` defines child output. `.codex/hooks.json`, `.codex/hooks/pre_tool_use.py`, `.codex/hooks/stop.py` and `.claude/settings.json` share a bounded command guard and Stop smoke feedback. `.claude/commands/harness.md` and `review.md` explain phase and Astra review entry points.
- `phases/index.json` is an empty source catalogue; `phases/templates/phase-index.json` and `step.md` are copyable authoring examples. `docs/HARNESS.md` documents use, recovery, evidence tiers, provenance and limits.
- `tests/test_harness_execute.py`, `tests/test_harness_hooks.py`, and `tests/test_harness_checks.py` exercise mocked model/process outcomes, role argv, safe dry-run, independent acceptance, retries, timeouts, missing responses, scope and staged edits, scoped commit, lock/fingerprint behavior, check/JUnit failures, hook payloads and reentrancy. `.github/workflows/ci.yml` adds these three files to the existing license-free quality selection. `.gitignore` exposes only shared Claude settings/commands while keeping local settings ignored. `README.md` links to the source guide. `pyproject.toml` narrowly excludes repo-only harness scripts/schema/tests from sdist because the companion AGENTS, hooks and phase assets are also absent there; existing packaged scripts/tests remain.

## Provenance and launch choices

Adapted sequential steps, stdin prompts, retry feedback and common hooks from `../kbase_kinase` commit `77354f94b844a8c64e7cd47691ac20a2e96214b3`, specifically `scripts/execute.py`, `.codex/hooks.json`, `.codex/hooks/pre_tool_use.py`, `.codex/hooks/stop.py`, `.claude/settings.json`, and `.claude/commands/{harness,review}.md`. The new code has no runtime dependency on that checkout. Intentional differences include runner-owned completion, executable AC, separate scientific tiers, scope protection, no default checkout/staging/commit, no blanket sandbox or hook-trust bypass, and pytest exit 5 treated as failure.

Inspected local `codex exec --help` and global `codex --help` for 0.156.1. The runner uses stdin `-`, `--model`, `--json`, `--output-schema`, `--output-last-message`, `--enable hooks`, and `-a never`; it does not use unsupported `--full-auto`. `--sandbox read-only` is forced for plan/review; implementation defaults to the invoking user's configured sandbox. A non-default `--trusted-hooks` can bypass hook trust only when chosen for vetted automation. The runner independently checks acceptance even if hooks do not execute. Model availability/authentication is established only at a later real invocation; there is no silent fallback.

## Initial verification

Commands run from repository root with the installed environment:

```text
codex exec --help
codex --help
uv run --no-sync python scripts/execute.py --help                 PASS
uv run --no-sync python scripts/execute.py harness-validation --dry-run  PASS (temporary phase removed)
uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_hooks.py tests/test_harness_checks.py  28 passed
uv run --no-sync ruff check .                                      PASS
uv run --no-sync mypy cmig                                         PASS (89 source files)
uv run --no-sync python scripts/harness_checks.py --tier quality  PASS (Ruff, 28 harness tests, lock, versions, mypy, envelope, CI selection)
uv build                                                           PASS (wheel and sdist)
uv run --no-sync python scripts/audit_distribution.py dist/*      PASS (both artifacts)
python -m json.tool .codex/hooks.json / .claude/settings.json / scripts/harness_result.schema.json  PASS individually
git check-ignore (shared settings/commands trackable; local settings ignored) PASS
git diff --check                                                    PASS
sdist member assertion (no harness assets; existing scripts/tests retained) PASS
```

The first quality run exposed an envelope invocation mistake (`python -m cmig` has no `cmig.__main__`); the catalogue now calls the CLI entry function, and the quality tier passed afterward. The initial Ruff formatting findings were fixed before validation. The coordinator's original full-suite baseline remains **1,537 passed, one AGORA URL-guard failure, 18 skipped**; this implementation did not rerun or relabel that suite. The coordinator explicitly reserved a fresh real full-tier run for its final validation. `uv sync` was not repeated because the provided environment already had dependencies and the task required `uv run --no-sync`.

## Limits for independent Astra review

The runner uses temporary Git repositories and real fake-Codex CLI subprocesses for the scope, check, cancellation and output cases. No live Codex model, Gurobi solver tier, GUI tier or publication study was run for this harness installation. The dry-run validates catalogue IDs rather than accepting arbitrary shell commands from Markdown; a new task-specific gate needs a reviewed catalogue entry. Hook execution depends on the clients enabling and trusting the configuration; runner acceptance is independent. The command guard is a bounded accident guard, not a shell parser or security boundary. Existing product audit findings and the AGORA baseline failure belong to the separate product review/fix phase.

## Astra review corrections

The independent review in `REVIEW/harness_review_2026-09-25.md` found nine bounded harness defects. This pass corrected them without changing `cmig/` application code, scientific policy, the Astra review, or pre-existing unrelated edits.

- **H1/H2:** Each child and check batch now verifies branch, HEAD, semantic Git index entries, dirty paths and protected content. Final success rechecks the same constraints. Declared paths reject noncanonical separators, dot segments, symlink aliases, actual case aliases on case-insensitive macOS, and Git/runtime metadata targets. Output/report collisions use case-folded identities. Real CLI probes for unauthorized branch, commit, stage and check writes now fail with one recorded attempt while leaving the offending edits for diagnosis. Benign Git index stat refreshes and ordinary edits to already-tracked owned files pass.
- **H3/H4:** A cancelled acceptance check exits 130 without retry; a timed-out check also stops after one attempt. Process failures retain failed status when JUnit includes skips. Process-group termination now works after a leader exits while a descendant holds pipes, output draining is bounded, and SIGTERM to Stop cleans its active pytest child. Windows cleanup snapshots descendants for fallback when `taskkill /T` fails or times out; mocked tests cover those paths, with native Windows execution still outstanding.
- **H5/H6:** Resume checks state schema, phase/step order, successful role/check/attempt evidence, declared inputs, completed outputs, source/check code, semantic index, relevant runtime settings and unrelated new dirty paths. Stored check cache is discarded on resume. Malformed or changed phase definitions after a child finishes now leave a terminal error with that attempt's logs and final response recorded.
- **H7/H8/H9:** Valid Astra review findings publish to the declared report even for `changes_requested` or `blocked`, while the phase remains incomplete. Later steps can read earlier declared outputs; the template now demonstrates plan → implement → review. Harness tests locally isolate inherited recursion markers, and the actual Stop-to-smoke path passes with `CMIG_HARNESS_DEPTH=1`; genuine nested live runs and reentrant Stop remain guarded.

Latest correction verification from the synchronized environment:

```text
uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_checks.py tests/test_harness_hooks.py
    PASS: 48 passed
uv run --no-sync ruff check .
    PASS
uv run --no-sync python scripts/harness_checks.py --tier quality
    PASS: Ruff, 48 harness tests, lock, release versions, mypy cmig, envelope, CI selection
env CMIG_HARNESS_DEPTH=1 uv run --no-sync python .codex/hooks/stop.py <<<'{}'
    PASS: exit 0, no block output; actual Stop smoke ran under inherited runner marker
Real Stop SIGTERM probe while pytest child was active
    PASS: hook exited within 6 seconds and the owned pytest child terminated
git diff --check
    PASS
```

The coordinator's fresh pre-correction full tier remains **1,584 collected; 1,565 passed, one AGORA URL-guard failure, 18 skipped**. It was not repeated during this bounded correction pass; the AGORA product failure remains visible and unresolved here. Model availability, native Windows descendant cleanup, licensed solver behavior, publication validity and visual GUI usability remain outside this harness correction evidence. The state label `user-configured` records the requested implementation sandbox setting, not an independently resolved effective Codex sandbox.

## Final bounded H3–H5 residual corrections

The independent Astra re-review in `REVIEW/harness_rereview_2026-09-25.md` identified four remaining cases. Before editing, its copied real probes reproduced tier expiry retrying to completion, a pytest descendant surviving Codex timeout during Stop, untouched tracked-file resume rejection, and an `AttributeError` traceback for a null attempt. This pass changed only the harness runner/check code and existing harness tests; no CMIG product code, branch, commit, push, or Astra review was changed.

- **Tier deadline:** Between-check expiry now carries `timed_out: true` and becomes terminal attempt evidence. A controlled-clock check plus runner probe ends with exit 1, phase `error`, exactly one implementation attempt and one model call. Ordinary failed-check retries remain covered by the existing retry regression.
- **Nested Stop lifecycle:** POSIX model termination sends SIGTERM to the model group, drains for up to two seconds so Stop can terminate its separately grouped active check, then forces group cleanup if grace expires. The final real fake-Codex → actual Stop → actual pytest timeout probe records one attempt, exit 1, and no surviving pytest process. New real subprocess regressions cover both model deadline and Ctrl-C, including inherited `CMIG_HARNESS_DEPTH` and `CMIG_STOP_HOOK_ACTIVE` values in pytest. The earlier parent-exits-first and direct Stop termination tests still pass. The harness-test check limit is now 65 seconds within the unchanged 75-second smoke tier because the expanded real-process test suite exceeded the old 40-second limit; the inherited-marker Stop smoke then exited 0 with no block output.
- **Ordered resume:** Completed read evidence is checked against the preceding authorized owner's output (or the initial input baseline), while the current file is checked against its latest completed owner's evidence. A committed `out.txt` read by plan, edited by implementation, and read by review completes and resumes unchanged without another model invocation. Later output tampering, changed unowned inputs, and stale read evidence still reject resume.
- **Malformed state:** Null/non-dictionary attempts and malformed check entries now raise bounded `HarnessError` diagnostics before nested dereferences. The real CLI null-attempt probe exits 2 with `harness: malformed completed-step attempt evidence`, leaves the state intact, and launches no model.

Final validation on the final code:

```text
uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_checks.py tests/test_harness_hooks.py
    PASS: 56 passed
uv run --no-sync python scripts/harness_checks.py --tier quality
    PASS: Ruff, 56 harness tests, lock, release versions, mypy cmig, envelope, CI selection
env CMIG_HARNESS_DEPTH=1 uv run --no-sync python .codex/hooks/stop.py <<<'{}'
    PASS: exit 0, empty output
Final copies of Astra correction probes in /var/folders/ms/sx754_r951x77jlgckb9vyx00000gn/T/cmig-residual-final-44_v6cnv/
    PASS: tracked-edit resume 0 without extra calls; malformed attempt 2 with diagnostic; nested timeout 1, no surviving pytest
Evolved controlled-clock tier probe in /var/folders/ms/sx754_r951x77jlgckb9vyx00000gn/T/cmig-residual-after-z0qvyyym/
    PASS: one implementation attempt, one model call, terminal timeout evidence and phase error
```

Native Windows process-tree behavior remains unverified; the existing Windows fallback tests are mocked. Live model/authentication, licensed solver, GUI and publication validity were not exercised. The known AGORA full-tier product failure and its 1,565-pass baseline were not rerun for this bounded harness correction.
