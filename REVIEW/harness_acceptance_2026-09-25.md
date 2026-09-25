# CMIG harness acceptance — 2026-09-25

Review owner: GPT-6 Astra. Implementation owner: GPT-6 Sol. **Final verdict: pass.**

All four residuals from `REVIEW/harness_rereview_2026-09-25.md` are resolved in the final code. Independent fresh-repository probes and all 56 harness tests pass; no material residual was found within the authorized accident-guard scope. This approves the bounded harness corrections, not product publication validity or a green whole-product suite.

## Finding dispositions

| Previous finding | Final disposition and evidence |
| --- | --- |
| R1 / H3 — tier expiry retries | **Resolved.** Between-check expiry carries `timed_out: true`; the runner persists terminal timeout evidence and exits 1/error after one implementation attempt, despite two allowed attempts. Ordinary failed-check correction retries still pass their regression. |
| R2 / H4 — model termination leaves Stop's pytest alive | **Resolved on tested macOS/POSIX.** Bounded SIGTERM grace lets Stop clean its separately grouped check before forced cleanup. Real deadline and Ctrl-C probes leave Codex, Stop, pytest and a normal pytest child process absent, with one attempt and the correct terminal cause. |
| R3 / H5 — legitimate planned edit breaks untouched resume | **Resolved.** Ordered ownership evidence accepts the tracked-file plan/read → implementation/edit → review sequence and unchanged resume. Stale planner evidence, final-output tampering and changed unowned input still reject. |
| R4 / H5–H6 — null attempt crashes validation | **Resolved.** Null/string attempts, null/string check entries and null response reject with bounded exit-2 diagnostics, no traceback, no model/check invocation and byte-identical input state. |

The prior re-review's resolved H1/H2/H7/H8/H9 dispositions stand. Final focused regressions retain Git/scope protection, dirty/index preservation, path-alias rejection, nonpassing-review publication, sequential context and recursion-marker guards. H6's phase-mutation diagnostic regression also passes. The original 13-scenario CLI matrix was already independently reproduced in the prior re-review and was not needlessly repeated here.

## Independent execution

Disposable evidence directory (all paths below are relative to it):

```text
/private/var/folders/ms/sx754_r951x77jlgckb9vyx00000gn/T/cmig-harness-acceptance-o7sxp60s/
```

Copied `probe.py` and `probe_corrections.py` from the preserved Astra re-review directory and ran the correction probe unchanged against fresh Git fixtures containing the final runner/check/hooks. Added `probe_acceptance.py` for explicit call counts, stale/malformed evidence and both nested interruption paths. `probe_tier_acceptance.py` adapts the original controlled-clock reproduction to assert the corrected terminal result. Model behavior is a PATH-selected fake Codex executable; Stop, pytest, process signals and the acceptance executor are real. Fixture Git commits occur only in disposable repositories.

| Execution | Exact result |
| --- | --- |
| `uv run --no-sync python <evidence>/probe_corrections.py` | Exit 0. Fresh future-output context and unchanged resume pass; tracked-edit run and resume both exit 0; null attempt exits 2 with `harness: malformed completed-step attempt evidence`; actual three-second model timeout exits 1/error in **3.533 s**, one attempt, pytest reached and did not survive. `correction-results.json`, `corrections.log`. |
| `uv run --no-sync python <evidence>/probe_tier_acceptance.py` | Exit 0. Actual `run_checks` expiry result fed through the runner: phase exit **1/error**, **one model call / one implementation attempt**, attempt `timed_out: true`, diagnostic `check harness-tests: tier deadline exceeded`. `tier-deadline-result.json`. This is a controlled-clock probe, not an elapsed 75-second tier run. |
| `uv run --no-sync python <evidence>/probe_acceptance.py` — ordinary resume | Exit 0. Plan reads committed `out.txt`, Sol edits its owned file, Astra reviews; untouched resume exits **0**. Counters remain **three model calls / two real acceptance-check calls** across resume; the initial review can reuse the unchanged-tree check cache. |
| Same probe — stale/malformed evidence | Eight cases each exit **2**, with no traceback, no additional model/check calls and unchanged state bytes: stale planner read, null attempt, string attempt, null check entry, string check entry, null response, tampered final output, changed unowned input. `acceptance-results.json`. |
| Same probe — nested model deadline | Actual four-second deadline: **1/error**, **4.563 s**, one attempt, `timed_out: true`, `cancelled: false`. Codex/Stop/pytest/helper PIDs **40443/40444/40446/40449** all absent before fixture cleanup. |
| Same probe — nested Ctrl-C | SIGINT after real pytest starts: **130/cancelled**, **1.078 s** total, one attempt, `cancelled: true`, `timed_out: false`. Codex/Stop/pytest/helper PIDs **40500/40501/40503/40504** all absent before fixture cleanup. Both nested cases record pytest inheriting `CMIG_HARNESS_DEPTH=1` and `CMIG_STOP_HOOK_ACTIVE=1`; a later PID recheck confirms all eight processes remain absent. |
| `uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_checks.py tests/test_harness_hooks.py --junitxml=<evidence>/focused.xml` | Exit **0**, **56 passed, zero failures/errors/skips**, JUnit duration **39.794 s**. Includes ordinary retry, both real nested termination paths, parent-exits-first pipe cleanup, direct SIGTERM cleanup, cancellation, scope, resume and mocked Windows fallback regressions. `focused.log`, `focused.xml`. |
| `git diff --check` | Passed. |

## Source and reused quality evidence

Inspected the final ownership/evidence validation, timeout propagation, process termination and Stop code, plus the relevant regressions; compared runner/check source against the prior re-review copies. The changes are bounded to those corrections and the harness-test check allowance from 40 to 65 seconds within the unchanged 75-second smoke tier.

Current runner/check/hook SHA-256 hashes match Sol's final fresh-probe copies in `cmig-residual-final-44_v6cnv/future-live/`; exact hashes are in `verified-source-hashes.json`. Runner hash begins `eec52915900e`, check hash `d35211d93c4f`. Repository-file hashes captured in `review-start.json` remain unchanged throughout this review except for this newly added acceptance report. No implementation/product edits, branch change, repository commit or push were made.

Independently read the archived Sol dispatch `ctx_fd66f1742851` using `orca orchestration worker-read --dispatch ctx_fd66f1742851 --limit 70 --json`; saved the receipt as `sol-final-transcript.json`. The final-code quality command, timestamp **1790300486498**, is `uv run --no-sync python scripts/harness_checks.py --tier quality`. Session **71483** completes in tool receipt **ctco_01a0d63b-1158-75d1-94de-53ec5204210a**, timestamp **1790300590424**, with **exit 0** and Ruff, harness tests, lock, release versions, `mypy cmig`, envelope and CI selection all passed. This verifies the final implementation report's quality result without duplicating unaffected product or package checks.

## Material limits

Native Windows process-tree behavior remains **unverified**; its fallback tests are mocked. No live model/authentication/hook-trust run, licensed solver/publication study or GUI validation was performed. The harness provides documented accident guards, not adversarial sandbox isolation; `user-configured` remains a requested implementation sandbox label rather than proof of effective configuration.

The independently read pre-correction whole-suite evidence in `.run/audit-20260925/harness-full/results.json` remains **1,565 passed, one existing AGORA URL-guard failure, 18 skipped** (1,584 collected, 1,566 executed). `full-tests` is failed and publication smoke was not reached. That suite was not rerun or relabeled green; the completed product audit and its remediation remain separate.

No further bounded harness correction is required for this acceptance.
