# Native Windows harness CI correction — design and independent review

Status: final independent review accepted for native Windows CI. No unresolved local review findings; native Windows validation remains pending with the coordinator.

## Evidence and bounded scope

The supplied result for run `36106684677` after `387ccce` reports successful Ubuntu 3.10/3.12 and macOS 3.12 quality jobs. Windows 3.12 passes release, Ruff, mypy and envelope gates but fails exactly four parametrized unauthorized-mutation cases and the cancellation-during-check case. Every traceback stops in `real_cli_fixture` while the Korean text in generated Codex source is written with the cp1252 default. This is fixture construction failure, not evidence that production scope or cancellation handling passed on Windows.

Read set: `AGENTS.md`; `.run/remediation-20260925/windows-ci-correction/{remote-ci-failure.log,remote-ci-result.json}`; `tests/test_harness_execute.py` (especially fixture and five cases at original lines 352–459); `scripts/execute.py` (preflight, argv construction, scope checks, evidence/state and cancellation exit); `scripts/harness_checks.py` (interpreter selection, process launch, termination and check results); `tests/test_harness_checks.py`; relevant `tests/test_harness_hooks.py`; `docs/HARNESS.md`; `.github/workflows/ci.yml` for exact existing gate commands.

Immediately downstream of encoding are three actual portability problems: an extensionless shebang file is not a native Windows executable; `.venv/bin/python` is another shebang fixture, selected before the valid Windows interpreter location; and Windows `Popen.send_signal(SIGINT)` is not the POSIX cancellation interface. `run_process` creates Windows process groups but currently installs cancellation handling only for POSIX SIGTERM. Fixing encoding alone is insufficient.

## Sol ownership and implementation contract

Sol owns only `tests/test_harness_execute.py`, `tests/test_harness_checks.py`, `scripts/harness_checks.py`, and ignored `.run/remediation-20260925/harness-windows-implementation/`. `scripts/execute.py` should require no changes: retain its scope, attempts, evidence and exit-code semantics. Reviewer alone owns this report and ignored `.run/remediation-20260925/harness-windows-review/`. No workflow/environment/package/scientific changes, dependency changes, commits or pushes by Sol. Aim for a bounded 10-minute implementation/check pass, then report exact residual Windows validation needs.

1. **Explicit UTF-8 fixtures and evidence.** Write generated Python source with `encoding="utf-8"` (and LF newlines for POSIX executable sources); retain literal Korean report content. Read and write generated JSON/report artifacts explicitly as UTF-8, including inside the fake subprocess. Prefer `json.dumps(..., ensure_ascii=False)` to exercise the actual Unicode artifact boundary. Do not remove Korean, force global UTF-8 mode, or change CI locale. Add a positive real-CLI round trip of the Korean review report so an early rejection cannot hide broken artifact handling.
2. **Real executable fixtures.** Preserve POSIX executable/shebang handling there. On Windows, write UTF-8 `codex.py` plus a native `codex.cmd` launcher invoking the quoted `sys.executable` and quoted script path with `%*`; ensure `.CMD` is discoverable through the normal platform PATHEXT. Do not disguise text as `.exe`. Replace the fake interpreter with a real stdlib-created minimal virtual environment (`venv.EnvBuilder(with_pip=False, symlinks=False)`) and a fixture-local `ruff.py` (or equivalent real Python module) implementing the current pass/checkwrite/cancelcheck modes. The production check remains a real `.venv` Python `-m ruff` subprocess. Keep helper files stable before the runner baseline; suppress test-helper bytecode with fixture-scoped `PYTHONDONTWRITEBYTECODE` or ignore that cache in the fixture repository so accidental cache files do not replace the intended scope failure. No mocking of scope verification, check execution or final cancellation state.
3. **Bounded production Windows launch correction, explicitly required.** In shared `run_process`, resolve a Windows executable name through `shutil.which`/PATH/PATHEXT before Popen so normal `codex.cmd` launchers work; preserve argument-list execution, original result argv/evidence, stdin bytes, environment, process group and unavailable-command behavior. Avoid a general `shell=True` change. Respect the supplied PATH when an explicit `env` is passed. Add meaningful lookup/launch coverage; at least one native Windows real fixture must reach the fake CLI rather than merely checking string construction. Paths containing spaces must remain quoted correctly. Batch launch adds Windows shell parsing, so do not broaden this into arbitrary shell command construction.
4. **Platform-appropriate cancellation with bounded production support.** The outer real CLI test starts a Windows `CREATE_NEW_PROCESS_GROUP` and sends `CTRL_BREAK_EVENT`; POSIX still sends SIGINT. In `run_process`, temporarily map Windows `SIGBREAK` to `KeyboardInterrupt` alongside the existing POSIX SIGTERM mechanism, restore the exact prior handler in `finally`, and retain the non-main-thread behavior. The existing `KeyboardInterrupt` path must terminate the child tree, return `cancelled=True`, and leave `timed_out=False`. Native Windows Python can defer a Python signal handler during a blocking reader-thread join: if necessary use short Windows-only `communicate` polling slices against one monotonic overall deadline, passing input only on the first call. Do not increase test timeout to hide delayed handling and do not reset the check timeout on each slice. Existing POSIX communication and cleanup need not change.
5. **Preserve and strengthen the five assertions.** All four original modes still launch real subprocesses and retain their Git HEAD/branch/index or unowned-file assertions, nonzero exit, scope-violation reason, and exactly one attempt. Assert review does not run. The cancellation case retains exit 130, state `cancelled`, exactly one attempt, and no retry or review; additionally assert cancelled attempt and check evidence and that the sleeping check process exits. Use a PID marker and legitimate native liveness check where needed; a marker alone proves startup, not cleanup. No skip/xfail or substitution of timeout, failure or mocked cancellation for the Windows test.

Windows console control must not assume that pytest inherited a console from the CI service. A robust native test control is a small test-only controller process created with `CREATE_NEW_CONSOLE`; that controller starts the real runner with `CREATE_NEW_PROCESS_GROUP`, waits for check startup, and sends `CTRL_BREAK_EVENT` specifically to the runner group before collecting its result. The runner and signal sender then share a known console, while the checker remains in its own group and must be killed by harness cleanup. Keep this controller outside the repository snapshot or create it before baseline. Do not combine `CREATE_NEW_CONSOLE` and `CREATE_NEW_PROCESS_GROUP` on the same runner and assume both took effect: Windows ignores the group flag in that combination. A different equally bounded native controller is acceptable if it establishes the same console and signal-target isolation explicitly.

The launch and SIGBREAK adjustments above are narrowly scoped production behavior corrections, not merely test repairs. If real implementation reveals another required production change, report it before expanding scope.

## Executable acceptance checks

Run in the synchronized environment; do not invoke a full test suite:

```text
uv run --no-sync pytest -q tests/test_harness_execute.py tests/test_harness_checks.py tests/test_harness_hooks.py
uv run --no-sync ruff check .
uv run --no-sync mypy cmig
uv run --no-sync python scripts/check_release_versions.py
uv run --no-sync cmig golden verify-envelope
git diff --check
```

Record exact pass/skip counts and preserve existing platform-specific skips without treating skips as passes. Focused added checks must exercise executable lookup, handler restoration/cancel flags, monotonic deadline behavior if polling is added, and the real CLI Unicode report. Native Windows CI is the decisive check for PATHEXT, `.cmd`, process group event delivery, native interpreter execution, and child-tree cleanup; local macOS success is only partial evidence. The coordinator owns subsequent remote CI and Git actions.

## Platform references

Python documents Windows control events and required process-group creation in [Popen.send_signal](https://docs.python.org/3.12/library/subprocess.html#subprocess.Popen.send_signal), describes the batch-file shell boundary in [subprocess security considerations](https://docs.python.org/3.12/library/subprocess.html#security-considerations), identifies [SIGBREAK](https://docs.python.org/3.12/library/signal.html#signal.SIGBREAK), and documents [PATHEXT lookup in shutil.which](https://docs.python.org/3.12/library/shutil.html#shutil.which). These support the platform mechanism selection; they do not establish that the proposed implementation has passed Windows CI.

Microsoft specifies the shared-console prerequisite in [GenerateConsoleCtrlEvent](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent) and the ignored group flag with a new console in [process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags).

## Independent implementation review

**Verdict: accepted for the coordinator's native Windows CI run.** The final frozen implementation is confined to `scripts/harness_checks.py`, `tests/test_harness_checks.py`, and `tests/test_harness_execute.py`. This reviewer changed only this report and ignored review evidence. No production/test/environment/Git edits were made by the reviewer, and no full suite was rerun.

The implementation preserves literal Korean source, writes the generated source and final JSON in UTF-8, and checks the exact UTF-8 bytes of the published Korean report using a fixture path with spaces. The fake checker is a real venv Python module. Windows executable lookup resolves PATH/PATHEXT without globally enabling a shell; original argv evidence and unavailable-command reporting remain intact. Native interpreter ordering now prefers `.venv/Scripts/python.exe` on Windows. SIGBREAK maps to the existing cancelled-result cleanup path, restores the prior handler, and uses one monotonic deadline with single-send stdin during short communication polls. Existing POSIX process-group handling is retained.

All four unauthorized-mutation cases keep their original nonzero exit, one-attempt, scope-violation and exact Git/file negative assertions, and now also reject any review execution. The cancellation case keeps exit 130 and cancelled state, adds explicit cancelled attempt/check evidence with no timeout, and requires no retry or review plus actual checker exit. The Windows controller allocates its own console, starts the runner in a separate process group, verifies the shared console with `GetConsoleProcessList`, then sends targeted CTRL_BREAK. The check remains in its own production-created group. Native liveness queries distinguish nonexistent PIDs from access/API errors; both exceptional cleanup `taskkill` calls now have three-second timeouts. The earlier shared-console and cleanup-bound findings are resolved. No skip/xfail, global UTF-8 mode, tolerance change, or scope/cancellation weakening was introduced.

Independent checks on macOS:

| Check | Result | Review evidence |
| --- | --- | --- |
| `uv run --no-sync pytest -o addopts='' -q tests/test_harness_checks.py` | 14 passed, 0 skipped | `.run/remediation-20260925/harness-windows-review/harness-checks.log` and `.xml` |
| `uv run --no-sync pytest -o addopts='' -q tests/test_harness_execute.py -k real_cli` | 6 passed, 0 skipped, 35 deselected | `.run/remediation-20260925/harness-windows-review/real-cli.log` and `.xml` |
| Extract and compile the generated Windows controller | passed; syntax only | `.run/remediation-20260925/harness-windows-review/controller-compile.log` |
| Final frozen diff and both cleanup timeouts | inspected; `git diff --check` passed | `.run/remediation-20260925/harness-windows-review/review-result.json` records reviewed file SHA-256 digests |

Also inspected Sol's implementation and controller verification reports under `.run/remediation-20260925/harness-windows-implementation/` and `.run/remediation-20260925/harness-windows-controller/`: the three harness files pass 60 tests with zero skips on macOS; Ruff, `mypy cmig` (91 source files), release/version alignment and all 18 workflow-envelope kinds pass. The final two timeout keyword additions were inspected directly; they do not justify repeating the broader harness run.

Remaining work belongs to the coordinator: actual native Windows CI must validate `.cmd`/PATHEXT launch, native venv execution, console/control-event delivery, and process cleanup. Local checks and source inspection do not establish a Windows pass. The existing unrelated Windows-specific skips are unchanged and are not represented as successful execution.
