# Independent CMIG harness review — 2026-09-25

Review owner: GPT-6 Astra. Implementation owner: GPT-6 Sol. **Verdict: changes_requested.**

The requested harness is present and its quality checks pass, but real CLI probes reproduce false completion, a protected-file overwrite, cancellation retry, stale resume acceptance, and process-lifecycle defects. Fix the bounded harness issues below with Sol, then obtain Astra re-review. Existing task authorization covers those corrections; no new user approval, product changes, branch, commit or push is requested.

## Scope and evidence

Read `AGENTS.md`, `CLAUDE.md`, the design and implementation reports, the entire new runner/check catalogue/schema, both clients' hook configurations and shared hook scripts, command templates, phase templates/catalogue, guide, three test modules, and all four tracked diffs (`.github/workflows/ci.yml`, `.gitignore`, `README.md`, `pyproject.toml`). Included untracked source files; this was not a tracked-diff-only review. Other audit reports and implementation files were not edited. This report is my only repository source change.

Integration evidence is in the disposable directory:

```text
/var/folders/ms/sx754_r951x77jlgckb9vyx00000gn/T/cmig-harness-review-_riw24ie/
```

`probe.py`, `probe_more.py`, `probe_hook.py`, and `probe_edges.py` create/use temporary Git repositories, copy the **unmodified** runner/check/hook code, and invoke `python scripts/execute.py demo` as a real process. A PATH-selected fake `codex` implements help/version, reads the real stdin prompt, records argv, and writes the actual structured final-output path. Acceptance runs the real check executor against a small executable fixture or real pytest; no runner function, state writer, Git helper, or subprocess helper is monkeypatched. `.venv` points to the synchronized CMIG environment. `results.json`, `more-results.json`, `hook-result.json`, `edge-results.json`, and each fixture's `.run/harness/demo/` retain results. The first two hook-kill attempts stopped honestly at fixture Ruff errors; the final `hook-result.json` is the successful lifecycle reproduction after correcting only temporary fixture formatting. All probe-owned surviving processes were explicitly killed.

These are control-flow/contract tests, not evidence of a live model or metabolic validity. The fake executable deliberately performs forbidden actions to test that the runner detects accidents; it is not a claim that a live model necessarily performs them.

## Required corrections

### H1 — P1: Git and scope guards accept unauthorized changes as completed

**Evidence:** `scripts/execute.py:403`, `scripts/execute.py:566`, `scripts/execute.py:595`, `scripts/execute.py:647`.

HEAD/branch are captured only before execution. The after-child guard compares dirty path sets but never verifies HEAD, branch, or the complete index. An out-of-scope file committed by the child disappears from that dirty set. The guard also runs before acceptance commands; those commands can introduce unowned changes without any final recheck.

**Observed real CLI triggers:**

- `branch`: the fake implementation runs `git checkout -qb unexpected`; runner returns **0/completed**, leaving branch `unexpected`.
- `commit`: it creates `outside.txt`, stages it and owned `out.txt`, and commits; runner returns **0/completed**, leaving unauthorized HEAD `unexpected` and the unowned file in history.
- `stage`: it stages owned `out.txt`; default runner returns **0/completed**, changing the user's index without `--commit`.
- `checkwrite`: the real acceptance fixture creates `outside-check.txt`; runner returns **0/completed**. The following read-only review simply incorporates this file into its starting dirty baseline.

**Bounded fix:** verify original HEAD/branch and index after each child and check batch, and immediately before final success/scoped commit. Detect changes outside ownership across the whole attempt, including validation commands; preserve unexpected edits for diagnosis. Apply the deliberate index/HEAD transition only inside authorized final `--commit` handling.

**Regression:** subprocess CLI fixtures for each trigger must fail and record the violation without resetting edits; normal unrelated staged/unstaged files must remain byte/index identical. The happy-path preservation probe already passes.

### H2 — P1: A path alias lets the runner overwrite a pre-existing user edit

**Evidence:** `scripts/execute.py:62`, `scripts/execute.py:180`, `scripts/execute.py:189`, `scripts/execute.py:393`, `scripts/execute.py:615`.

Path validation resolves a path but keeps raw spelling for collision/dirty comparisons. `Path('./user.txt').parts` normalizes away `.` before the attempted rejection. Thus a report path `./user.txt` does not match dirty Git path `user.txt`; the runner later writes the same physical file after scope checks.

**Observed:** fixture `report-alias` starts with `user.txt = 'precious pre-existing user edit'`, uses review `report_path: './user.txt'`, and returns **0/completed** with the user file replaced by `review findings 한글`.

**Bounded fix:** canonicalize every declared path once to a consistent repository-relative identity, or reject noncanonical spellings. Use those identities for ownership, reports, protected files and collisions; recheck the target before runner publication. Reject metadata/runtime targets that would overwrite `.git` or the runner's own state. Preserve platform case/alias behavior deliberately.

**Regression:** `./name`, repeated separators and in-repository symlink aliases cannot bypass dirty overlap/report collision checks; ordinary UTF-8 and space-containing paths remain usable. Include a Windows case-normalization test without requiring a live model.

### H3 — P1: Cancellation or timeout during acceptance can trigger a new model attempt

**Evidence:** `scripts/harness_checks.py:335`, `scripts/execute.py:602`, `scripts/execute.py:639`.

Check results retain `cancelled`/`timed_out`, but the runner treats every non-blocked check failure as retryable. Exit 130 is selected only from the earlier Codex process's cancellation flag.

**Observed:** in `cancelcheck`, a real acceptance subprocess waits; SIGINT is sent to the runner. The first check records `cancelled: true`, exit `-9`, and status `failed`. With `max_attempts: 2`, a second Codex implementation launches and the whole phase returns **0/completed**. A timed-out check follows the same branch by inspection.

**Bounded fix:** propagate any check cancellation immediately to exit 130 and a persisted cancelled reason; any check timeout stops without retry. Preserve these terminal causes if subsequent JUnit parsing also discovers skips/missing XML. In `run_check`, mixed skips currently can overwrite a prior process failure with `partial`; coverage metadata must not downgrade process failure.

**Regression:** real SIGINT during an acceptance check must leave exactly one child attempt and return 130; a bounded timeout probe must leave exactly one attempt and return failure. Retain normal correction retries for ordinary failed tests.

### H4 — P1: Descendants defeat deadlines and survive hook termination

**Evidence:** `scripts/harness_checks.py:195`, `scripts/harness_checks.py:237`, `scripts/harness_checks.py:254`, `.codex/hooks/stop.py:22`.

`_terminate` returns immediately if the process leader has exited, even when descendants still hold stdout/stderr pipes. The following unbounded `communicate()` then waits for those descendants. Each check also starts a separate session, and Stop installs no termination cleanup, so its pytest process escapes termination of the hook/ancestor group.

**Observed:**

- `orphan`: fake Codex spawns a sleeping child that inherits pipes and exits. With `timeout_s: 1`, the runner remains blocked beyond the probe's four-second watchdog. It returns only after the probe kills the exact descendant.
- Final `hook-result.json`: a real Stop smoke run reaches real pytest; SIGTERM kills Stop (exit `-15`), while pytest remains alive. The probe cleans up pytest's exact process group.

**Bounded fix:** retain process-tree identity independently of leader liveness, terminate the owned group/tree even after leader exit, and bound all output draining/cleanup. Ensure hook/runner termination owns or cleans up check descendants, including outer forced termination; do not kill unrelated processes. Provide explicit Windows cleanup tests, including taskkill errors/timeouts, rather than treating presence of `/T` as verification.

**Regression:** real parent-exits-first PIPE retention, ordinary timeout with grandchildren, SIGINT, and hook termination must finish within bounded time and leave no owned descendant. Keep Windows behavior separately identified until exercised on Windows.

### H5 — P1: Resume accepts changed inputs and incompatible completion evidence

**Evidence:** `scripts/execute.py:155`, `scripts/execute.py:211`, `scripts/execute.py:416`, `scripts/execute.py:433`, `scripts/execute.py:478`.

The phase fingerprint covers index JSON, step Markdown and catalogue values, but not declared input content. Resume validates only initial dirty files and the optional owned-output evidence. It ignores the state's schema version and top-level error status, and permits completed steps with no attempts/evidence. Completed steps skip acceptance entirely.

**Observed:**

- `resume-changed-input`: complete a phase, change its required `AGENTS.md`, then invoke `--resume`; runner returns **0/completed** without fresh Codex/check calls.
- `resume-incompatible-state`: after completion, set `schema_version` to 999, set phase status to `error`, remove step 0 evidence and empty its attempts; `--resume` still returns **0/completed** and retains schema 999.

**Bounded fix:** validate the complete state schema, phase/step identities, legal ordered transitions, required successful attempt/check/role evidence and relevant file fingerprints before trusting completed steps. Capture declared inputs and compatible post-step changes so allowed implementation edits work, while unrelated input/source/environment changes invalidate stale evidence. Reject incompatible state with an explicit diagnostic rather than silently repairing it to success.

**Regression:** both CLI cases must fail safely; unknown schemas, missing attempts/check evidence, non-prefix completed steps and changed relevant input/check definitions must never yield success. An untouched valid completed run may resume without redundant work.

### H6 — P2: A changed/malformed phase leaves an unrecorded running attempt

**Evidence:** `scripts/execute.py:532`, `scripts/execute.py:580`, `scripts/execute.py:638`, `scripts/execute.py:669`.

Revalidation raises directly before the appended attempt and diagnosed failure are persisted. The outer `finally` removes the lock but does not transition the state. This differs from a genuinely interrupted still-running process and discards useful attempt metadata.

**Observed:** `badphase` has the fake child corrupt phase JSON and return valid final JSON. The CLI exits 2 with the parsing error, but persisted phase/step status remains `running`; the recorded attempts are still empty even though final output and logs exist.

**Bounded fix:** route expected validation/I/O/state errors through a terminal-attempt recorder before releasing the lock. Preserve the cause and output paths; do not convert failure into completion or automatically retry a scope/definition change. Malformed external state should also produce bounded diagnostics instead of uncaught type/key exceptions.

**Regression:** malformed and well-formed-but-changed phase/check inputs after child execution must record an error with the completed attempt's evidence and prevent further launches.

### H7 — P2: A review requesting changes does not produce its declared report

**Evidence:** `scripts/execute.py:562`, `scripts/execute.py:611`.

Report publication is inside the no-failure success branch. A valid review with `verdict: changes_requested` correctly fails the phase but never writes `report_path`; its findings exist only inside ignored `final.json`/state.

**Observed:** `reviewfail` returns 1/error and has valid review Markdown in structured output, but `review.md` does not exist.

**Bounded fix:** safely publish valid scoped review findings to their declared artifact path even when the verdict requests changes or reports a blocker. Keep artifact success distinct from phase acceptance and preserve the nonzero phase outcome. Never publish after a scope violation to an unsafe target.

**Regression:** `changes_requested` creates the expected report and leaves the phase incomplete; passing, blocked and invalid-response cases retain their distinct semantics.

### H8 — P2: Sequential steps cannot declare newly produced inputs

**Evidence:** `scripts/execute.py:178`, `scripts/execute.py:301`, `phases/templates/step.md:3`.

Whole-phase validation requires every `read_files` entry to exist before the first step. A later implementation cannot declare its plan report, nor can a final review declare a newly created implementation file, without a fabricated pre-existing placeholder. This weakens the requested exact-read-list workflow.

**Observed:** `future-read` declares a step-0 plan output `plan.md` and includes it in step 1's `read_files`. `--dry-run` returns 2, `required file missing: plan.md`.

**Bounded fix:** permit dependencies on declared outputs of earlier steps, while rejecting forward/self references; require the file and capture its content when that dependent step starts. Make the template/guide demonstrate this usable sequence. No general DAG engine is needed.

**Regression:** a fresh plan → implement → review fixture with those explicit reads validates and runs; a missing undeclared input and a forward reference still fail before launch.

### H9 — P1: Real Stop smoke fails because its own recursion markers contaminate tests

**Evidence:** `.codex/hooks/stop.py:20`, `.codex/hooks/stop.py:22`, `scripts/execute.py:368`, `scripts/execute.py:498`, `tests/test_harness_hooks.py:48`, `tests/test_harness_execute.py:122`.

Stop sets `CMIG_STOP_HOOK_ACTIVE=1` before starting smoke; pytest inherits it. The hook test's direct `stop.decide({}, checks=fake)` therefore returns early instead of exercising its injected failure and the assertion fails. Inside an actual runner child, `CMIG_HARNESS_DEPTH=1` is also inherited, so mocked runner tests are refused as nested live runs. Ordinary standalone quality execution lacks these markers and conceals the defect.

**Observed:** launching the real repository Stop script with `{}` returns a block reason for `tests/test_harness_hooks.py::test_stop_reentrant_and_first_failure`, despite the ordinary 28-test pass. Running the same three test modules with both actual inherited markers records **16 failures / 12 passes**, including the nested-run refusals, in temporary `hook-child-tests.xml` and `hook-child-tests.log`.

**Bounded fix:** isolate injected unit-test environments locally while retaining production recursion guards. Do not globally strip the guards from arbitrary descendants or disable nested-run protection. Verify the actual Stop-to-smoke path separately from tests that could recursively run that same path.

**Regression:** ordinary smoke and smoke invoked by Stop in a runner child's environment must both pass on a clean implementation, while truly reentrant Stop and nested live runner calls still return immediately/refuse as designed. No real model call is needed.

## What passed and what remains limited

- **Exact routing and flags:** real temporary CLI runs record plan `gpt-6-astra`, implement `gpt-6-sol`, review `gpt-6-astra`, explicit medium effort, `-a never`, JSONL, schema and final-output paths. Astra roles receive `--sandbox read-only`; implementation leaves sandbox selection to user configuration unless supplied. No default sandbox/hook-trust bypass, branch creation, commit or push is in the runner argv. Local `codex --version`, `codex exec --help`, and `codex --help` confirm 0.156.1 supports the flags used. No live model/authentication/availability/trusted-hook execution was tested. The recorded sandbox string `user-configured` is not proof of an effective sandbox value or of inheritance of a parent session's CLI override; document that limit or record resolved effective settings.
- **Honest basic failures:** real CLI nonzero child, missing final response, failed acceptance, review requesting changes, all-skipped pytest, pytest exit 5/no collection, and mixed skips all produce nonzero incomplete outcomes. The real passing pytest fixture checks the UTF-8 implementation output. Failed review artifact publication still needs H7.
- **Dry run and recursion:** the real CLI dry-run prints Astra/Sol/Astra, preserves Git status and writes no `.run`; nested live execution returns 2 before subprocess/state creation. Supplied hook tests verify reentrant Stop skips checks, malformed payload handling and launcher operation from a nested directory containing spaces. The final hook lifecycle probe exposes H4 despite those passes; actual Stop smoke also exposes H9.
- **Canonical rules/configuration:** `CLAUDE.md` imports `@AGENTS.md` without duplicating development policy. No `AGENTS.ms` exists. Shared Claude settings/commands are trackable, `settings.local.json` remains ignored, and the existing consumer skill and product sources have no tracked diff. The command guard remains an accident guard rather than a shell parser/security boundary.
- **CI/packaging:** all three harness modules are added to the existing license-free matrix without removing earlier gates. The narrow sdist exclusions avoid distributing orphaned harness files and preserve existing packaged scripts/tests; this is a reasonable documented extension beyond the design's initial narrow file map. Both freshly built distributions pass the existing audit, and archive inspection finds no harness/AGENTS/Claude/phase members while retaining `scripts/check_release_versions.py` and `tests/test_sign.py`.
- **Coverage metadata:** JUnit counts and skip node identities are retained, but structured results do not preserve skip reasons or distinguish xfail from skip; raw XML remains available. The tests contain no Windows process-tree cleanup regression. This macOS review does not establish Windows runtime correctness, licensed publication validity, or visual GUI usability.
- **Template/guide limits:** source templates do not read the sibling reference at runtime. Tailor `phase`, output/report paths, exact AC and the example review input to each new task; the shipped example points at the dated installation design report. H8 is the concrete sequencing defect. Recovery currently relies on diagnosed manual state handling and must not be described as automatic restart of failed steps.

## Executed validation

Commands from this review (already synchronized environment; no `uv sync`):

```text
codex --version                                               codex-cli 0.156.1
codex exec --help / codex --help                              supported argv inspected
uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_hooks.py tests/test_harness_checks.py
                                                             PASS: 28 tests
uv run --no-sync python scripts/harness_checks.py --tier quality
                                                             PASS: Ruff, harness tests, lock, versions, mypy, envelope, CI tests
uv run --no-sync python <temporary-dir>/probe.py               completed; 13 actual runner CLI scenarios
uv run --no-sync python <temporary-dir>/probe_more.py          completed; resume/JUnit cases, initial hook fixture diagnostics
uv run --no-sync python <temporary-dir>/probe_hook.py          final reproduction: pytest survives Stop SIGTERM
uv run --no-sync python <temporary-dir>/probe_edges.py         completed; future-read, nested CLI, dry-run
Actual Stop subprocess with input {}                         BLOCKED by its own inherited-marker test failure (H9)
Three harness test modules with both inherited markers        FAIL: 16 failed / 12 passed (H9)
uv build --out-dir <temporary-dir>/dist                       PASS: wheel and sdist
uv run --no-sync python scripts/audit_distribution.py <temporary-dir>/dist/*
                                                             PASS: both artifacts
git check-ignore (shared and local Claude paths)              shared unignored; settings.local.json ignored
git diff --check                                              PASS
```

The coordinator separately ran the fresh full tier; I read `.run/audit-20260925/harness-full/results.json` and its test accounting. Ruff, 28 harness tests, lock, release versions, mypy, envelope, 259 CI-selection tests, real Gurobi optimization preflight and golden verification passed. Full pytest reports **1,584 collected; 1,565 passed; 1 failed; 18 skipped** (`executed: 1,566` includes the failed test), with the original `tests.test_agora2::test_fetch_model_refuses_a_url_outside_the_publisher` failure. `full-tests` records exit 1/status failed, the coordinator reports outer exit 1, and publication-smoke was not reached. This preserves the original baseline's **1,537 passed / 1 failure / 18 skips** plus the 28 added harness tests; it is neither a new harness regression nor a green full-suite result. Product remediation remains with its separate owner.

For the Sol correction pass, add the bounded real-process regressions above, rerun focused harness tests and quality, and recheck distribution behavior if packaging changes. No duplicate full scientific-suite run or scientific tolerance/skip changes are needed to address these runner defects.
