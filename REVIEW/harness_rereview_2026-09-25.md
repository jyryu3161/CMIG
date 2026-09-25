# CMIG harness re-review — 2026-09-25

Review owner: GPT-6 Astra. Correction owner: GPT-6 Sol. **Final verdict: changes_requested.**

The corrections resolve most original reproductions, and the 48 harness tests and quality tier pass. Four bounded residuals remain within H3–H6: a tier deadline can retry, model termination can leave a Stop check alive, legitimate planned edits invalidate untouched resume, and malformed attempt evidence raises an uncaught exception. These were reported immediately to the coordinator; Sol should correct them before final Astra approval.

## Scope and evidence

Read `AGENTS.md`, both prior harness reports, the final runner/check code, relevant hooks/tests, guide and phase templates. Compared the runner/check/hook files with the original review's preserved source copies. This report is my only repository edit; implementation, old review and product code were not changed. No live model call, whole product suite, checkout, repository commit or push was performed.

Disposable evidence directory:

```text
/var/folders/ms/sx754_r951x77jlgckb9vyx00000gn/T/cmig-harness-rereview-q16078vz/
```

`probe.py`, `probe_more.py`, `probe_hook.py` and `probe_edges.py` rerun the prior real CLI matrix against fresh copies of the current, unmodified harness. `probe_corrections.py` adds real future-context, resume, malformed-state and nested-hook cases; `probe_timeouts.py` adds actual check/model deadlines with two permitted attempts. Fake Codex is PATH-selected, records real argv/stdin, and writes the real final-response file; acceptance uses the actual check executor. Fixtures use temporary Git repositories and the synchronized CMIG Python. Only the old hook fixture needed formatting/configuration repairs to reach pytest: its first attempts honestly stopped at Ruff, then its corrected real lifecycle probe ran. Source hashes in `review-start.json` remained unchanged throughout review.

`probe_tier_deadline.py` is explicitly a controlled-clock/test-fixture probe, not a real elapsed 75-second tier: it obtains the actual `run_checks` expiry result and feeds it through the existing runner fixture. Its first interactive setup used the macOS `/var` alias and was rejected by canonical-path validation; the canonical `/private/var` run and saved script reproduce the issue. No bypass of production path validation was made.

## Original finding dispositions

| Finding | Disposition | Re-review evidence |
| --- | --- | --- |
| H1 — Git/scope protection | **Resolved** | Real branch, commit, stage and acceptance-write cases now exit 1/error with one recorded attempt and preserve offending changes for diagnosis. Happy Astra/Sol/Astra run completes while preserving unrelated staged diff and unstaged bytes. Tracked owned edits and benign index refresh regressions pass. |
| H2 — Report aliases | **Resolved** | Original `./user.txt` case exits 2 before launch and preserves the precious edit. Regressions cover repeated separators, symlink/case aliases, `.git`/`.run` targets, Windows-normalized identity and Unicode/space paths. |
| H3 — Cancellation/timeout precedence | **Partially resolved; R1 below** | Actual SIGINT during acceptance exits 130/cancelled after one attempt; actual 30-second check timeout and model timeout exit 1/error after one attempt despite `max_attempts: 2`. JUnit skips no longer downgrade process failure, and missing XML retains the process cause. Between-check tier expiry still retries. |
| H4 — Process lifecycle | **Partially resolved; R2 below** | Parent-exits-first pipe retention is now bounded; direct SIGTERM of real Stop terminates its pytest child. Windows taskkill error/timeout fallback unit tests pass. A model timeout while its Stop hook is checking still leaks pytest. |
| H5 — Resume compatibility | **Partially resolved; R3/R4 below** | Original changed-input and incompatible-state CLI cases now reject resume; schema, missing checks/attempts, non-prefix state and runtime-environment regressions pass. Fresh-output plan → implement → review completes and unchanged resume makes no extra model invocation. Normal planning of an existing file subsequently edited by implementation is falsely rejected on untouched resume. |
| H6 — Diagnostic state | **Original phase-mutation case resolved; R4 remains** | Malformed phase after child completion now exits 1/error with that attempt, final response and log paths persisted; well-formed phase-change regression also passes. Malformed external attempt evidence still produces an uncaught `AttributeError`. |
| H7 — Nonpassing review artifacts | **Resolved** | Original `changes_requested` CLI case writes `review.md` and keeps exit 1/error. Passing, blocked-verdict and blocked-response publication regressions pass. Scope violations prevent unsafe publication. |
| H8 — Sequential inputs | **Resolved** | Missing future outputs validate when owned by an earlier step. Real fresh plan → implement → review delivers plan Markdown in Sol's stdin and implementation content in Astra's stdin; no placeholders required. Missing/forward input regression rejects launch. |
| H9 — Stop recursion-marker contamination | **Resolved** | Actual `CMIG_HARNESS_DEPTH=1` Stop smoke exits 0 with no block output. Its pytest descendants inherit both production markers; local test isolation preserves reentrant Stop and nested-live-run protections. |

## Remaining bounded corrections

### R1 — P1: Between-check tier expiry permits another model attempt (H3)

`scripts/harness_checks.py:464` emits `status: failed, reason: tier deadline exceeded` without `timed_out`. `scripts/execute.py:806` only stops retrying for blocked/cancelled/timed-out check results. The coordinator identified this edge; independent controlled-clock reproduction confirms it.

With smoke's clock advancing from 0 to 76 after a passed Ruff result, `run_checks` returns that unmarked expiry for `harness-tests`. The current runner fixture with two allowed attempts then launches implementation twice and returns **0/completed** after a later pass. Evidence: `probe_tier_deadline.py`, `tier-deadline-result.json` (three model calls: two implementation, one review).

**Sol fix and acceptance:** give tier exhaustion explicit timeout metadata and propagate it as terminal attempt/state evidence. The same probe must fail after exactly one implementation attempt with a timeout cause; ordinary failed-test correction retries must remain available.

### R2 — P1: Model termination leaves the active Stop check alive (H4)

`scripts/harness_checks.py:275` immediately sends SIGKILL to the model's process group. The real Stop hook in that group cannot run its new SIGTERM cleanup, and its check started a separate session at `scripts/harness_checks.py:313`.

`probe_corrections.py`, case `model-timeout-during-stop`, launches fake Codex → real `.codex/hooks/stop.py` → real pytest, then reaches the three-second model deadline. Runner returns **1/error in 3.30 seconds**, records one attempt, and kills Codex/Stop, but pytest **remains alive**. This is ordinary nested hook execution, not hostile daemonization. The probe explicitly kills the surviving owned PID; subsequent PID checks confirm all probe descendants terminated.

**Sol fix and acceptance:** allow bounded graceful cleanup of the owned hook/check tree before forced termination, retaining a bounded fallback and the parent-exits-first guarantees. Add real nested Stop regressions for both model deadline and Ctrl-C; each must terminate the owned pytest child, stop after one attempt and retain the terminal cause. Passing direct Stop SIGTERM alone does not exercise this path. No adversarial isolation or unrelated-process killing is requested.

### R3 — P2: Untouched resume rejects a normal plan/read/edit/review sequence (H5)

`scripts/execute.py:548–550` compares each completed step's read evidence with current content, exempting only that same step's writes. It does not account for a later completed implementation legitimately owning and changing a file the planner read.

`probe_corrections.py`, case `planned-tracked-edit`, starts with committed `out.txt`, lets the plan read it, lets Sol own/edit it, and lets review read the result. The phase completes successfully. Without changing any file or invocation settings, `--resume` returns **2**, `completed-step input changed: out.txt`; no new model runs. Evidence: `correction-results.json`, `planned-tracked-edit/.run/harness/demo/state.json`.

**Sol fix and acceptance:** validate ordered, authorized input/output transitions so a later completed owner's validated output can supersede an earlier read fingerprint. Preserve detection of post-run tampering and unrelated changed inputs. The exact tracked-file workflow must resume successfully without another model/check run, while modifying its final output afterward must still be rejected.

### R4 — P2: Malformed attempt evidence bypasses bounded state diagnostics (H5/H6)

`scripts/execute.py:528–533` conditionally reads fields when the last attempt is a dictionary, then unconditionally calls `good.get`. In a completed fixture, replacing `steps[0].attempts[-1]` with JSON `null` and invoking `--resume` exits **1 with an `AttributeError` traceback**, rather than the promised explicit incompatible-state diagnostic. It does not falsely complete or launch a model, but state validation is incomplete. Evidence: `probe_corrections.py`, case `malformed-attempt`, and `correction-results.json`.

**Sol fix and acceptance:** validate nested attempt/check/response shapes before dereferencing them and return `HarnessError` for malformed evidence, preserving the input state for diagnosis. Null/non-dictionary attempts and malformed check entries must reject resume without a traceback or model execution. Do not silently repair the state to success.

## Executed validation and limits

| Validation | Result |
| --- | --- |
| `uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_checks.py tests/test_harness_hooks.py` | **48 passed** |
| `uv run --no-sync python scripts/harness_checks.py --tier quality` | **Passed:** Ruff, harness tests, lock, release versions, `mypy cmig`, envelope, CI selection; `quality.log` |
| Prior real fake-Codex matrix | Original 13 CLI cases rerun; honest failures, Git/scope rejection, dirty preservation, report publication, cancellation and pipe-timeout corrections confirmed; `results.json` |
| Resume/JUnit and edge matrix | Changed inputs/schema rejected; actual all-skipped, zero-collection and mixed-skip runs remain nonpassing; actual passing pytest completes; dry-run leaves no state and preserves Git; nested live execution refused; `more-results.json`, `edge-results.json` |
| Direct Stop SIGTERM | Reached real pytest, exited within watchdog, pytest terminated; `hook-result.json` |
| `env CMIG_HARNESS_DEPTH=1 uv run --no-sync python .codex/hooks/stop.py <<<'{}'` | Exit 0, empty output; `stop-inherited.log` |
| Actual check/model timeouts, two allowed attempts | Check: 30.47 seconds, exit 1, one attempt, `timed_out: true`; model: exit 1, one attempt; `timeout-results.json` |
| Additional correction probes | Future context and unchanged fresh-output resume pass; R1–R4 reproduce as detailed above |
| `git diff --check` | Passed |

The coordinator's existing `.run/audit-20260925/harness-full/results.json` remains **1,565 passed, one known AGORA URL-guard failure, 18 skipped** (1,584 collected, 1,566 executed), from the pre-correction 28-test harness. `full-tests` is correctly failed and publication smoke was not reached. I read this evidence and did not rerun or relabel it. Product remediation stays outside this review.

Native Windows process behavior, live model/authentication/hook trust, licensed publication validity and visual GUI behavior are not established by these probes. Windows fallback coverage here is mocked. Packaging was unchanged by this correction pass, so the previous distribution evidence was not needlessly repeated. The implementation sandbox remains accurately documented as requested `user-configured`, not a verified effective setting.

Required next action: bounded Sol fixes for R1–R4, focused real-process/state regressions and quality, then final Astra re-review. No product changes or additional full-suite run are required for these harness corrections.
